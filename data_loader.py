import glob
import json
import os
import re
import urllib.request
from datetime import datetime
from html import unescape
import requests
import pandas as pd
from dotenv import load_dotenv


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


class MockResponse:
    """A helper class to mimic a requests.Response object for locally cached JSONs."""

    def __init__(self, data: dict):
        self.status_code = 200
        self._data = data
        self.text = json.dumps(data)

    def json(self) -> dict:
        return self._data


# ---------------------------------------------------------------------------
# FRED API Network Calls
# ---------------------------------------------------------------------------

BASE_FRED_URL = "https://api.stlouisfed.org/fred"


def _request_fred(endpoint: str, params: dict, timeout: int = 10) -> dict | None:
    """
    Internal helper to execute FRED API GET requests with defensive error handling.
    Catches 429 (rate limiting), network errors, and standard HTTP failures.
    """
    try:
        api_key = load_and_validate_api_key()
    except ValueError as e:
        print(f"API Key error: {e}")
        return None

    url = f"{BASE_FRED_URL}/{endpoint.lstrip('/')}"
    req_params = {
        "api_key": api_key,
        "file_type": "json",
        **params
    }

    try:
        response = requests.get(url, params=req_params, timeout=timeout)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:
            print("FRED API Error: HTTP 429 Rate Limit Exceeded.")
            raise FredRateLimitError("FRED API rate limit exceeded (HTTP 429). Please wait a moment.")
        else:
            try:
                err_data = response.json()
                msg = err_data.get("error_message", f"HTTP {response.status_code}")
            except Exception:
                msg = f"HTTP {response.status_code}: {response.text[:200]}"
            print(f"FRED API Error ({response.status_code}): {msg}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Network error while connecting to FRED API ({endpoint}): {e}")
        return None


def fetch_category_info(category_id: int) -> dict | None:
    """
    Fetches metadata for a single category.
    Returns: {"id": int, "name": str, "parent_id": int} or None.
    """
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
    """
    Fetches immediate child categories for a given category.
    Returns: list of {"id": int, "name": str, "parent_id": int} or None.
    """
    data = _request_fred("category/children", {"category_id": category_id})
    if data and "categories" in data:
        children = []
        for cat in data["categories"]:
            children.append({
                "id": int(cat["id"]),
                "name": cat["name"],
                "parent_id": int(cat["parent_id"]) if cat.get("parent_id") is not None else category_id
            })
        return children
    return None


def fetch_category_series(
    category_id: int,
    limit: int = 50,
    offset: int = 0,
    order_by: str = "popularity",
    sort_order: str = "desc"
) -> dict | None:
    """
    Fetches series belonging to a category with pagination and multi-attribute sorting.
    Returns:
    {
        "count": int,
        "offset": int,
        "limit": int,
        "order_by": str,
        "sort_order": str,
        "series": list[dict]
    } or None.
    """
    params = {
        "category_id": category_id,
        "limit": limit,
        "offset": offset,
        "order_by": order_by,
        "sort_order": sort_order
    }
    data = _request_fred("category/series", params)
    if data and "seriess" in data:
        series_list = []
        for s in data["seriess"]:
            series_list.append({
                "id": str(s.get("id")),
                "title": str(s.get("title", s.get("id"))),
                "frequency": s.get("frequency_short", s.get("frequency")),
                "units": s.get("units_short", s.get("units")),
                "seasonal_adjustment": s.get("seasonal_adjustment_short", s.get("seasonal_adjustment")),
                "last_updated": s.get("last_updated"),
                "observation_start": s.get("observation_start"),
                "observation_end": s.get("observation_end"),
                "popularity": s.get("popularity", 0)
            })
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
    """
    Fetches the parent category hierarchy for a specific series.
    Returns: list of {"id": int, "name": str, "parent_id": int} or None.
    """
    data = _request_fred("series/categories", {"series_id": series_id})
    if data and "categories" in data:
        cats = []
        for cat in data["categories"]:
            cats.append({
                "id": int(cat["id"]),
                "name": cat["name"],
                "parent_id": int(cat["parent_id"]) if cat.get("parent_id") is not None else None
            })
        return cats
    return None


def fetch_series_observations(series_id: str) -> list[dict] | None:
    """
    Fetches historical observations for a series.
    Returns: list of {"date": str, "value": str} or None.
    """
    data = _request_fred("series/observations", {"series_id": series_id})
    if data and "observations" in data:
        return data["observations"]
    return None


def clean_and_format_notes(raw_text: str | None) -> str:
    """
    Sanitizes and formats FRED notes string.
    - Handles raw HTML elements (<p>, <br>, <a>, etc.) cleanly without leaking tags.
    - Converts hyperlinks (<a href="...">...</a>) to Markdown [text](url).
    - Unescapes HTML entities (&amp;, &lt;, &gt;, &#39;, &quot;).
    - Strips dangling/trailing tags (like </p>) and collapses redundant whitespace/newlines.
    """
    if not raw_text:
        return ""

    text = unescape(str(raw_text))

    # 1. Convert <a href="URL">TEXT</a> to Markdown [TEXT](URL)
    def _link_sub(match):
        href = match.group(1).strip()
        label = match.group(2).strip()
        label = re.sub(r'<[^>]+>', '', label)
        if not label:
            label = href
        return f"[{label}]({href})"

    text = re.sub(
        r'<a\s+[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        _link_sub,
        text,
        flags=re.IGNORECASE | re.DOTALL
    )

    # 2. Convert common block breaks (<br>, <p>, </p>, <div>, </div>) into newlines
    text = re.sub(r'<(?:br\s*/?|/p|p|/div|div)[^>]*>', '\n\n', text, flags=re.IGNORECASE)

    # 3. Format emphasis tags into Markdown
    text = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<i[^>]*>(.*?)</i>', r'*\1*', text, flags=re.IGNORECASE | re.DOTALL)

    # 4. Strip any remaining or orphaned HTML tags (e.g. </p>, </span>, etc.)
    text = re.sub(r'<[^>]+>', '', text)

    # 5. Clean up line breaks and spacing
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    lines = [line.strip() for line in text.split('\n')]

    cleaned_lines = []
    prev_blank = False
    for line in lines:
        if line:
            cleaned_lines.append(line)
            prev_blank = False
        elif not prev_blank:
            cleaned_lines.append("")
            prev_blank = True

    return '\n'.join(cleaned_lines).strip()


def clean_citation(raw_citation: str | None, series_id: str = "", title: str = "") -> str:
    """
    Cleans and standardizes the Suggested Citation text.
    Strips internal HTML, resolves dynamic date placeholders, or generates standard citation if missing.
    """
    date_str = datetime.now().strftime("%B %d, %Y")
    if raw_citation and raw_citation.strip():
        text = unescape(str(raw_citation))
        # Replace date span placeholder with current formatted date
        text = re.sub(r'<span[^>]*class=["\'][^"\']*cit-date[^"\']*["\'][^>]*>.*?</span>', date_str, text, flags=re.IGNORECASE | re.DOTALL)
        # Strip all HTML tags
        text = re.sub(r'<[^>]+>', ' ', text)
        # Normalize whitespace
        lines = [re.sub(r'\s+', ' ', l).strip() for l in text.split('\n')]
        lines = [l for l in lines if l]
        cit = ' '.join(lines)
        cit = re.sub(r'\s*,\s*,+', ',', cit)
        if date_str not in cit and "retrieved from FRED" in cit:
            cit = cit.rstrip('. ,') + f", {date_str}."
        return cit.strip().rstrip('.') + '.'
    elif series_id:
        title_str = title if title else series_id
        return f"{title_str} [{series_id}], retrieved from FRED, Federal Reserve Bank of St. Louis; https://fred.stlouisfed.org/series/{series_id}, {date_str}."
    return ""


def fetch_series_web_details(series_id: str, timeout: int = 4) -> dict:
    """
    Fetches rich metadata directly from the FRED series webpage:
    - Extracts full un-truncated series notes (including opening definition paragraphs cut off in API).
    - Extracts the official 'Suggested Citation' block.
    """
    url = f"https://fred.stlouisfed.org/series/{series_id.strip().upper()}"
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return {}

    # Extract series notes
    notes_match = re.search(
        r'<p\s+class="[^"]*series-notes[^"]*"[^>]*>(.*?)</p>\s*(?:</div>|\s*<div)',
        html,
        re.DOTALL | re.IGNORECASE
    )
    raw_web_notes = notes_match.group(1).strip() if notes_match else ""

    # Extract citation
    cit_match = re.search(
        r'<p\s+class="[^"]*citation[^"]*"[^>]*>(.*?)</p>',
        html,
        re.DOTALL | re.IGNORECASE
    )
    raw_cit = cit_match.group(1).strip() if cit_match else ""

    return {
        "notes": clean_and_format_notes(raw_web_notes) if raw_web_notes else "",
        "citation": clean_citation(raw_cit, series_id=series_id) if raw_cit else ""
    }


def fetch_series_metadata(series_id: str) -> dict | None:
    """
    Fetches series metadata (title, units, frequency, notes, citation, etc.).
    Combines FRED API metadata with full web details to ensure complete,
    un-truncated notes and citation blocks.
    """
    data = _request_fred("series", {"series_id": series_id})
    meta = None
    if data and "seriess" in data and len(data["seriess"]) > 0:
        meta = dict(data["seriess"][0])

    # Fetch web details for complete notes and suggested citation
    web_details = fetch_series_web_details(series_id)

    if meta is not None:
        api_notes = clean_and_format_notes(meta.get("notes", ""))
        web_notes = web_details.get("notes", "")

        # Use web notes if available and more complete (or when API notes is truncated/missing description)
        if web_notes and (len(web_notes) >= len(api_notes) or api_notes.startswith("announcements") or "</p>" in str(meta.get("notes", ""))):
            meta["notes"] = web_notes
        else:
            meta["notes"] = api_notes if api_notes else web_notes

        # Suggested Citation
        cit = web_details.get("citation", "")
        if not cit:
            cit = clean_citation("", series_id=series_id, title=meta.get("title", ""))
        meta["citation"] = cit
        return meta

    elif web_details.get("notes") or web_details.get("citation"):
        # Fallback if API failed but webpage succeeded
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


# ---------------------------------------------------------------------------
# Dataset Persistence & Local Cache Pipeline
# ---------------------------------------------------------------------------

DATA_DIR = "data"
METADATA_DIR = os.path.join(DATA_DIR, "metadata")
_SERIES_METADATA_CACHE: dict[str, dict] = {}


def get_or_fetch_series_metadata(series_id: str) -> dict:
    """
    Retrieves series metadata (title, units, frequency, notes, citation, etc.) with caching.
    Checks memory cache, then local disk cache (data/metadata/{series_id}.json),
    then fetches from FRED API + web enrichment.
    Returns metadata dict, or empty dict if unavailable.
    """
    series_id = series_id.strip().upper()

    def _is_cache_invalid(cached_meta: dict) -> bool:
        if not cached_meta or not isinstance(cached_meta, dict):
            return True
        notes = str(cached_meta.get("notes", ""))
        # Invalidate if notes has raw HTML tags, starts mid-sentence with announcements, or lacks citation
        if "</p>" in notes or "<p" in notes or notes.strip().startswith("announcements ("):
            return True
        if not cached_meta.get("citation"):
            return True
        return False

    # 1. In-memory cache
    if series_id in _SERIES_METADATA_CACHE:
        cached = _SERIES_METADATA_CACHE[series_id]
        if not _is_cache_invalid(cached):
            return cached

    # 2. Local disk cache
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

    # 3. FRED API network call + enrichment
    meta = fetch_series_metadata(series_id)
    if meta and isinstance(meta, dict):
        meta["notes"] = clean_and_format_notes(meta.get("notes", ""))
        if not meta.get("citation"):
            meta["citation"] = clean_citation("", series_id=series_id, title=meta.get("title", ""))
        _SERIES_METADATA_CACHE[series_id] = meta
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
        except Exception as e:
            print(f"Error saving metadata cache for {series_id}: {e}")
        return meta

    # 4. Fallback: check if local observations JSON exists with some basic keys
    json_path = os.path.join(DATA_DIR, f"{series_id}.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            fallback = {
                "id": series_id,
                "title": series_id,
                "units": data.get("units", "N/A"),
                "units_short": data.get("units", "N/A"),
                "frequency": "N/A",
                "notes": "",
                "citation": clean_citation("", series_id=series_id)
            }
            return fallback
        except Exception:
            pass

    return {}


def list_cached_series_ids() -> list[str]:
    """
    Scans the local 'data/' directory for saved series datasets (.parquet, .csv, .json).
    Returns a sorted list of unique series IDs.
    """
    if not os.path.exists(DATA_DIR):
        return []

    series_ids = set()
    for ext in ("*.parquet", "*.csv", "*.json"):
        for file_path in glob.glob(os.path.join(DATA_DIR, ext)):
            base = os.path.basename(file_path)
            # Exclude category cache, metadata dir, or non-series files
            if base in ("fred_cache.json", "categories", "metadata") or os.path.isdir(file_path):
                continue
            series_name = os.path.splitext(base)[0]
            if series_name:
                series_ids.add(series_name.upper())

    return sorted(list(series_ids))


def is_series_cached(series_id: str) -> bool:
    """Checks whether a dataset for series_id exists on disk."""
    series_id = series_id.strip().upper()
    for ext in (".parquet", ".csv", ".json"):
        if os.path.exists(os.path.join(DATA_DIR, f"{series_id}{ext}")):
            return True
    return False


def load_series_from_disk(series_id: str) -> pd.DataFrame | None:
    """
    Attempts to load a series dataset from local storage (data/*.parquet, *.csv, *.json).
    Returns cleaned DataFrame with ['date', 'value'] or None if not found.
    """
    series_id = series_id.strip().upper()
    parquet_path = os.path.join(DATA_DIR, f"{series_id}.parquet")
    csv_path = os.path.join(DATA_DIR, f"{series_id}.csv")
    json_path = os.path.join(DATA_DIR, f"{series_id}.json")

    df = None
    if os.path.exists(parquet_path):
        try:
            df = pd.read_parquet(parquet_path)
        except Exception as e:
            print(f"Error reading parquet file {parquet_path}: {e}")

    if df is None and os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path)
        except Exception as e:
            print(f"Error reading CSV file {csv_path}: {e}")

    if df is None and os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            observations = data.get("observations", [])
            df = pd.DataFrame(observations)
        except Exception as e:
            print(f"Error reading JSON file {json_path}: {e}")

    if df is not None and not df.empty and "date" in df.columns and "value" in df.columns:
        df = df[["date", "value"]].copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna().sort_values("date").reset_index(drop=True)
        return df

    return None


def save_series_to_disk(series_id: str, df: pd.DataFrame) -> None:
    """
    Persists cleaned time series DataFrame to data/{series_id}.parquet.
    """
    if df is None or df.empty:
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    series_id = series_id.strip().upper()
    parquet_path = os.path.join(DATA_DIR, f"{series_id}.parquet")
    try:
        clean_df = df[["date", "value"]].copy()
        clean_df.to_parquet(parquet_path, index=False)
        print(f"Successfully saved {series_id} dataset to {parquet_path}")
    except Exception as e:
        print(f"Error saving {series_id} to parquet: {e}")
        # Fallback to CSV
        csv_path = os.path.join(DATA_DIR, f"{series_id}.csv")
        clean_df.to_csv(csv_path, index=False)


def get_or_fetch_series_data(series_id: str) -> pd.DataFrame:
    """
    Retrieves series data by checking local cache first, then fetching from FRED API.
    Saves new observations locally to .parquet.
    Returns cleaned DataFrame with ['date', 'value'].
    """
    series_id = series_id.strip().upper()

    # 1. Local Cache Check
    cached_df = load_series_from_disk(series_id)
    if cached_df is not None and not cached_df.empty:
        print(f"Loaded {series_id} from local cache ({len(cached_df)} records).")
        return cached_df

    # 2. FRED API Fetch
    print(f"Fetching {series_id} observations from FRED API...")
    observations = fetch_series_observations(series_id)
    if not observations:
        print(f"No observations returned from FRED API for {series_id}.")
        return pd.DataFrame()

    df = pd.DataFrame(observations)
    if "date" in df.columns and "value" in df.columns:
        df = df[["date", "value"]].copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna().sort_values("date").reset_index(drop=True)

        # Persist locally
        save_series_to_disk(series_id, df)
        return df

    return pd.DataFrame()


# ---------------------------------------------------------------------------
# Backwards Compatibility Wrappers
# ---------------------------------------------------------------------------

def prepare_end_point_parameters(api_key: str, series_id: str = "CPIAUCSL"):
    """
    Legacy helper: Checks local cache or fetches series from FRED API.
    Returns requests.Response or MockResponse.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    json_path = os.path.join(DATA_DIR, f"{series_id}.json")

    # Check local cache
    cached_df = load_series_from_disk(series_id)
    if cached_df is not None and not cached_df.empty:
        # Wrap into MockResponse
        records = [
            {"date": d.strftime("%Y-%m-%d"), "value": str(v)}
            for d, v in zip(cached_df["date"], cached_df["value"])
        ]
        return MockResponse({"observations": records})

    # Fetch from FRED API
    url = f"{BASE_FRED_URL}/series/observations"
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(response.json(), f, indent=4)
        return response
    except requests.exceptions.RequestException as e:
        print(f"Network error: {e}")
        return None


def process_response(response, series_id: str) -> pd.DataFrame:
    """Legacy helper: processes response into a cleaned DataFrame."""
    if response and response.status_code == 200:
        data = response.json().get("observations", [])
        df = pd.DataFrame(data)[["date", "value"]]
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df["date"] = pd.to_datetime(df["date"])
        df = df.dropna().sort_values("date").reset_index(drop=True)
        return df
    return pd.DataFrame()
