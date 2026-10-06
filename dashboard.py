import pandas as pd  # type: ignore[import-untyped]
import plotly.express as px  # type: ignore[import-untyped]
import streamlit as st

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
    [data-testid="stMetricValue"] {
        font-size: 1.45rem !important;
        font-weight: 600;
        overflow-wrap: break-word;
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

# ---------------------------------------------------------------------------
# Constants & Enums
# ---------------------------------------------------------------------------
PLACEHOLDER_SAVED_DATASET: str = "-- Select Saved Dataset --"
VIEW_EXPLORER: str = "📂 Category Explorer & Series"
VIEW_VISUALIZER: str = "📈 Series Visualization"

SORT_OPTIONS: dict[str, str] = {
    "Popularity": "popularity",
    "Last Updated": "last_updated",
    "Observation End": "observation_end",
    "Observation Start": "observation_start",
    "Title": "title",
    "Frequency": "frequency",
    "Units": "units",
    "Seasonal Adjustment": "seasonal_adjustment",
}
SORT_LABEL_FROM_KEY: dict[str, str] = {v: k for k, v in SORT_OPTIONS.items()}

SORT_ORDERS: dict[str, str] = {
    "⬇️ Descending": "desc",
    "⬆️ Ascending": "asc",
}
SORT_ORDER_LABEL_FROM_KEY: dict[str, str] = {
    v: k for k, v in SORT_ORDERS.items()}


# ---------------------------------------------------------------------------
# Pagination UI Component
# ---------------------------------------------------------------------------
def render_pagination_bar(
    curr_id: int,
    total_count: int,
    current_page: int,
    total_pages: int,
    start_idx: int,
    end_idx: int,
    location: str = "top"
) -> None:
    """
    Renders an interactive pagination bar with previous, next, and jump-to controls.
    """
    range_str = (
        f"Displaying **{start_idx}–{end_idx}** of **{total_count:,}** datasets"
        if total_count > 0 else "Displaying **0 of 0** datasets"
    )

    col_range, col_prev, col_status, col_next, col_jump = st.columns(
        [3.8, 1.4, 1.8, 1.4, 1.6])

    with col_range:
        st.markdown(
            f"<div style='padding-top: 6px; color: #94a3b8; font-size: 0.92rem;'>{range_str}</div>",
            unsafe_allow_html=True
        )

    with col_prev:
        can_prev = current_page > 1
        if st.button("⬅️ Prev", key=f"btn_prev_{location}_{curr_id}", disabled=not can_prev, width="stretch"):
            st.session_state.category_page = current_page - 1
            st.rerun()

    with col_status:
        st.markdown(
            f"<div style='text-align: center; padding-top: 6px; font-weight: 600; color: #e2e8f0; font-size: 0.9rem;'>"
            f"Page {current_page} of {total_pages}</div>",
            unsafe_allow_html=True
        )

    with col_next:
        can_next = current_page < total_pages
        if st.button("Next ➡️", key=f"btn_next_{location}_{curr_id}", disabled=not can_next, width="stretch"):
            st.session_state.category_page = current_page + 1
            st.rerun()

    with col_jump:
        if total_pages > 1:
            jump_options = list(range(1, total_pages + 1))
            current_jump_idx = current_page - 1 if current_page <= total_pages else 0
            selected_page = st.selectbox(
                "Jump to page",
                options=jump_options,
                index=current_jump_idx,
                key=f"jump_{location}_{curr_id}_{current_page}",
                label_visibility="collapsed"
            )
            if selected_page != current_page:
                st.session_state.category_page = selected_page
                st.rerun()


# ---------------------------------------------------------------------------
# State Management & Navigation Functions
# ---------------------------------------------------------------------------
def init_session_state() -> None:
    """Initializes Streamlit session state variables with sensible defaults."""
    cached = data_loader.list_cached_series_ids()

    if "current_category_id" not in st.session_state:
        st.session_state.current_category_id = 0  # Start at Root (0)

    if "history_stack" not in st.session_state:
        st.session_state.history_stack = []

    if "forward_stack" not in st.session_state:
        st.session_state.forward_stack = []

    if "active_series_id" not in st.session_state:
        st.session_state.active_series_id = "CPIAUCSL" if "CPIAUCSL" in cached else (
            cached[0] if cached else "CPIAUCSL")

    if "saved_datasets_select" not in st.session_state:
        active = st.session_state.active_series_id
        st.session_state.saved_datasets_select = active if active in cached else PLACEHOLDER_SAVED_DATASET

    if "active_view" not in st.session_state:
        st.session_state.active_view = VIEW_EXPLORER

    if "pending_view" not in st.session_state:
        st.session_state.pending_view = None

    if "time_horizon" not in st.session_state:
        st.session_state.time_horizon = "10Y"

    if "series_search_filter" not in st.session_state:
        st.session_state.series_search_filter = ""

    if "category_sort_by" not in st.session_state:
        st.session_state.category_sort_by = "popularity"

    if "category_sort_order" not in st.session_state:
        st.session_state.category_sort_order = "desc"

    if "category_page" not in st.session_state:
        st.session_state.category_page = 1

    if "last_filter_query" not in st.session_state:
        st.session_state.last_filter_query = ""


def select_series(series_id: str, switch_to_visualizer: bool = True, resolve_category: bool = False) -> None:
    """
    Central helper to update active series and active view.
    Does NOT modify widget-bound keys directly to strictly comply with
    Streamlit's widget lifecycle and avoid StreamlitWidgetAlreadyInstantiatedError.
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
            st.session_state.history_stack.append(
                st.session_state.current_category_id)
            st.session_state.forward_stack = []
            st.session_state.current_category_id = cat_id


def on_dropdown_select() -> None:
    """Callback fired ONLY when user interacts directly with the saved datasets selectbox."""
    chosen = st.session_state.saved_datasets_select
    if chosen and chosen != PLACEHOLDER_SAVED_DATASET:
        select_series(chosen, switch_to_visualizer=True, resolve_category=True)


def navigate_to_category(new_cat_id: int) -> None:
    """Navigates to a new category, updating the history stack and clearing forward stack."""
    if new_cat_id != st.session_state.current_category_id:
        st.session_state.history_stack.append(
            st.session_state.current_category_id)
        st.session_state.forward_stack = []
        st.session_state.current_category_id = new_cat_id
        st.session_state.series_search_filter = ""
        st.rerun()


def navigate_back() -> None:
    """Pops the previous category from history stack and pushes current to forward stack."""
    if st.session_state.history_stack:
        prev_id = st.session_state.history_stack.pop()
        st.session_state.forward_stack.append(
            st.session_state.current_category_id)
        st.session_state.current_category_id = prev_id
        st.session_state.series_search_filter = ""
        st.rerun()


def navigate_forward() -> None:
    """Pops the next category from forward stack and pushes current to history stack."""
    if st.session_state.forward_stack:
        next_id = st.session_state.forward_stack.pop()
        st.session_state.history_stack.append(
            st.session_state.current_category_id)
        st.session_state.current_category_id = next_id
        st.session_state.series_search_filter = ""
        st.rerun()


# ---------------------------------------------------------------------------
# Component: Sidebar
# ---------------------------------------------------------------------------
def render_sidebar() -> None:
    """Renders all controls in the sidebar: search, saved datasets, stats, and refresh."""
    with st.sidebar:
        st.title("FRED Navigator")
        st.caption("Federal Reserve Economic Data bidirectional explorer")

        st.markdown("---")
        _render_sidebar_direct_search()

        st.markdown("---")
        _render_sidebar_saved_datasets()

        st.markdown("---")
        _render_sidebar_storage_stats()


def _render_sidebar_direct_search() -> None:
    """Renders the direct series search input and bottom-up resolution button in the sidebar."""
    st.subheader("🔎 Direct Series Search")
    st.write("Resolve series upward to its parent category in the FRED graph.")

    search_input = st.text_input(
        "Enter Series ID",
        placeholder="e.g. GDP, UNRATE, CPIAUCSL",
        key="direct_series_input"
    ).strip().upper()

    col_search_btn, _ = st.columns([2, 1])
    with col_search_btn:
        resolve_btn = st.button(
            "Explore Series", width="stretch", type="primary")

    if resolve_btn and search_input:
        with st.spinner(f"Resolving '{search_input}' in category graph..."):
            try:
                resolved_cat_id, _ = category_manager.resolve_series_bottom_up(
                    search_input)
                if resolved_cat_id is not None:
                    select_series(
                        search_input, switch_to_visualizer=True, resolve_category=True)
                    st.rerun()
                else:
                    select_series(
                        search_input, switch_to_visualizer=True, resolve_category=False)
                    st.warning(
                        f"Could not map '{search_input}' to a category, but loaded as active series.")
                    st.rerun()
            except Exception as e:
                st.error(f"Error resolving series: {e}")


def _render_sidebar_saved_datasets() -> None:
    """Renders the dropdown selector of locally cached datasets in the sidebar."""
    st.subheader("📁 Saved Datasets")
    cached_series_list = data_loader.list_cached_series_ids()
    dropdown_options = [PLACEHOLDER_SAVED_DATASET] + cached_series_list

    # Ensure session state for saved_datasets_select is valid
    active_series = st.session_state.active_series_id
    if active_series in cached_series_list:
        expected_val = active_series
    else:
        expected_val = PLACEHOLDER_SAVED_DATASET
    if st.session_state.get("saved_datasets_select") != expected_val:
        st.session_state.saved_datasets_select = expected_val

    st.selectbox(
        "Load from Local Cache",
        options=dropdown_options,
        key="saved_datasets_select",
        on_change=on_dropdown_select
    )


def _render_sidebar_storage_stats() -> None:
    """Renders the cache statistics metrics and category refresh trigger in the sidebar."""
    st.subheader("📊 Graph & Storage Stats")
    stats = category_manager.get_cache_stats()
    cached_series_list = data_loader.list_cached_series_ids()

    c1, c2 = st.columns(2)
    with c1:
        st.metric("Graph Nodes", stats.get("total_categories", 0))
    with c2:
        st.metric("Saved Datasets", len(cached_series_list))

    st.caption("Cache file: `fred_cache.json` | Data dir: `data/`")

    if st.button("🔄 Refresh Current Category", width="stretch"):
        category_manager.get_category_node(
            st.session_state.current_category_id, refresh=True)
        st.toast("Refreshed category cache from FRED API!", icon="✅")
        st.rerun()


# ---------------------------------------------------------------------------
# Component: Header & Browser Navigation
# ---------------------------------------------------------------------------
def render_navigation_header() -> None:
    """Renders top header, navigation history controls, and clickable breadcrumbs."""
    st.title("FRED Category Explorer & Series Visualizer")

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

    with nav_col4:
        _render_breadcrumbs(st.session_state.current_category_id)

    st.markdown("---")


def _render_breadcrumbs(category_id: int) -> None:
    """Renders horizontal clickable breadcrumbs for category ancestry."""
    breadcrumbs = category_manager.get_breadcrumbs(category_id)
    crumb_cols = st.columns(len(breadcrumbs))
    for idx, crumb in enumerate(breadcrumbs):
        with crumb_cols[idx]:
            is_current = (crumb["id"] == category_id)
            label = f"📍 {crumb['name']}" if is_current else f"{crumb['name']} ➔"
            if st.button(label, key=f"crumb_{crumb['id']}_{idx}", disabled=is_current, width="stretch"):
                navigate_to_category(crumb["id"])


# ---------------------------------------------------------------------------
# Component: View Mode Bar & Active Series Status
# ---------------------------------------------------------------------------
def render_view_mode_bar() -> None:
    """Renders the view mode segmented control and active series status indicator."""
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
            key="view_selector"
        )
        if view_selection and view_selection != st.session_state.active_view:
            st.session_state.active_view = view_selection
            st.rerun()

    with view_col2:
        curr_active = st.session_state.active_series_id
        is_cached_marker = "⚡ Cached" if data_loader.is_series_cached(
            curr_active) else "☁️ Remote"
        fred_url = f"https://fred.stlouisfed.org/series/{curr_active}"
        st.markdown(
            f"<div style='text-align: right; padding-top: 6px; color: #94a3b8; display: flex; align-items: center; justify-content: flex-end; gap: 8px; flex-wrap: wrap;'>"
            f"<span>Active Series: <strong style='color:#38bdf8;'>{curr_active}</strong></span>"
            f"<span style='font-size: 0.8rem; background: rgba(56, 189, 248, 0.15); padding: 3px 8px; border-radius: 6px;'>{is_cached_marker}</span>"
            f"<a href='{fred_url}' target='_blank' rel='noopener noreferrer' style='color: #38bdf8; text-decoration: none; font-size: 0.82rem; font-weight: 500; background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.3); padding: 3px 8px; border-radius: 6px; display: inline-flex; align-items: center; gap: 4px;' title='View {curr_active} on official FRED website'>"
            f"↗ View on FRED</a>"
            f"</div>",
            unsafe_allow_html=True
        )

    st.markdown("")


# ---------------------------------------------------------------------------
# Component: View 1 - Category Explorer & Series Browser
# ---------------------------------------------------------------------------
def render_category_explorer_view() -> None:
    """Renders the category hierarchy, subcategory tiles, search filters, and series list."""
    curr_id = st.session_state.current_category_id
    with st.spinner("Loading category details..."):
        cat_node = category_manager.get_category_node(curr_id)

    if not cat_node:
        st.error(
            f"Could not load category information for ID `{curr_id}`. Please check network connection.")
        return

    cat_name = cat_node.get("name", "Categories")
    children_ids = cat_node.get("children_ids") or []

    st.subheader(f"Current Category: **{cat_name}** `(ID: {curr_id})`")

    # Section 1: Subcategories
    _render_subcategories_section(curr_id, children_ids)

    st.markdown("---")

    # Section 2: Available Series
    _render_category_series_section(curr_id, cat_name)


def _render_subcategories_section(curr_id: int, children_ids: list[int]) -> None:
    """Renders subcategory buttons organized into a 3-column responsive tile grid."""
    st.markdown("##### Subcategories")
    if children_ids:
        children_categories = category_manager.get_child_categories(curr_id)
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
        st.info(
            "🍃 **Leaf Category:** No subcategories under this section. Explore the economic series below.")


def _render_category_series_section(curr_id: int, cat_name: str) -> None:
    """Renders filtering, sorting, pagination, and dataset items for the current category."""
    if curr_id == 0:
        st.markdown("---")
        st.info("💡 **Root Categories:** Select a top-level category tile above to browse economic series and datasets.")
        return

    st.markdown("---")
    st.markdown(f"##### Available Series in '{cat_name}'")

    # Filter & Sort controls
    filter_col, sort_by_col, sort_dir_col = st.columns([4.5, 3.2, 2.3])

    with filter_col:
        search_query = st.text_input(
            "Filter series in this category",
            placeholder="Search by title or series ID (e.g. CPI, Percent, Monthly)...",
            key="series_filter_input"
        ).strip()

    with sort_by_col:
        current_sort_label = SORT_LABEL_FROM_KEY.get(
            st.session_state.category_sort_by, "Popularity")
        sort_options_keys = list(SORT_OPTIONS.keys())
        chosen_sort_label = st.selectbox(
            "Sort Attribute",
            options=sort_options_keys,
            index=sort_options_keys.index(current_sort_label),
            key=f"sort_by_select_{curr_id}"
        )
        chosen_sort_by = SORT_OPTIONS[chosen_sort_label]

    with sort_dir_col:
        current_dir_label = SORT_ORDER_LABEL_FROM_KEY.get(
            st.session_state.category_sort_order, "⬇️ Descending")
        dir_options_keys = list(SORT_ORDERS.keys())
        chosen_dir_label = st.selectbox(
            "Order",
            options=dir_options_keys,
            index=dir_options_keys.index(current_dir_label),
            key=f"sort_dir_select_{curr_id}"
        )
        chosen_sort_order = SORT_ORDERS[chosen_dir_label]

    # Reset page on sort or filter change
    if chosen_sort_by != st.session_state.category_sort_by or chosen_sort_order != st.session_state.category_sort_order:
        st.session_state.category_sort_by = chosen_sort_by
        st.session_state.category_sort_order = chosen_sort_order
        st.session_state.category_page = 1
        st.rerun()

    if search_query != st.session_state.last_filter_query:
        st.session_state.last_filter_query = search_query
        st.session_state.category_page = 1
        st.rerun()

    with st.spinner("Fetching datasets from FRED..."):
        page_data = category_manager.get_category_series_paginated(
            category_id=curr_id,
            page=st.session_state.category_page,
            page_size=50,
            order_by=st.session_state.category_sort_by,
            sort_order=st.session_state.category_sort_order,
            filter_text=search_query
        )

    total_count = page_data["total_count"]
    current_page = page_data["page"]
    total_pages = page_data["total_pages"]
    start_idx = page_data["start_index"]
    end_idx = page_data["end_index"]
    series_items = page_data["series"]
    is_fallback = page_data.get("is_fallback", False)

    st.session_state.category_page = current_page

    if is_fallback:
        st.info("ℹ️ Displaying locally cached series data.")

    if total_count > 0:
        render_pagination_bar(curr_id, total_count, current_page,
                              total_pages, start_idx, end_idx, location="top")
        st.markdown("<div style='margin-bottom: 12px;'></div>",
                    unsafe_allow_html=True)

        for s in series_items:
            _render_series_item_row(s, current_page)

        if total_pages > 1:
            st.markdown("<div style='margin-top: 14px;'></div>",
                        unsafe_allow_html=True)
            render_pagination_bar(curr_id, total_count, current_page,
                                  total_pages, start_idx, end_idx, location="bottom")
    else:
        if search_query:
            st.warning(
                f"No series matching '{search_query}' found in this category.")
        else:
            st.info(
                "No series directly associated with this category. Please check its subcategories.")


def _render_series_item_row(s: dict, current_page: int) -> None:
    """Renders a single series record row with metadata pills, chart trigger, and FRED link."""
    s_id = s["id"]
    s_title = s["title"]
    is_cached = data_loader.is_series_cached(s_id)
    is_active = (s_id == st.session_state.active_series_id)

    row_col1, row_col2, row_col3 = st.columns([1.8, 6.2, 2.0])
    with row_col1:
        badge = "⚡ Cached" if is_cached else "☁️ Remote"
        active_marker = "👉 " if is_active else ""
        st.markdown(f"**{active_marker}`{s_id}`** &nbsp; `{badge}`")
        pop_val = s.get("popularity")
        if pop_val is not None:
            st.caption(f"🔥 Popularity: **{pop_val}**")

    with row_col2:
        st.markdown(
            f"<div style='font-size: 1rem; font-weight: 500; color: #f8fafc;'>{s_title}</div>", unsafe_allow_html=True)
        meta_parts = []
        if s.get("units"):
            meta_parts.append(f"Units: {s['units']}")
        if s.get("frequency"):
            meta_parts.append(f"Freq: {s['frequency']}")
        if s.get("seasonal_adjustment"):
            meta_parts.append(f"Adj: {s['seasonal_adjustment']}")
        if s.get("last_updated"):
            updated_date = str(s["last_updated"]).split(" ")[0]
            meta_parts.append(f"Updated: {updated_date}")
        if s.get("observation_start") and s.get("observation_end"):
            meta_parts.append(
                f"Span: {s['observation_start']} to {s['observation_end']}")
        if meta_parts:
            st.markdown(
                f"<div style='font-size: 0.8rem; color: #94a3b8; margin-top: 3px;'>{' &bull; '.join(meta_parts)}</div>", unsafe_allow_html=True)

    with row_col3:
        btn_text = "📊 View Active Chart" if is_active else "📈 View Chart"
        if st.button(
            btn_text,
            key=f"view_series_{s_id}_{current_page}",
            type="primary" if is_active else "secondary",
            width="stretch"
        ):
            select_series(s_id, switch_to_visualizer=True)
            st.rerun()

        s_fred_url = f"https://fred.stlouisfed.org/series/{s_id}"
        st.markdown(
            f"<div style='text-align: center; margin-top: 3px;'>"
            f"<a href='{s_fred_url}' target='_blank' rel='noopener noreferrer' style='color: #38bdf8; font-size: 0.8rem; text-decoration: none;' title='Open {s_id} on official FRED website'>"
            f"View on FRED ↗</a></div>",
            unsafe_allow_html=True
        )

    st.markdown("<hr style='margin: 6px 0; border: none; border-bottom: 1px solid rgba(255,255,255,0.06);'>",
                unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Component: View 2 - Series Visualization & Analysis
# ---------------------------------------------------------------------------
def render_series_visualizer_view() -> None:
    """Renders time series observations, interactive chart, metrics, notes, and raw export."""
    active_id = st.session_state.active_series_id
    if not active_id:
        st.info(
            "No series currently selected. Select one from the Explorer or Sidebar.")
        return

    with st.spinner(f"Loading observations for `{active_id}`..."):
        df = data_loader.get_or_fetch_series_data(active_id)

    if df is None or df.empty:
        st.warning(
            f"No observation data found for `{active_id}`. Please verify your series ID or FRED API key.")
        return

    is_cached_now = data_loader.is_series_cached(active_id)
    cache_badge = "⚡ Stored Locally" if is_cached_now else "☁️ Fetched from FRED"

    # Header & controls
    time_frame = _render_visualizer_controls(active_id, cache_badge, len(df))

    # Date horizon filtering
    filtered_df = _filter_by_time_horizon(df, time_frame)

    # Metadata & Metrics Panel
    meta = data_loader.get_or_fetch_series_metadata(active_id)
    _render_summary_metrics(filtered_df, meta, time_frame)

    # Plotly Line Chart
    _render_timeseries_chart(filtered_df, active_id, time_frame)

    # Notes & Citation Section
    _render_notes_and_citations(meta, active_id)

    # Raw Data Expander & CSV Download
    _render_raw_data_expander(filtered_df, active_id, time_frame)


def _render_visualizer_controls(active_id: str, cache_badge: str, obs_count: int) -> str:
    """Renders the series header, external link, back navigation, and horizon segmented control."""
    header_col, link_col, action_col, horizon_col = st.columns(
        [4.2, 1.8, 1.8, 2.2])

    with header_col:
        st.subheader(f"Active Series: `{active_id}`")
        st.caption(
            f"Status: **{cache_badge}** | Total Observations: **{obs_count:,}**")

    with link_col:
        fred_url = f"https://fred.stlouisfed.org/series/{active_id}"
        st.link_button("↗️ View on FRED", url=fred_url, width="stretch",
                       help=f"Open {active_id} on official FRED website")

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
        else:
            time_frame = st.session_state.time_horizon

    return time_frame


def _filter_by_time_horizon(df: pd.DataFrame, time_frame: str) -> pd.DataFrame:
    """Slices a DataFrame according to the selected time horizon offset."""
    max_date = df["date"].max()
    if time_frame == "1Y":
        start_date = max_date - pd.DateOffset(years=1)
    elif time_frame == "5Y":
        start_date = max_date - pd.DateOffset(years=5)
    elif time_frame == "10Y":
        start_date = max_date - pd.DateOffset(years=10)
    else:
        start_date = df["date"].min()

    return df[df["date"] >= start_date].copy()


def _render_summary_metrics(filtered_df: pd.DataFrame, meta: dict, time_frame: str) -> None:
    """Renders 3-column summary metrics for units, frequency, and date span."""
    units_display = meta.get("units") or meta.get("units_short") or "N/A"
    frequency_display = meta.get("frequency") or meta.get(
        "frequency_short") or "N/A"

    if not filtered_df.empty:
        start_date_actual = filtered_df["date"].min().strftime("%b %d, %Y")
        end_date_actual = filtered_df["date"].max().strftime("%b %d, %Y")
        date_range_label = f"{start_date_actual} to {end_date_actual}"
    else:
        date_range_label = "No observations in range"

    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("Units", units_display)
    with m2:
        st.metric("Frequency", frequency_display)
    with m3:
        st.metric("Time Horizon", time_frame,
                  delta=date_range_label, delta_color="off")


def _render_timeseries_chart(filtered_df: pd.DataFrame, active_id: str, time_frame: str) -> None:
    """Constructs and displays the interactive Plotly Express dark-mode line chart."""
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


def _render_notes_and_citations(meta: dict, active_id: str) -> None:
    """Renders the sanitized notes and suggested citation in a scrollable container."""
    st.markdown("##### 📝 Notes")
    raw_notes = meta.get("notes") if meta else ""
    raw_citation = meta.get("citation") if meta else ""

    clean_notes = data_loader.clean_and_format_notes(
        raw_notes) if raw_notes else ""
    clean_cit = data_loader.clean_citation(
        raw_citation,
        series_id=active_id,
        title=str(meta.get("title") or "") if meta else ""
    )

    has_content = bool(clean_notes or clean_cit)

    if has_content:
        total_chars = len(clean_notes) + len(clean_cit)
        container_args = {"height": 240, "border": True} if total_chars > 300 else {
            "border": True}
        with st.container(**container_args):
            if clean_notes:
                st.markdown(clean_notes)
            if clean_cit:
                if clean_notes:
                    st.divider()
                st.markdown(f"**Suggested Citation:**\n\n{clean_cit}")
    else:
        with st.container(border=True):
            st.caption("No descriptive notes available for this series.")


def _render_raw_data_expander(filtered_df: pd.DataFrame, active_id: str, time_frame: str) -> None:
    """Renders the raw tabular observations expander and CSV download trigger."""
    with st.expander("🔍 View Raw Observations & Download"):
        st.dataframe(filtered_df.sort_values(
            "date", ascending=False), width="stretch")
        csv_data = filtered_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label=f"📥 Download {active_id} Data (CSV)",
            data=csv_data,
            file_name=f"{active_id}_{time_frame}.csv",
            mime="text/csv"
        )


# ---------------------------------------------------------------------------
# Main Application Orchestrator
# ---------------------------------------------------------------------------
def main() -> None:
    """
    High-level application orchestrator coordinating session state bootstrapping,
    layout containers, and view routing between Explorer and Visualizer.
    """
    init_session_state()
    render_sidebar()
    render_navigation_header()
    render_view_mode_bar()

    if st.session_state.active_view == VIEW_EXPLORER:
        render_category_explorer_view()
    elif st.session_state.active_view == VIEW_VISUALIZER:
        render_series_visualizer_view()


if __name__ == "__main__":
    main()
