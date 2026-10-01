import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# Strictly import from category_manager and data_loader
# dashboard.py must NOT directly call the FRED API or read/write cache files
import category_manager
import data_loader

# ---------------------------------------------------------------------------
# Page Configuration & Styling
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="FRED Category Explorer & Series Visualizer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for modern styling and card designs
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0.02));
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 10px;
        padding: 14px 18px;
        margin-bottom: 10px;
    }
    .metric-label {
        font-size: 0.82rem;
        color: #94a3b8;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .metric-val {
        font-size: 1.6rem;
        font-weight: 700;
        color: #f8fafc;
        margin-top: 4px;
    }
    .metric-sub {
        font-size: 0.85rem;
        color: #38bdf8;
        margin-top: 2px;
    }
    .crumb-bar {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 6px;
        background: rgba(15, 23, 42, 0.4);
        padding: 10px 14px;
        border-radius: 8px;
        border: 1px solid rgba(255, 255, 255, 0.08);
        margin-bottom: 16px;
    }
    .category-card {
        border: 1px solid rgba(255, 255, 255, 0.12);
        background: rgba(30, 41, 59, 0.5);
        border-radius: 8px;
        padding: 12px;
        transition: transform 0.15s ease, border-color 0.15s ease;
    }
    .category-card:hover {
        border-color: #38bdf8;
        transform: translateY(-2px);
    }
    .badge-cached {
        background-color: #065f46;
        color: #34d399;
        font-size: 0.75rem;
        padding: 2px 8px;
        border-radius: 9999px;
        font-weight: 600;
    }
    .badge-remote {
        background-color: #1e3a8a;
        color: #93c5fd;
        font-size: 0.75rem;
        padding: 2px 8px;
        border-radius: 9999px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

PLACEHOLDER_SAVED_DATASET = "-- Select Saved Dataset --"
VIEW_EXPLORER = "📂 Category Explorer & Series"
VIEW_VISUALIZER = "📈 Series Visualization"


# ---------------------------------------------------------------------------
# State Management & Navigation Functions
# ---------------------------------------------------------------------------
def init_session_state():
    """Initializes Streamlit session state variables."""
    if "current_category_id" not in st.session_state:
        st.session_state.current_category_id = 0  # Start at Root (0)

    if "history_stack" not in st.session_state:
        st.session_state.history_stack = []

    if "forward_stack" not in st.session_state:
        st.session_state.forward_stack = []

    if "active_series_id" not in st.session_state:
        cached = data_loader.list_cached_series_ids()
        st.session_state.active_series_id = "CPIAUCSL" if "CPIAUCSL" in cached else (cached[0] if cached else "CPIAUCSL")

    if "saved_datasets_select" not in st.session_state:
        cached = data_loader.list_cached_series_ids()
        active = st.session_state.active_series_id
        st.session_state.saved_datasets_select = active if active in cached else PLACEHOLDER_SAVED_DATASET

    if "cached_series_dropdown_index" not in st.session_state:
        cached = data_loader.list_cached_series_ids()
        active = st.session_state.active_series_id
        st.session_state.cached_series_dropdown_index = (cached.index(active) + 1) if active in cached else 0

    if "active_view" not in st.session_state:
        st.session_state.active_view = VIEW_EXPLORER

    if "pending_view" not in st.session_state:
        st.session_state.pending_view = None

    if "time_horizon" not in st.session_state:
        st.session_state.time_horizon = "10Y"

    if "series_search_filter" not in st.session_state:
        st.session_state.series_search_filter = ""


def select_series(series_id: str, switch_to_visualizer: bool = True, resolve_category: bool = False):
    """
    Central helper to update active series and active view.
    Does NOT modify widget-bound keys (e.g. saved_datasets_select) directly
    to strictly comply with Streamlit's widget lifecycle and avoid
    StreamlitWidgetAlreadyInstantiatedError. Widget synchronization is handled
    cleanly before widget instantiation in main().
    """
    series_id = series_id.strip().upper()
    st.session_state.active_series_id = series_id

    # Switch active view if requested via pending_view so segmented_control syncs cleanly
    if switch_to_visualizer:
        st.session_state.active_view = VIEW_VISUALIZER
        st.session_state.pending_view = VIEW_VISUALIZER

    # Optionally resolve category hierarchy bottom-up
    if resolve_category:
        cat_id, _ = category_manager.resolve_series_bottom_up(series_id)
        if cat_id is not None and cat_id != st.session_state.current_category_id:
            st.session_state.history_stack.append(st.session_state.current_category_id)
            st.session_state.forward_stack = []
            st.session_state.current_category_id = cat_id


def on_dropdown_select():
    """Callback fired ONLY when user interacts directly with the saved datasets selectbox."""
    chosen = st.session_state.saved_datasets_select
    if chosen and chosen != PLACEHOLDER_SAVED_DATASET:
        select_series(chosen, switch_to_visualizer=True, resolve_category=True)


def navigate_to_category(new_cat_id: int):
    """Navigates to a new category, updating the history stack and clearing forward stack."""
    if new_cat_id != st.session_state.current_category_id:
        st.session_state.history_stack.append(st.session_state.current_category_id)
        st.session_state.forward_stack = []
        st.session_state.current_category_id = new_cat_id
        st.session_state.series_search_filter = ""
        st.rerun()


def navigate_back():
    """Pops the previous category from history stack and pushes current to forward stack."""
    if st.session_state.history_stack:
        prev_id = st.session_state.history_stack.pop()
        st.session_state.forward_stack.append(st.session_state.current_category_id)
        st.session_state.current_category_id = prev_id
        st.session_state.series_search_filter = ""
        st.rerun()


def navigate_forward():
    """Pops the next category from forward stack and pushes current to history stack."""
    if st.session_state.forward_stack:
        next_id = st.session_state.forward_stack.pop()
        st.session_state.history_stack.append(st.session_state.current_category_id)
        st.session_state.current_category_id = next_id
        st.session_state.series_search_filter = ""
        st.rerun()


# ---------------------------------------------------------------------------
# Main Application
# ---------------------------------------------------------------------------
def main():
    init_session_state()

    # --- SIDEBAR CONTROLS ---
    with st.sidebar:
        st.title("FRED Navigator")
        st.caption("Federal Reserve Economic Data bidirectional explorer")

        st.markdown("---")
        st.subheader("🔎 Direct Series Search")
        st.write("Resolve series upward to its parent category in the FRED graph.")

        search_input = st.text_input(
            "Enter Series ID",
            placeholder="e.g. GDP, UNRATE, CPIAUCSL",
            key="direct_series_input"
        ).strip().upper()

        col_search_btn, col_search_clear = st.columns([2, 1])
        with col_search_btn:
            resolve_btn = st.button("Explore Series", width="stretch", type="primary")

        if resolve_btn and search_input:
            with st.spinner(f"Resolving '{search_input}' in category graph..."):
                try:
                    resolved_cat_id, crumbs = category_manager.resolve_series_bottom_up(search_input)
                    if resolved_cat_id is not None:
                        select_series(search_input, switch_to_visualizer=True, resolve_category=True)
                        st.rerun()
                    else:
                        select_series(search_input, switch_to_visualizer=True, resolve_category=False)
                        st.warning(f"Could not map '{search_input}' to a category, but loaded as active series.")
                        st.rerun()
                except Exception as e:
                    st.error(f"Error resolving series: {e}")

        st.markdown("---")
        st.subheader("📁 Saved Datasets")
        cached_series_list = data_loader.list_cached_series_ids()
        dropdown_options = [PLACEHOLDER_SAVED_DATASET] + cached_series_list

        # Ensure session state for dropdown index is valid
        active_series = st.session_state.active_series_id
        if active_series in cached_series_list:
            expected_index = cached_series_list.index(active_series) + 1
            st.session_state.saved_datasets_select = active_series
        else:
            expected_index = 0
            st.session_state.saved_datasets_select = PLACEHOLDER_SAVED_DATASET

        st.session_state.cached_series_dropdown_index = expected_index

        st.selectbox(
            "Load from Local Cache",
            options=dropdown_options,
            index=st.session_state.cached_series_dropdown_index,
            key="saved_datasets_select",
            on_change=on_dropdown_select
        )

        st.markdown("---")
        st.subheader("📊 Graph & Storage Stats")
        stats = category_manager.get_cache_stats()
        c1, c2 = st.columns(2)
        with c1:
            st.metric("Graph Nodes", stats.get("total_categories", 0))
        with c2:
            st.metric("Saved Datasets", len(cached_series_list))

        st.caption("Cache file: `fred_cache.json` | Data dir: `data/`")

        if st.button("🔄 Refresh Current Category", width="stretch"):
            category_manager.get_category_node(st.session_state.current_category_id, refresh=True)
            st.toast("Refreshed category cache from FRED API!", icon="✅")
            st.rerun()

    # --- TOP HEADER & BROWSER NAVIGATION ---
    st.title("FRED Category Explorer & Series Visualizer")

    # Navigation bar with Back, Forward, Root, and Breadcrumbs
    nav_col1, nav_col2, nav_col3, nav_col4 = st.columns([1, 1, 1.4, 7])

    with nav_col1:
        can_back = len(st.session_state.history_stack) > 0
        if st.button("⬅️ Back", disabled=not can_back, width="stretch"):
            navigate_back()

    with nav_col2:
        can_forward = len(st.session_state.forward_stack) > 0
        if st.button("➡️ Forward", disabled=not can_forward, width="stretch"):
            navigate_forward()

    with nav_col3:
        is_at_root = st.session_state.current_category_id == 0
        if st.button("🏠 Root Categories", disabled=is_at_root, width="stretch"):
            navigate_to_category(0)

    # Clickable Breadcrumbs
    with nav_col4:
        breadcrumbs = category_manager.get_breadcrumbs(st.session_state.current_category_id)
        # Render breadcrumbs as a series of compact buttons
        crumb_cols = st.columns(len(breadcrumbs))
        for idx, crumb in enumerate(breadcrumbs):
            with crumb_cols[idx]:
                is_current = (crumb["id"] == st.session_state.current_category_id)
                label = f"📍 {crumb['name']}" if is_current else f"{crumb['name']} ➔"
                if st.button(label, key=f"crumb_{crumb['id']}_{idx}", disabled=is_current, width="stretch"):
                    navigate_to_category(crumb["id"])

    st.markdown("---")

    # --- VIEW MODE SELECTOR ---
    view_col1, view_col2 = st.columns([3, 7])
    with view_col1:
        # Synchronize view_selector widget state from pending_view before widget instantiation
        if "pending_view" in st.session_state and st.session_state.pending_view is not None:
            st.session_state.active_view = st.session_state.pending_view
            st.session_state.view_selector = st.session_state.pending_view
            st.session_state.pending_view = None
        elif "view_selector" not in st.session_state:
            st.session_state.view_selector = st.session_state.active_view

        view_selection = st.segmented_control(
            "View Mode",
            options=[VIEW_EXPLORER, VIEW_VISUALIZER],
            default=st.session_state.view_selector,
            key="view_selector"
        )
        if view_selection and view_selection != st.session_state.active_view:
            st.session_state.active_view = view_selection
            st.rerun()

    with view_col2:
        curr_active = st.session_state.active_series_id
        is_cached_marker = "⚡ Cached" if data_loader.is_series_cached(curr_active) else "☁️ Remote"
        st.markdown(
            f"<div style='text-align: right; padding-top: 6px; color: #94a3b8;'>"
            f"Active Series: <strong style='color:#38bdf8;'>{curr_active}</strong> &nbsp; "
            f"<span style='font-size: 0.8rem; background: rgba(56, 189, 248, 0.15); padding: 3px 8px; border-radius: 6px;'>{is_cached_marker}</span>"
            f"</div>",
            unsafe_allow_html=True
        )

    st.markdown("")

    # -----------------------------------------------------------------------
    # VIEW 1: Category Explorer & Series Browser
    # -----------------------------------------------------------------------
    if st.session_state.active_view == VIEW_EXPLORER:
        curr_id = st.session_state.current_category_id
        with st.spinner("Loading category details..."):
            cat_node = category_manager.get_category_node(curr_id)

        if not cat_node:
            st.error(f"Could not load category information for ID `{curr_id}`. Please check network connection.")
            return

        cat_name = cat_node.get("name", "Categories")
        children_ids = cat_node.get("children_ids") or []
        series_items = cat_node.get("series") or []

        st.subheader(f"Current Category: **{cat_name}** `(ID: {curr_id})`")

        # Section 1: Subcategories (Category Tiles)
        st.markdown("##### Subcategories")
        if children_ids:
            children_categories = category_manager.get_child_categories(curr_id)
            # Display tiles in grid of 3 columns
            cols_per_row = 3
            for i in range(0, len(children_categories), cols_per_row):
                row_items = children_categories[i:i + cols_per_row]
                cols = st.columns(cols_per_row)
                for j, child in enumerate(row_items):
                    with cols[j]:
                        tile_label = f"📁 {child['name']}"
                        if st.button(tile_label, key=f"cat_tile_{child['id']}", width="stretch"):
                            navigate_to_category(child["id"])
        else:
            st.info("🍃 **Leaf Category:** No subcategories under this section. Explore the economic series below.")

        st.markdown("---")

        # Section 2: Series in this Category
        st.markdown(f"##### Available Series in '{cat_name}' ({len(series_items)} found)")

        if series_items:
            # Filter bar for series
            search_query = st.text_input(
                "Filter series in this category",
                placeholder="Search by title or series ID (e.g. CPI, Percent, Monthly)...",
                key="series_filter_input"
            ).strip().lower()

            filtered_series = [
                s for s in series_items
                if search_query in s["id"].lower() or search_query in s["title"].lower()
            ] if search_query else series_items

            st.caption(f"Showing {min(len(filtered_series), 50)} of {len(filtered_series)} matching series")

            # Series Table / Selection list
            displayed_items = filtered_series[:50]

            for s in displayed_items:
                s_id = s["id"]
                s_title = s["title"]
                is_cached = data_loader.is_series_cached(s_id)
                is_active = (s_id == st.session_state.active_series_id)

                row_col1, row_col2, row_col3 = st.columns([1.5, 6, 2])
                with row_col1:
                    badge = "⚡ Cached" if is_cached else "☁️ Remote"
                    active_marker = "👉 " if is_active else ""
                    st.markdown(f"**{active_marker}`{s_id}`** &nbsp; `{badge}`")
                with row_col2:
                    st.write(s_title)
                with row_col3:
                    btn_text = "📊 View Active Chart" if is_active else "📈 View Chart"
                    if st.button(
                        btn_text,
                        key=f"view_series_{s_id}",
                        type="primary" if is_active else "secondary",
                        width="stretch"
                    ):
                        select_series(s_id, switch_to_visualizer=True)
                        st.rerun()
                st.markdown("<hr style='margin: 4px 0; border: none; border-bottom: 1px solid rgba(255,255,255,0.06);'>", unsafe_allow_html=True)

            if len(filtered_series) > 50:
                st.info(f"Showing first 50 of {len(filtered_series)} series. Use the filter bar to refine your search.")
        else:
            if curr_id == 0:
                st.write("Root category contains top-level sectors. Click a subcategory tile above to explore series.")
            else:
                st.write("No series directly associated with this category. Please check its subcategories.")

    # -----------------------------------------------------------------------
    # VIEW 2: Series Visualization & Analysis
    # -----------------------------------------------------------------------
    elif st.session_state.active_view == VIEW_VISUALIZER:
        active_id = st.session_state.active_series_id
        if not active_id:
            st.info("No series currently selected. Select one from the Explorer or Sidebar.")
            return

        with st.spinner(f"Loading observations for `{active_id}`..."):
            df = data_loader.get_or_fetch_series_data(active_id)

        if df is None or df.empty:
            st.warning(f"No observation data found for `{active_id}`. Please verify your series ID or FRED API key.")
            return

        is_cached_now = data_loader.is_series_cached(active_id)
        cache_badge = "⚡ Stored Locally" if is_cached_now else "☁️ Fetched from FRED"

        header_col, action_col, horizon_col = st.columns([5, 2, 3])
        with header_col:
            st.subheader(f"Active Series: `{active_id}`")
            st.caption(f"Status: **{cache_badge}** | Total Observations: **{len(df):,}**")

        with action_col:
            if st.button("📂 Back to Explorer", width="stretch"):
                st.session_state.pending_view = VIEW_EXPLORER
                st.session_state.active_view = VIEW_EXPLORER
                st.rerun()

        with horizon_col:
            time_frame = st.segmented_control(
                "Time Horizon",
                options=["1Y", "5Y", "10Y", "Max"],
                default=st.session_state.time_horizon,
                key="horizon_selector"
            )
            if time_frame:
                st.session_state.time_horizon = time_frame

        # Filter by horizon
        max_date = df["date"].max()
        if time_frame == "1Y":
            start_date = max_date - pd.DateOffset(years=1)
        elif time_frame == "5Y":
            start_date = max_date - pd.DateOffset(years=5)
        elif time_frame == "10Y":
            start_date = max_date - pd.DateOffset(years=10)
        else:
            start_date = df["date"].min()

        filtered_df = df[df["date"] >= start_date].copy()

        # Summary Metrics
        if not filtered_df.empty:
            latest_row = filtered_df.iloc[-1]
            first_row = filtered_df.iloc[0]
            latest_val = latest_row["value"]
            latest_date_str = latest_row["date"].strftime("%b %d, %Y")

            diff_val = latest_val - first_row["value"]
            pct_val = (diff_val / first_row["value"] * 100) if first_row["value"] != 0 else 0
            min_val = filtered_df["value"].min()
            max_val = filtered_df["value"].max()

            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.metric("Latest Observation", f"{latest_val:,.2f}", delta=f"{latest_date_str}", delta_color="off")
            with m2:
                st.metric(f"Change ({time_frame})", f"{diff_val:+,.2f}", delta=f"{pct_val:+.2f}%")
            with m3:
                st.metric(f"Period High", f"{max_val:,.2f}")
            with m4:
                st.metric(f"Period Low", f"{min_val:,.2f}")

        # Plotly Express Visualization
        fig = px.line(
            filtered_df,
            x="date",
            y="value",
            title=f"{active_id} Historical Trajectory ({time_frame})",
            labels={"date": "Observation Date", "value": "Observation Value"},
            template="plotly_dark"
        )
        fig.update_traces(
            line=dict(color="#38bdf8", width=2.5),
            hovertemplate="<b>Date:</b> %{x|%Y-%m-%d}<br><b>Value:</b> %{y:,.2f}<extra></extra>"
        )
        fig.update_layout(
            hovermode="x unified",
            margin=dict(l=20, r=20, t=50, b=20),
            xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.08)"),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.08)"),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)"
        )

        st.plotly_chart(fig, width="stretch")

        # Raw Data Inspection Expander
        with st.expander("🔍 View Raw Observations & Download"):
            st.dataframe(filtered_df.sort_values("date", ascending=False), width="stretch")
            csv_data = filtered_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label=f"📥 Download {active_id} Data (CSV)",
                data=csv_data,
                file_name=f"{active_id}_{time_frame}.csv",
                mime="text/csv"
            )


if __name__ == "__main__":
    main()
