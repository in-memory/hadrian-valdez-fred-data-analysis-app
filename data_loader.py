import os
import json
import requests
import pandas as pd
from dotenv import load_dotenv


def load_and_validate_api_key() -> str:
    """Loads and validates the FRED API key from environment variables."""
    load_dotenv()
    api_key = os.getenv("FRED_API_KEY")

    if not api_key:
        raise ValueError("FRED_API_KEY was not found! Check your .env file.")

    return api_key


class MockResponse:
    """A helper class to mimic a requests.Response object for locally cached JSONs."""

    def __init__(self, data: dict):
        self.status_code = 200
        self._data = data
        self.text = json.dumps(data)

    def json(self) -> dict:
        return self._data


def prepare_end_point_parameters(api_key: str, series_id: str = "CPIAUCSL"):
    """
    Checks if a series exists locally in the 'data/' folder. 
    If so, returns a MockResponse. If not, fetches it from the FRED API and caches it.
    """
    os.makedirs("data", exist_ok=True)
    file_path = f"data/{series_id}.json"

    # Check local cache first
    if os.path.exists(file_path):
        print(f"Loading {series_id} data from local cache...")
        with open(file_path, "r", encoding="utf-8") as f:
            cached_data = json.load(f)
        return MockResponse(cached_data)

    # Fetch from FRED API if not cached
    print(f"Fetching {series_id} data from FRED API...")
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        # Save the JSON response if successful
        if response.status_code == 200:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(response.json(), f, indent=4)
            print(f"Successfully saved data to {file_path}")
        return response
    except requests.exceptions.RequestException as e:
        print(f"Network error occurred: {e}")
        return None


def process_response(response, series_id: str) -> pd.DataFrame:
    """Processes a raw API or mock response into a cleaned Pandas DataFrame."""
    if response and response.status_code == 200:
        data = response.json().get("observations", [])
        df = pd.DataFrame(data)[["date", "value"]]

        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df["date"] = pd.to_datetime(df["date"])
        df = df.dropna().sort_values("date")

        print(f"Processed {len(df)} observations for {series_id}.")
        return df
    else:
        status = getattr(response, "status_code", "Unknown")
        print(f"Error processing response. Status: {status}")
        return pd.DataFrame()
