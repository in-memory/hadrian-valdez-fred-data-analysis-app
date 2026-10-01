import glob
import json
import os
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


def fetch_category_series(category_id: int, limit: int = 1000) -> list[dict] | None:
    """
    Fetches series belonging to a category.
    Returns: list of {"id": str, "title": str} or None.
    """
    data = _request_fred("category/series", {"category_id": category_id, "limit": limit})
    if data and "seriess" in data:
        series_list = []
        for s in data["seriess"]:
            series_list.append({
                "id": str(s.get("id")),
                "title": str(s.get("title", s.get("id"))),
                "frequency": s.get("frequency_short", s.get("frequency")),
                "units": s.get("units_short", s.get("units")),
                "last_updated": s.get("last_updated")
            })
        return series_list
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


def fetch_series_metadata(series_id: str) -> dict | None:
    """
    Fetches series metadata (title, units, frequency, etc.).
    """
    data = _request_fred("series", {"series_id": series_id})
    if data and "seriess" in data and len(data["seriess"]) > 0:
        return data["seriess"][0]
    return None


# ---------------------------------------------------------------------------
# Dataset Persistence & Local Cache Pipeline
# ---------------------------------------------------------------------------

DATA_DIR = "data"


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
            # Exclude category cache or non-series files
            if base in ("fred_cache.json", "categories"):
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
