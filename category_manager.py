from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Any, NotRequired, TypedDict, cast

import data_loader

CACHE_FILE = "fred_cache.json"

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Strict Type Models (TypedDict)
# ---------------------------------------------------------------------------

class SeriesItem(TypedDict):
    id: str
    title: str
    frequency: NotRequired[str | None]
    units: NotRequired[str | None]
    seasonal_adjustment: NotRequired[str | None]
    last_updated: NotRequired[str | None]
    observation_start: NotRequired[str | None]
    observation_end: NotRequired[str | None]
    popularity: NotRequired[int | float | None]


class CategoryNode(TypedDict):
    id: int
    name: str
    parent_id: int | None
    children_ids: list[int] | None
    series: list[SeriesItem] | None
    total_series_count: NotRequired[int]


class Breadcrumb(TypedDict):
    id: int
    name: str


class ChildCategory(TypedDict):
    id: int
    name: str
    parent_id: int | None


class CacheStats(TypedDict):
    total_categories: int
    visited_categories: int
    total_series_indexed: int


class PaginatedSeriesResult(TypedDict):
    total_count: int
    page: int
    page_size: int
    total_pages: int
    start_index: int
    end_index: int
    order_by: str
    sort_order: str
    series: list[SeriesItem]
    is_fallback: bool


# ---------------------------------------------------------------------------
# Internal Helpers (Private)
# ---------------------------------------------------------------------------

def _get_or_create_node(
    cache: dict[str, CategoryNode],
    category_id: int,
    name: str | None = None,
    parent_id: int | None = None
) -> CategoryNode:
    """Retrieves an existing category node or initializes a structured stub node in cache."""
    cat_key = str(category_id)
    if cat_key in cache:
        node = cache[cat_key]
        if name and (not node.get("name") or node.get("name") == f"Category {category_id}"):
            node["name"] = name
        if parent_id is not None and node.get("parent_id") is None and category_id != 0:
            node["parent_id"] = parent_id
        return node

    default_name = name or ("Categories" if category_id == 0 else f"Category {category_id}")
    new_node: CategoryNode = {
        "id": category_id,
        "name": default_name,
        "parent_id": None if category_id == 0 else parent_id,
        "children_ids": None,
        "series": [] if category_id == 0 else None
    }
    cache[cat_key] = new_node
    return new_node


def _merge_series_into_node(node: CategoryNode, new_series: list[SeriesItem]) -> None:
    """Merges new series records into node['series'] by ID without clobbering existing records."""
    existing_map: dict[str, SeriesItem] = {
        str(s["id"]): s for s in (node.get("series") or []) if isinstance(s, dict) and "id" in s
    }
    for s in new_series:
        if isinstance(s, dict) and "id" in s:
            existing_map[str(s["id"])] = s
    node["series"] = list(existing_map.values())


def _sort_series(
    series_list: list[SeriesItem],
    order_by: str = "popularity",
    sort_order: str = "desc"
) -> list[SeriesItem]:
    """Sorts a list of series dictionaries cleanly with graceful fallback for heterogeneous types."""
    valid_order_by = {
        "popularity", "last_updated", "observation_end", "observation_start",
        "title", "frequency", "units", "seasonal_adjustment"
    }
    if order_by not in valid_order_by:
        order_by = "popularity"

    reverse = (sort_order.lower() == "desc")

    def _sort_key(s: SeriesItem) -> Any:
        val = cast(dict[str, Any], s).get(order_by)
        if val is None:
            return "" if order_by in ("title", "units", "frequency", "seasonal_adjustment") else 0
        return val

    try:
        series_list.sort(key=_sort_key, reverse=reverse)
    except TypeError:
        series_list.sort(key=lambda s: str(cast(dict[str, Any], s).get(order_by, "") or ""), reverse=reverse)
    return series_list


def _paginate_series(
    series_list: list[SeriesItem],
    page: int,
    page_size: int,
    total_count: int | None = None,
    order_by: str = "popularity",
    sort_order: str = "desc",
    is_fallback: bool = False
) -> PaginatedSeriesResult:
    """Builds the standardized paginated response envelope for series queries."""
    if total_count is None:
        total_count = len(series_list)
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        clamped_page = max(1, min(page, total_pages))
        start_slice = (clamped_page - 1) * page_size
        end_slice = clamped_page * page_size
        slice_items = series_list[start_slice:end_slice]
    else:
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        clamped_page = page
        slice_items = series_list

    return {
        "total_count": total_count,
        "page": clamped_page,
        "page_size": page_size,
        "total_pages": total_pages,
        "start_index": (clamped_page - 1) * page_size + 1 if total_count > 0 else 0,
        "end_index": min(clamped_page * page_size, total_count),
        "order_by": order_by,
        "sort_order": sort_order,
        "series": slice_items,
        "is_fallback": is_fallback
    }


# ---------------------------------------------------------------------------
# Cache Persistence
# ---------------------------------------------------------------------------

def load_category_cache(cache_path: str = CACHE_FILE) -> dict[str, CategoryNode]:
    """Loads and returns the category cache JSON from disk, or an empty dict on failure."""
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return cast(dict[str, CategoryNode], data)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(
                f"Error loading {cache_path}: {e}. Initializing empty cache.")
    return {}


def save_category_cache(cache: dict[str, CategoryNode], cache_path: str = CACHE_FILE) -> None:
    """Persists category cache to disk atomically using a secure temp file."""
    dir_name = os.path.dirname(cache_path) or "."
    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=dir_name,
            encoding="utf-8",
            delete=False,
            prefix=f"{os.path.basename(cache_path)}.",
            suffix=".tmp"
        ) as f:
            temp_path = f.name
            json.dump(cache, f, indent=2)
        os.replace(temp_path, cache_path)
    except (OSError, TypeError) as e:
        logger.error(f"Error saving {cache_path}: {e}")
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Hierarchy & Graph Management
# ---------------------------------------------------------------------------

def get_category_node(
    category_id: int,
    refresh: bool = False,
    cache_path: str = CACHE_FILE,
    _cache: dict[str, CategoryNode] | None = None
) -> CategoryNode | None:
    """
    Retrieves category details, children, and top series from cache or fetches from FRED API.
    Saves to disk only if modifications were made. Accepts optional in-memory `_cache` to avoid
    redundant disk I/O.
    """
    cache = _cache if _cache is not None else load_category_cache(cache_path)
    cat_key = str(category_id)
    dirty = False

    if cat_key not in cache or refresh:
        if category_id == 0:
            cat_info = data_loader.fetch_category_info(0)
            name = cat_info["name"] if cat_info else "Categories"
            node = _get_or_create_node(cache, 0, name=name, parent_id=None)
            node["parent_id"] = None
            if node.get("series") is None:
                node["series"] = []
            dirty = True
        else:
            cat_info = data_loader.fetch_category_info(category_id)
            if not cat_info:
                return None
            raw_parent = cat_info.get("parent_id")
            parent_id = raw_parent if raw_parent != 0 else None
            node = _get_or_create_node(
                cache, category_id, name=cat_info["name"], parent_id=parent_id)
            node["parent_id"] = parent_id
            dirty = True
    else:
        node = cache[cat_key]

    if node.get("children_ids") is None or refresh:
        children = data_loader.fetch_category_children(category_id)
        if children is not None:
            child_ids: list[int] = []
            for child in children:
                cid = int(child["id"])
                child_ids.append(cid)
                child_node = _get_or_create_node(
                    cache, cid, name=str(child["name"]), parent_id=category_id)
                child_node["parent_id"] = category_id
            node["children_ids"] = child_ids
            dirty = True
        elif node.get("children_ids") is None:
            node["children_ids"] = []
            dirty = True

    if node.get("series") is None or refresh:
        if category_id == 0:
            node["series"] = []
            dirty = True
        else:
            api_res = data_loader.fetch_category_series(category_id, limit=50)
            if api_res is not None:
                series_list = api_res.get("series", []) if isinstance(
                    api_res, dict) else api_res
                node["series"] = [
                    {
                        "id": str(s["id"]),
                        "title": str(s["title"]),
                        "frequency": s.get("frequency"),
                        "units": s.get("units"),
                        "seasonal_adjustment": s.get("seasonal_adjustment"),
                        "last_updated": s.get("last_updated"),
                        "observation_start": s.get("observation_start"),
                        "observation_end": s.get("observation_end"),
                        "popularity": s.get("popularity", 0)
                    }
                    for s in series_list
                ]
                if isinstance(api_res, dict) and "count" in api_res:
                    node["total_series_count"] = int(api_res["count"])
                dirty = True
            elif node.get("series") is None:
                node["series"] = []
                dirty = True

    if dirty:
        save_category_cache(cache, cache_path)
    return node


def resolve_series_bottom_up(
    series_id: str,
    cache_path: str = CACHE_FILE
) -> tuple[int | None, list[Breadcrumb]]:
    """Resolves the category lineage for an arbitrary series ID bottom-up via cache or API."""
    series_id = series_id.strip().upper()
    cache = load_category_cache(cache_path)

    for node in cache.values():
        if isinstance(node, dict) and any(
            s.get("id", "").upper() == series_id for s in (node.get("series") or []) if isinstance(s, dict)
        ):
            cat_id = int(node["id"])
            return cat_id, get_breadcrumbs(cat_id, cache_path, _cache=cache)

    categories = data_loader.fetch_series_categories(series_id)
    if not categories:
        return None, []

    primary_cat = categories[0]
    target_cat_id = int(primary_cat["id"])
    target_name = str(primary_cat["name"])
    target_parent = primary_cat.get("parent_id")
    target_parent_clean = None if target_cat_id == 0 else (
        int(target_parent) if target_parent is not None else None)

    target_node = _get_or_create_node(
        cache, target_cat_id, name=target_name, parent_id=target_parent_clean)
    if target_node.get("series") is None:
        target_node["series"] = []

    if not any(s.get("id", "").upper() == series_id for s in (target_node.get("series") or []) if isinstance(s, dict)):
        stub_series: SeriesItem = {
            "id": series_id,
            "title": series_id,
            "frequency": None,
            "units": None
        }
        if target_node.get("series") is None:
            target_node["series"] = []
        target_series = target_node["series"]
        if target_series is not None:
            target_series.append(stub_series)

    curr_id = target_parent_clean
    visited: set[int] = set()
    while curr_id is not None and curr_id != 0 and curr_id not in visited:
        visited.add(curr_id)
        curr_key = str(curr_id)
        if curr_key in cache:
            parent_raw = cache[curr_key].get("parent_id")
            curr_id = int(parent_raw) if parent_raw is not None else None
        else:
            parent_info = data_loader.fetch_category_info(curr_id)
            if parent_info:
                p_parent = parent_info.get("parent_id")
                clean_parent = None if curr_id == 0 else (
                    int(p_parent) if p_parent is not None else None)
                _get_or_create_node(
                    cache, curr_id, name=str(parent_info["name"]), parent_id=clean_parent)
                curr_id = clean_parent
            else:
                break

    # Ensure root category (0) is present in cache
    root_node = _get_or_create_node(cache, 0, name="Categories", parent_id=None)
    assert root_node is not None

    save_category_cache(cache, cache_path)
    return target_cat_id, get_breadcrumbs(target_cat_id, cache_path, _cache=cache)


def get_breadcrumbs(
    category_id: int,
    cache_path: str = CACHE_FILE,
    _cache: dict[str, CategoryNode] | None = None
) -> list[Breadcrumb]:
    """
    Constructs the breadcrumb lineage list from Root (0) down to the given category.
    Accepts an optional in-memory `_cache` dict to avoid redundant disk I/O.
    """
    cache = _cache if _cache is not None else load_category_cache(cache_path)
    crumbs: list[Breadcrumb] = []
    curr_id: int | None = category_id
    visited: set[int] = set()
    dirty = False

    while curr_id is not None and curr_id not in visited:
        visited.add(curr_id)
        curr_key = str(curr_id)
        if curr_key in cache:
            node = cache[curr_key]
            crumbs.append({"id": node["id"], "name": node["name"]})
            parent_id = node.get("parent_id")
            if curr_id == 0 or parent_id == curr_id or parent_id is None:
                break
            curr_id = int(parent_id)
        else:
            info = data_loader.fetch_category_info(curr_id)
            if info:
                crumbs.append({"id": int(info["id"]), "name": str(info["name"])})
                parent_id = info.get("parent_id")
                clean_parent = None if curr_id == 0 else (
                    int(parent_id) if parent_id is not None else None)
                _get_or_create_node(
                    cache, curr_id, name=str(info["name"]), parent_id=clean_parent)
                dirty = True
                if curr_id == 0 or parent_id == curr_id or parent_id is None:
                    break
                curr_id = clean_parent
            else:
                crumbs.append({"id": curr_id, "name": f"Category {curr_id}"})
                break

    crumbs.reverse()
    if not crumbs or crumbs[0]["id"] != 0:
        root_node = cache.get("0")
        root_name = root_node["name"] if root_node else "Categories"
        crumbs.insert(0, {"id": 0, "name": root_name})

    if dirty:
        save_category_cache(cache, cache_path)

    return crumbs


def get_child_categories(
    category_id: int,
    cache_path: str = CACHE_FILE
) -> list[ChildCategory]:
    """Retrieves immediate subcategory objects with id, name, and parent_id for the given category."""
    cache = load_category_cache(cache_path)
    node = get_category_node(category_id, cache_path=cache_path, _cache=cache)
    if not node:
        return []

    child_ids = node.get("children_ids") or []
    if not child_ids:
        return []

    result: list[ChildCategory] = []
    for cid in child_ids:
        child_node = cache.get(str(cid))
        result.append({
            "id": child_node["id"] if child_node else cid,
            "name": child_node["name"] if child_node else f"Category {cid}",
            "parent_id": child_node.get("parent_id") if child_node else category_id
        })
    return result


def get_cache_stats(cache_path: str = CACHE_FILE) -> CacheStats:
    """Returns high-level graph and category metadata statistics from local cache."""
    cache = load_category_cache(cache_path)
    return {
        "total_categories": len(cache),
        "visited_categories": sum(
            1 for n in cache.values() if isinstance(n, dict) and n.get("children_ids") is not None
        ),
        "total_series_indexed": sum(
            len(n.get("series") or []) for n in cache.values() if isinstance(n, dict)
        )
    }


def get_category_series_paginated(
    category_id: int,
    page: int = 1,
    page_size: int = 50,
    order_by: str = "popularity",
    sort_order: str = "desc",
    filter_text: str = "",
    cache_path: str = CACHE_FILE
) -> PaginatedSeriesResult:
    """
    Returns a paginated slice of series under category_id with support for ordering,
    text filtering, and offline local cache fallback.
    """
    page = max(1, int(page))
    page_size = max(1, int(page_size))
    valid_order_by = {
        "popularity", "last_updated", "observation_end", "observation_start",
        "title", "frequency", "units", "seasonal_adjustment"
    }
    if order_by not in valid_order_by:
        order_by = "popularity"

    sort_order = sort_order.lower() if sort_order in ("asc", "desc") else "desc"

    if category_id == 0:
        return _paginate_series(
            series_list=[],
            page=1,
            page_size=page_size,
            total_count=0,
            order_by=order_by,
            sort_order=sort_order,
            is_fallback=False
        )

    filter_text = (filter_text or "").strip().lower()

    if filter_text:
        cache = load_category_cache(cache_path)
        cat_key = str(category_id)
        node = cache.get(cat_key)

        fetch_res = data_loader.fetch_category_series(
            category_id, limit=1000, offset=0, order_by=order_by, sort_order=sort_order)
        if fetch_res and "series" in fetch_res:
            if not node:
                node = _get_or_create_node(cache, category_id)
            _merge_series_into_node(node, cast(list[SeriesItem], fetch_res["series"]))
            node["total_series_count"] = int(fetch_res.get("count", len(node["series"] or [])))
            save_category_cache(cache, cache_path)
            is_fallback = False
        else:
            is_fallback = True

        all_series: list[SeriesItem] = list((node.get("series") if node else []) or [])
        filtered = [
            s for s in all_series
            if filter_text in str(s.get("id", "")).lower() or filter_text in str(s.get("title", "")).lower()
        ]
        _sort_series(filtered, order_by=order_by, sort_order=sort_order)
        return _paginate_series(
            series_list=filtered,
            page=page,
            page_size=page_size,
            order_by=order_by,
            sort_order=sort_order,
            is_fallback=is_fallback
        )

    # Empty filter_text: paginated API fetch with local cache update
    offset = (page - 1) * page_size
    api_res = data_loader.fetch_category_series(
        category_id=category_id, limit=page_size, offset=offset, order_by=order_by, sort_order=sort_order)
    cache = load_category_cache(cache_path)
    cat_key = str(category_id)
    node = cache.get(cat_key)

    if api_res is not None:
        total_count = int(api_res.get("count", 0))
        series_items: list[SeriesItem] = list(api_res.get("series", []))
        total_pages = max(1, (total_count + page_size - 1) // page_size)

        if page > total_pages and total_count > 0:
            page = total_pages
            offset = (page - 1) * page_size
            api_res = data_loader.fetch_category_series(
                category_id=category_id, limit=page_size, offset=offset, order_by=order_by, sort_order=sort_order)
            series_items = list(api_res.get("series", [])) if api_res else series_items

        if node is None:
            node = _get_or_create_node(cache, category_id)

        node["total_series_count"] = total_count
        _merge_series_into_node(node, series_items)
        save_category_cache(cache, cache_path)

        return _paginate_series(
            series_list=series_items,
            page=page,
            page_size=page_size,
            total_count=total_count,
            order_by=order_by,
            sort_order=sort_order,
            is_fallback=False
        )

    # Offline fallback path when network/API call fails
    cached_series: list[SeriesItem] = list((node.get("series") if node else []) or [])
    _sort_series(cached_series, order_by=order_by, sort_order=sort_order)
    return _paginate_series(
        series_list=cached_series,
        page=page,
        page_size=page_size,
        order_by=order_by,
        sort_order=sort_order,
        is_fallback=True
    )
