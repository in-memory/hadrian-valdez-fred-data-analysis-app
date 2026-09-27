LOAD file_pattern_matcher (glob)
LOAD filesystem_module (os)
LOAD tabular_data_module (pandas)
LOAD visualization_module (plotly.express)
LOAD web_dashboard_framework (streamlit)

FROM data_loader LOAD load_and_validate_api_key
FROM data_loader LOAD prepare_end_point_parameters


FUNCTION get_available_local_series:
    IF "data" directory does not exist:
        - RETURN empty list

    - FIND all file paths matching "data/*.json"
    - EXTRACT base filename without ".json" extension for each file INTO series_ids
    - RETURN sorted series_ids


FUNCTION load_series_data (series_id):
    - RETRIEVE api_key VIA load_and_validate_api_key
    - DISPATCH request VIA prepare_end_point_parameters (api_key, series_id) INTO response

    IF response is valid AND response.status_code == 200:
        - EXTRACT "observations" list from response JSON
        - CONSTRUCT DataFrame retaining columns ["date", "value"] INTO temp_df
        - CONVERT "date" column to datetime dtype
        - CONVERT "value" column to numeric (coercing invalid entries to NaN)
        - DROP all rows containing NaN values
        - SORT temp_df by "date" ascending
        - RETURN temp_df

    ELSE:
        - RESOLVE status from response.status_code OR fallback to "Unknown"
        - DISPLAY UI error message "Failed to fetch data for {series_id}. Status: {status}"
        - RETURN empty DataFrame


FUNCTION main:
    - RENDER main title "FRED Economic Data Explorer"

    - RETRIEVE local_series VIA get_available_local_series
    - SET placeholder_option = "-- Select Saved Series --"

    # Step 1: Session state initialization
    IF "dropdown_selection" not in st.session_state:
        - SET st.session_state.dropdown_selection = placeholder_option

    IF "active_series" not in st.session_state:
        IF "CPIAUCSL" in local_series:
            - SET st.session_state.active_series = "CPIAUCSL"
        ELSE IF local_series is not empty:
            - SET st.session_state.active_series = local_series[0]
        ELSE:
            - SET st.session_state.active_series = "CPIAUCSL"

    # Step 2: Sidebar controls & user input handling
    - RENDER sidebar header "Data Configuration"

    - RENDER sidebar text_input "Fetch New Series ID"
    - STRIP whitespace and CONVERT to uppercase INTO new_series_input
    - RENDER sidebar button "Fetch & Load Series" INTO fetch_button

    IF fetch_button is clicked AND new_series_input is not empty:
        - RESET st.session_state.dropdown_selection = placeholder_option
        - SET st.session_state.active_series = new_series_input
        - TRIGGER st.rerun

    - CONSTRUCT dropdown_options = [placeholder_option] + local_series
    - RENDER sidebar selectbox "Load from Local Cache" bound to "dropdown_selection" INTO selected_local

    IF selected_local != placeholder_option AND selected_local != st.session_state.active_series:
        - SET st.session_state.active_series = selected_local
        - TRIGGER st.rerun

    # Step 3: Fetch active dataset & guard
    - SET target_series = st.session_state.active_series
    - RETRIEVE df VIA load_series_data (target_series)

    IF df is empty:
        - DISPLAY UI warning "No data available to display. Check your series ID or API key."
        - RETURN

    # Step 4: Time horizon filtering
    - RENDER subheader "Analyzing Series: `{target_series}`"
    - RENDER segmented_control with options ["1Y", "5Y", "10Y", "Max"] (default="10Y") INTO time_frame
    - EXTRACT max_date from df["date"]

    IF time_frame == "1Y":
        - SET start_date = max_date - 1 year offset
    ELSE IF time_frame == "5Y":
        - SET start_date = max_date - 5 years offset
    ELSE IF time_frame == "10Y":
        - SET start_date = max_date - 10 years offset
    ELSE ("Max"):
        - SET start_date = minimum date in df["date"]

    - FILTER df WHERE date >= start_date INTO filtered_df

    # Step 5: Chart generation and data table display
    - CONSTRUCT interactive line chart figure FROM filtered_df (x="date", y="value")
    - UPDATE figure layout with axis titles ("Date", "Observation Value")
    - RENDER figure via st.plotly_chart (width="stretch")

    WITH collapsible expander "View Raw Data Table":
        - RENDER data table showing the last 100 rows of filtered_df (width="stretch")


IF executed directly as "__main__":
    - INVOKE main