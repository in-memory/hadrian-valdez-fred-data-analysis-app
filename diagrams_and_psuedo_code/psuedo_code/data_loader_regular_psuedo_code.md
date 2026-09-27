LOAD filesystem_module (os)
LOAD json_serialization_module (json)
LOAD http_client_module (requests)
LOAD tabular_data_module (pandas as pd)
FROM dotenv LOAD environment_loader (load_dotenv)


FUNCTION load_and_validate_api_key:
    - INVOKE load_dotenv to read environment variables
    - RETRIEVE api_key VIA os.getenv USING key "FRED_API_KEY"

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
    - CREATE "data" directory on disk IF it does not already exist
    - CONSTRUCT file_path = "data/" + series_id + ".json"

    # Step 1: Check local cache first
    IF file_path exists on filesystem:
        - PRINT "Loading {series_id} data from local cache..."
        - OPEN file_path IN read mode WITH utf-8 encoding
        - PARSE cached_data FROM JSON file
        - RETURN MockResponse instantiated with cached_data

    # Step 2: Fallback to remote FRED API call
    - PRINT "Fetching {series_id} data from FRED API..."
    - SET url = "https://api.stlouisfed.org/fred/series/observations"
    - SET params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json"
    }

    TRY:
        - DISPATCH HTTP GET request to url WITH params (timeout = 10s) INTO response
        
        # Save the JSON response if successful
        IF response.status_code == 200:
            - OPEN file_path IN write mode WITH utf-8 encoding
            - DUMP response.json() into file WITH 4-space indentation
            - PRINT "Successfully saved data to {file_path}"

        - RETURN response

    CATCH requests.exceptions.RequestException AS e:
        - PRINT "Network error occurred: {e}"
        - RETURN None


FUNCTION process_response (response, series_id):
    IF response is not None AND response.status_code == 200:
        - PARSE response.json() AND EXTRACT "observations" list INTO data
        - CONSTRUCT DataFrame retaining columns ["date", "value"] FROM data INTO df

        # Data sanitization and sorting
        - CONVERT df["value"] to numeric (coercing errors to NaN)
        - CONVERT df["date"] to datetime
        - DROP all rows containing NaN values FROM df
        - SORT df BY "date" ascending

        - PRINT "Processed {len(df)} observations for {series_id}."
        - RETURN df

    ELSE:
        - RESOLVE status = response.status_code (IF present) ELSE "Unknown"
        - PRINT "Error processing response. Status: {status}"
        - RETURN empty DataFrame