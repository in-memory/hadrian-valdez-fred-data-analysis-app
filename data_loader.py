import glob
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime
from html import unescape
import requests
import pandas as pd  # type: ignore[import-untyped]
from dotenv import load_dotenv

BASE_FRED_URL = "https://api.stlouisfed.org/fred"
DATA_DIR = "data"
METADATA_DIR = os.path.join(DATA_DIR, "metadata")
_SERIES_METADATA_CACHE: dict[str, dict] = {}

# Pre-compiled regex patterns for string cleansing
RE_A_HREF = re.compile(
    r'<a\s+[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
RE_BLOCK_BREAKS = re.compile(r'<(?:br\s*/?|p|div)[^>]*>', re.IGNORECASE)
RE_STRONG = re.compile(
    r'<strong[^>]*>(.*?)</strong>', re.IGNORECASE | re.DOTALL)
RE_BOLD = re.compile(r'<b[^>]*>(.*?)</b>', re.IGNORECASE | re.DOTALL)
RE_EM = re.compile(r'<em[^>]*>(.*?)</em>', re.IGNORECASE | re.DOTALL)
RE_ITALIC = re.compile(r'<i[^>]*>(.*?)</i>', re.IGNORECASE | re.DOTALL)
RE_HTML_TAGS = re.compile(r'<[^>]+>')
RE_CONSECUTIVE_NEWLINES = re.compile(r'\n{3,}')
RE_CIT_DATE = re.compile(
    r'<span[^>]*class=["\'][^"\']*cit-date[^"\']*["\'][^>]*>.*?</span>', re.IGNORECASE | re.DOTALL)


class FredAPIError(Exception):
    """Base exception for FRED API errors."""
    pass


class FredRateLimitError(FredAPIError):
    """Raised when FRED API responds with HTTP 429 Too Many Requests."""
    pass


def load_and_validate_api_key() -> str:
    """Loads and validates the FRED API key from environment variables."""
    load_dotenv()
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        raise ValueError("FRED_API_KEY was not found! Check your .env file.")
    return api_key.strip()


def _request_fred(endpoint: str, params: dict, timeout: int = 10) -> dict | None:
    try:
        api_key = load_and_validate_api_key()
    except ValueError as e:
        print(f"API Key error: {e}")
        return None

    url = f"{BASE_FRED_URL}/{endpoint.lstrip('/')}"
    req_params = {"api_key": api_key, "file_type": "json", **params}

    try:
        response = requests.get(url, params=req_params, timeout=timeout)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:
            raise FredRateLimitError(
                "FRED API rate limit exceeded (HTTP 429).")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Network error while connecting to FRED API ({endpoint}): {e}")
        return None


def fetch_category_info(category_id: int) -> dict | None:
    data = _request_fred("category", {"category_id": category_id})
    if data and "categories" in data and len(data["categories"]) > 0:
        cat = data["categories"][0]
        return {
            "id": int(cat["id"]),
            "name": cat["name"],
            "parent_id": int(cat["parent_id"]) if cat.get("parent_id") is not None else None
        }
    return None


def fetch_category_children(category_id: int) -> list[dict] | None:
    data = _request_fred("category/children", {"category_id": category_id})
    if data and "categories" in data:
        return [
            {
                "id": int(cat["id"]),
                "name": cat["name"],
                "parent_id": int(cat["parent_id"]) if cat.get("parent_id") is not None else category_id
            }
            for cat in data["categories"]
        ]
    return None


def fetch_category_series(
    category_id: int,
    limit: int = 50,
    offset: int = 0,
    order_by: str = "popularity",
    sort_order: str = "desc"
) -> dict | None:
    params = {
        "category_id": category_id,
        "limit": limit,
        "offset": offset,
        "order_by": order_by,
        "sort_order": sort_order
    }
    data = _request_fred("category/series", params)
    if data and "seriess" in data:
        series_list = [
            {
                "id": str(s.get("id")),
                "title": str(s.get("title", s.get("id"))),
                "frequency": s.get("frequency_short", s.get("frequency")),
                "units": s.get("units_short", s.get("units")),
                "seasonal_adjustment": s.get("seasonal_adjustment_short", s.get("seasonal_adjustment")),
                "last_updated": s.get("last_updated"),
                "observation_start": s.get("observation_start"),
                "observation_end": s.get("observation_end"),
                "popularity": s.get("popularity", 0)
            }
            for s in data["seriess"]
        ]
        return {
            "count": int(data.get("count", len(series_list))),
            "offset": int(data.get("offset", offset)),
            "limit": int(data.get("limit", limit)),
            "order_by": data.get("order_by", order_by),
            "sort_order": data.get("sort_order", sort_order),
            "series": series_list
        }
    return None


def fetch_series_categories(series_id: str) -> list[dict] | None:
    data = _request_fred("series/categories", {"series_id": series_id})
    if data and "categories" in data:
        return [
            {
                "id": int(cat["id"]),
                "name": cat["name"],
                "parent_id": int(cat["parent_id"]) if cat.get("parent_id") is not None else None
            }
            for cat in data["categories"]
        ]
    return None


def fetch_series_observations(series_id: str) -> list[dict] | None:
    data = _request_fred("series/observations", {"series_id": series_id})
    return data.get("observations") if data else None


def clean_and_format_notes(raw_text: str | None) -> str:
    if not raw_text:
        return ""

    text = unescape(str(raw_text))

    def _link_sub(match):
        href = match.group(1).strip()
        label = RE_HTML_TAGS.sub('', match.group(2).strip()) or href
        return f"[{label}]({href})"

    text = RE_A_HREF.sub(_link_sub, text)
    text = RE_BLOCK_BREAKS.sub('\n\n', text)
    text = RE_STRONG.sub(r'**\1**', text)
    text = RE_BOLD.sub(r'**\1**', text)
    text = RE_EM.sub(r'*\1*', text)
    text = RE_ITALIC.sub(r'*\1*', text)
    text = RE_HTML_TAGS.sub('', text)

    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = "\n".join(line.strip() for line in text.split("\n"))
    return RE_CONSECUTIVE_NEWLINES.sub('\n\n', text).strip()


def clean_citation(raw_citation: str | None, series_id: str = "", title: str | None = "") -> str:
    date_str = datetime.now().strftime("%B %d, %Y")
    if raw_citation and raw_citation.strip():
        text = unescape(str(raw_citation))
        text = RE_CIT_DATE.sub(date_str, text)
        text = RE_HTML_TAGS.sub(' ', text)
        cit = ' '.join(re.sub(r'\s+', ' ', l).strip()
                       for l in text.split('\n') if l.strip())
        cit = re.sub(r'\s*,\s*,+', ',', cit)
        if date_str not in cit and "retrieved from FRED" in cit:
            cit = cit.rstrip('. ,') + f", {date_str}."
        return cit.strip().rstrip('.') + '.'
    elif series_id:
        title_str = title if title else series_id
        return f"{title_str} [{series_id}], retrieved from FRED, Federal Reserve Bank of St. Louis; https://fred.stlouisfed.org/series/{series_id}, {date_str}."
    return ""


def fetch_series_web_details(series_id: str, timeout: int = 4) -> dict:
    clean_id = urllib.parse.quote(series_id.strip().upper(), safe="")
    url = f"https://fred.stlouisfed.org/series/{clean_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
            html = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return {}

    notes_match = re.search(
        r'<p\s+class="[^"]*series-notes[^"]*"[^>]*>(.*?)</p>\s*(?:</div>|\s*<div)', html, re.DOTALL | re.IGNORECASE)
    cit_match = re.search(
        r'<p\s+class="[^"]*citation[^"]*"[^>]*>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)

    raw_web_notes = notes_match.group(1).strip() if notes_match else ""
    raw_cit = cit_match.group(1).strip() if cit_match else ""

    return {
        "notes": clean_and_format_notes(raw_web_notes) if raw_web_notes else "",
        "citation": clean_citation(raw_cit, series_id=series_id) if raw_cit else ""
    }


def fetch_series_metadata(series_id: str) -> dict | None:
    data = _request_fred("series", {"series_id": series_id})
    meta = dict(data["seriess"][0]) if data and "seriess" in data and len(
        data["seriess"]) > 0 else None
    web_details = fetch_series_web_details(series_id)

    if meta is not None:
        api_notes = clean_and_format_notes(meta.get("notes", ""))
        web_notes = web_details.get("notes", "")

        if web_notes and (len(web_notes) >= len(api_notes) or api_notes.startswith("announcements") or "</p>" in str(meta.get("notes", ""))):
            meta["notes"] = web_notes
        else:
            meta["notes"] = api_notes if api_notes else web_notes

        meta["citation"] = web_details.get("citation") or clean_citation(
            "", series_id=series_id, title=meta.get("title", ""))
        return meta

    elif web_details.get("notes") or web_details.get("citation"):
        return {
            "id": series_id,
            "title": series_id,
            "units": "N/A",
            "units_short": "N/A",
            "frequency": "N/A",
            "notes": web_details.get("notes", ""),
            "citation": web_details.get("citation", clean_citation("", series_id=series_id))
        }
    return None


def get_or_fetch_series_metadata(series_id: str) -> dict:
    series_id = series_id.strip().upper()

    def _is_cache_invalid(cached_meta: dict) -> bool:
        if not cached_meta or not isinstance(cached_meta, dict):
            return True
        notes = str(cached_meta.get("notes", ""))
        return "</p>" in notes or "<p" in notes or notes.strip().startswith("announcements (") or not cached_meta.get("citation")

    if series_id in _SERIES_METADATA_CACHE and not _is_cache_invalid(_SERIES_METADATA_CACHE[series_id]):
        return _SERIES_METADATA_CACHE[series_id]

    os.makedirs(METADATA_DIR, exist_ok=True)
    meta_path = os.path.join(METADATA_DIR, f"{series_id}.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            if isinstance(meta, dict) and meta and not _is_cache_invalid(meta):
                _SERIES_METADATA_CACHE[series_id] = meta
                return meta
        except Exception as e:
            print(f"Error reading metadata cache for {series_id}: {e}")

    meta = fetch_series_metadata(series_id)
    if meta and isinstance(meta, dict):
        meta["notes"] = clean_and_format_notes(meta.get("notes", ""))
        if not meta.get("citation"):
            meta["citation"] = clean_citation(
                "", series_id=series_id, title=meta.get("title", ""))
        _SERIES_METADATA_CACHE[series_id] = meta
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
        except Exception as e:
            print(f"Error saving metadata cache for {series_id}: {e}")
        return meta

    return {}


def list_cached_series_ids() -> list[str]:
    if not os.path.exists(DATA_DIR):
        return []

    series_ids = set()
    for ext in ("*.parquet", "*.csv", "*.json"):
        for file_path in glob.glob(os.path.join(DATA_DIR, ext)):
            base = os.path.basename(file_path)
            if base in ("fred_cache.json", "categories", "metadata") or os.path.isdir(file_path):
                continue
            series_name = os.path.splitext(base)[0]
            if series_name:
                series_ids.add(series_name.upper())

    return sorted(list(series_ids))


def is_series_cached(series_id: str) -> bool:
    series_id = series_id.strip().upper()
    for ext in (".parquet", ".csv", ".json"):
        if os.path.exists(os.path.join(DATA_DIR, f"{series_id}{ext}")):
            return True
    return False


def load_series_from_disk(series_id: str) -> pd.DataFrame | None:
    series_id = series_id.strip().upper()
    parquet_path = os.path.join(DATA_DIR, f"{series_id}.parquet")
    csv_path = os.path.join(DATA_DIR, f"{series_id}.csv")
    json_path = os.path.join(DATA_DIR, f"{series_id}.json")

    df = None
    if os.path.exists(parquet_path):
        try:
            df = pd.read_parquet(parquet_path)
        except Exception:
            pass

    if df is None and os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path)
        except Exception:
            pass

    if df is None and os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                df = pd.DataFrame(json.load(f).get("observations", []))
        except Exception:
            pass

    if df is not None and not df.empty and "date" in df.columns and "value" in df.columns:
        df = df[["date", "value"]].copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        return df.dropna().sort_values("date").reset_index(drop=True)

    return None


def save_series_to_disk(series_id: str, df: pd.DataFrame) -> None:
    if df is None or df.empty or "date" not in df.columns or "value" not in df.columns:
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    series_id = series_id.strip().upper()
    clean_df = df[["date", "value"]].copy()

    parquet_path = os.path.join(DATA_DIR, f"{series_id}.parquet")
    try:
        clean_df.to_parquet(parquet_path, index=False)
    except Exception as e:
        print(f"Parquet write failed ({e}); falling back to CSV.")
        csv_path = os.path.join(DATA_DIR, f"{series_id}.csv")
        clean_df.to_csv(csv_path, index=False)


def get_or_fetch_series_data(series_id: str) -> pd.DataFrame:
    series_id = series_id.strip().upper()

    cached_df = load_series_from_disk(series_id)
    if cached_df is not None and not cached_df.empty:
        return cached_df

    observations = fetch_series_observations(series_id)
    if not observations:
        return pd.DataFrame()

    df = pd.DataFrame(observations)
    if "date" in df.columns and "value" in df.columns:
        df = df[["date", "value"]].copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna().sort_values("date").reset_index(drop=True)
        save_series_to_disk(series_id, df)
        return df

    return pd.DataFrame()
