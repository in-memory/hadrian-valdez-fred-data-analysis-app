LOAD filesystem_module (os)
LOAD json_serialization_module (json)
LOAD http_client_module (requests)
LOAD tabular_data_module (pandas as pd)
FROM dotenv LOAD environment_loader (load_dotenv)


FUNCTION load_and_validate_api_key:
    # Step 1: Environment configuration
    - INVOKE load_dotenv
    - RETRIEVE api_key VIA os.getenv USING "FRED_API_KEY"

    # Step 2: Validation check
    IF api_key is None or empty:
        - RAISE ValueError "FRED_API_KEY was not found! Check your .env file."

    - RETURN api_key


CLASS MockResponse:
    CONSTRUCTOR (data):
        - SET self.status_code = 200
        - SET self._data = data
        - SET self.text = data converted to JSON string VIA json.dumps

    METHOD json:
        - RETURN self._data


FUNCTION prepare_end_point_parameters (api_key, series_id = "CPIAUCSL"):
    # Step 1: Local cache resolution
    - CREATE "data" directory IF NOT EXISTS
    - SET file_path = "data/" + series_id + ".json"

    IF file_path exists on filesystem:
        - PRINT "Loading {series_id} data from local cache..."
        - OPEN file_path IN read mode WITH utf-8 encoding
        - PARSE cached_data FROM JSON file
        - RETURN MockResponse instantiated with cached_data

    # Step 2: Remote endpoint fallback & persistence
    - PRINT "Fetching {series_id} data from FRED API..."
    - SET url = "https://api.stlouisfed.org/fred/series/observations"
    - SET params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json"
    }

    TRY:
        - DISPATCH HTTP GET request to url WITH params (timeout = 10s) INTO response

        IF response.status_code == 200:
            - OPEN file_path IN write mode WITH utf-8 encoding
            - DUMP response.json() into file WITH 4-space indentation
            - PRINT "Successfully saved data to {file_path}"

        - RETURN response

    CATCH requests.exceptions.RequestException AS e:
        - PRINT "Network error occurred: {e}"
        - RETURN None


FUNCTION process_response (response, series_id):
    # Step 1: Response verification & extraction
    IF response is not None AND response.status_code == 200:
        - EXTRACT "observations" list FROM response.json() INTO data
        - CONSTRUCT DataFrame retaining columns ["date", "value"] FROM data INTO df

        # Step 2: Type casting & sanitization
        - CONVERT df["value"] to numeric (coercing invalid values to NaN)
        - CONVERT df["date"] to datetime
        - DROP rows containing NaN values FROM df
        - SORT df BY "date" ascending

        # Step 3: Logging & output
        - PRINT "Processed {len(df)} observations for {series_id}."
        - RETURN df

    ELSE:
        - RESOLVE status = response.status_code (IF present) ELSE "Unknown"
        - PRINT "Error processing response. Status: {status}"
        - RETURN empty DataFrame