import glob
import os
import pandas as pd
import plotly.express as px
import streamlit as st

# Import your data loader functions
from data_loader import (
    load_and_validate_api_key,
    prepare_end_point_parameters,
)


def get_available_local_series() -> list:
    """Scans the local 'data/' directory for saved JSON series IDs."""
    if not os.path.exists("data"):
        return []
    files = glob.glob("data/*.json")
    series_ids = [os.path.splitext(os.path.basename(f))[0] for f in files]
    return sorted(series_ids)


def load_series_data(series_id: str) -> pd.DataFrame:
    """Loads data either from local cache or fetches it via data_loader if missing."""
    api_key = load_and_validate_api_key()
    response = prepare_end_point_parameters(api_key, series_id)

    if response and response.status_code == 200:
        data = response.json().get("observations", [])
        temp_df = pd.DataFrame(data)[["date", "value"]]
        temp_df["date"] = pd.to_datetime(temp_df["date"])
        temp_df["value"] = pd.to_numeric(temp_df["value"], errors="coerce")
        return temp_df.dropna().sort_values("date")
    else:
        status = getattr(response, "status_code", "Unknown")
        st.error(f"Failed to fetch data for {series_id}. Status: {status}")
        return pd.DataFrame()


def main():
    st.title("FRED Economic Data Explorer")

    local_series = get_available_local_series()
    placeholder_option = "-- Select Saved Series --"

    # Initialize session state keys
    if "dropdown_selection" not in st.session_state:
        st.session_state.dropdown_selection = placeholder_option

    if "active_series" not in st.session_state:
        st.session_state.active_series = "CPIAUCSL" if "CPIAUCSL" in local_series else (
            local_series[0] if local_series else "CPIAUCSL")

    # --- SIDEBAR CONTROLS ---
    st.sidebar.header("Data Configuration")

    # 1. Text input for series ID
    new_series_input = st.sidebar.text_input(
        "🌐 Fetch New Series ID",
        placeholder="e.g., GDP, UNRATE, DGS10",
        key="new_series_input",
    ).strip().upper()

    fetch_button = st.sidebar.button("Fetch & Load Series")

    # 2. If the user clicks Fetch & Load:
    # - Force the selectbox state back to the placeholder option
    # - Set active_series directly to the typed input
    if fetch_button and new_series_input:
        st.session_state.dropdown_selection = placeholder_option
        st.session_state.active_series = new_series_input
        st.rerun()

    st.sidebar.markdown("---")

    # 3. Dropdown for locally saved data bound to st.session_state.dropdown_selection
    dropdown_options = [placeholder_option] + local_series

    selected_local = st.sidebar.selectbox(
        "📁 Load from Local Cache",
        options=dropdown_options,
        key="dropdown_selection",
    )

    # If the user picks something from the dropdown that is not the placeholder,
    # update active_series to that selection
    if selected_local != placeholder_option and selected_local != st.session_state.active_series:
        st.session_state.active_series = selected_local
        st.rerun()

    target_series = st.session_state.active_series

    # Load the dataframe for the active target series
    df = load_series_data(target_series)

    if df.empty:
        st.warning(
            "No data available to display. Check your series ID or API key.")
        return

    # --- MAIN DASHBOARD UI ---
    st.subheader(f"Analyzing Series: `{target_series}`")

    # Time horizon buttons
    time_frame = st.segmented_control(
        "Select Time Horizon", options=["1Y", "5Y", "10Y", "Max"], default="10Y"
    )

    max_date = df["date"].max()

    if time_frame == "1Y":
        start_date = max_date - pd.DateOffset(years=1)
    elif time_frame == "5Y":
        start_date = max_date - pd.DateOffset(years=5)
    elif time_frame == "10Y":
        start_date = max_date - pd.DateOffset(years=10)
    else:  # "Max"
        start_date = df["date"].min()

    filtered_df = df[df["date"] >= start_date]

    # Plotting with Plotly
    figure = px.line(
        filtered_df,
        x="date",
        y="value",
        title=f"{target_series} Over Time ({time_frame})",
        markers=False,
    )
    figure.update_layout(xaxis_title="Date", yaxis_title="Observation Value")

    st.plotly_chart(figure, width="stretch")

    # Display raw data expander
    with st.expander("View Raw Data Table"):
        st.dataframe(filtered_df.tail(100), width="stretch")


if __name__ == "__main__":
    main()
