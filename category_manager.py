import json
import os
import data_loader

CACHE_FILE = "fred_cache.json"


def load_category_cache(cache_path: str = CACHE_FILE) -> dict:
    """
    Loads the flat category adjacency graph from fred_cache.json.
    Schema per specification:
    {
        "category_id": {
            "id": int,
            "name": str,
            "parent_id": int | None,
            "children_ids": list[int] | None,  # None if unvisited, [] if leaf
            "series": list[dict] | None        # None if unvisited; list of {"id": str, "title": str}
        }
    }
    """
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            print(f"Error loading {cache_path}: {e}. Initializing empty cache.")
    return {}


def save_category_cache(cache: dict, cache_path: str = CACHE_FILE) -> None:
    """Persists the flat adjacency graph to fred_cache.json."""
    try:
        temp_path = f"{cache_path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
        if os.path.exists(cache_path):
            os.replace(temp_path, cache_path)
        else:
            os.rename(temp_path, cache_path)
    except Exception as e:
        print(f"Error saving {cache_path}: {e}")


def get_category_node(category_id: int, refresh: bool = False, cache_path: str = CACHE_FILE) -> dict | None:
    """
    Implements top-down lazy-loading category exploration.
    - If category_id not in cache, fetches category metadata.
    - If children_ids is None, fetches children from FRED API and adds child nodes.
    - If series is None, fetches series from FRED API.
    - Persists changes to fred_cache.json and returns the node.
    """
    cache = load_category_cache(cache_path)
    cat_key = str(category_id)

    # 1. Ensure the category node itself exists in cache
    if cat_key not in cache or refresh:
        if category_id == 0:
            # Root category
            cat_info = data_loader.fetch_category_info(0)
            name = cat_info["name"] if cat_info else "Categories"
            cache[cat_key] = {
                "id": 0,
                "name": name,
                "parent_id": None,
                "children_ids": None,
                "series": None
            }
        else:
            cat_info = data_loader.fetch_category_info(category_id)
            if not cat_info:
                print(f"Could not fetch metadata for category {category_id}.")
                return None
            parent_id = cat_info.get("parent_id")
            # Root parent is None or 0
            if parent_id == 0 and category_id == 0:
                parent_id = None
            cache[cat_key] = {
                "id": category_id,
                "name": cat_info["name"],
                "parent_id": parent_id,
                "children_ids": None,
                "series": None
            }

    node = cache[cat_key]

    # 2. Lazy-load children if unvisited
    if node.get("children_ids") is None or refresh:
        children = data_loader.fetch_category_children(category_id)
        if children is not None:
            child_ids = []
            for child in children:
                cid = child["id"]
                child_ids.append(cid)
                cid_key = str(cid)
                if cid_key not in cache:
                    cache[cid_key] = {
                        "id": cid,
                        "name": child["name"],
                        "parent_id": category_id,
                        "children_ids": None,
                        "series": None
                    }
                else:
                    cache[cid_key]["parent_id"] = category_id
            node["children_ids"] = child_ids
        else:
            node["children_ids"] = []

    # 3. Lazy-load series if unvisited
    if node.get("series") is None or refresh:
        if category_id == 0:
            # Root category has no series
            node["series"] = []
        else:
            api_res = data_loader.fetch_category_series(category_id, limit=50)
            if api_res is not None:
                series_list = api_res.get("series", []) if isinstance(api_res, dict) else api_res
                cleaned_series = []
                for s in series_list:
                    cleaned_series.append({
                        "id": s["id"],
                        "title": s["title"],
                        "frequency": s.get("frequency"),
                        "units": s.get("units"),
                        "seasonal_adjustment": s.get("seasonal_adjustment"),
                        "last_updated": s.get("last_updated"),
                        "observation_start": s.get("observation_start"),
                        "observation_end": s.get("observation_end"),
                        "popularity": s.get("popularity", 0)
                    })
                node["series"] = cleaned_series
                if isinstance(api_res, dict) and "count" in api_res:
                    node["total_series_count"] = api_res["count"]
            else:
                node["series"] = []

    save_category_cache(cache, cache_path)
    return node


def resolve_series_bottom_up(series_id: str, cache_path: str = CACHE_FILE) -> tuple[int | None, list[dict]]:
    """
    Implements bottom-up resolution:
    Given a series_id, finds its parent category and traces upward to Root (0),
    populating missing ancestors in fred_cache.json.
    Returns: (category_id, breadcrumbs_list)
    """
    series_id = series_id.strip().upper()
    cache = load_category_cache(cache_path)

    # Step 1: Check local cache to see if series is already registered in a category
    for cat_key, node in cache.items():
        series_items = node.get("series")
        if series_items:
            for s in series_items:
                if s.get("id", "").upper() == series_id:
                    cat_id = node["id"]
                    crumbs = get_breadcrumbs(cat_id, cache_path)
                    return cat_id, crumbs

    # Step 2: Fetch category hierarchy for this series from FRED API
    categories = data_loader.fetch_series_categories(series_id)
    if not categories:
        print(f"No categories found for series '{series_id}' via FRED API.")
        return None, []

    primary_cat = categories[0]
    target_cat_id = primary_cat["id"]
    target_name = primary_cat["name"]
    target_parent = primary_cat.get("parent_id")

    # Ensure target category is present in cache
    target_key = str(target_cat_id)
    if target_key not in cache:
        cache[target_key] = {
            "id": target_cat_id,
            "name": target_name,
            "parent_id": None if target_cat_id == 0 else target_parent,
            "children_ids": None,
            "series": None
        }

    # Ensure series_id is registered inside target category series list
    if cache[target_key].get("series") is not None:
        if not any(s["id"].upper() == series_id for s in cache[target_key]["series"]):
            cache[target_key]["series"].append({
                "id": series_id,
                "title": series_id,
                "frequency": None,
                "units": None
            })

    # Step 3: Trace upwards from target_parent to Root (0), populating missing ancestors
    curr_id = target_parent
    visited = set()
    while curr_id is not None and curr_id != 0 and curr_id not in visited:
        visited.add(curr_id)
        curr_key = str(curr_id)
        if curr_key in cache:
            curr_id = cache[curr_key].get("parent_id")
        else:
            parent_info = data_loader.fetch_category_info(curr_id)
            if parent_info:
                p_parent = parent_info.get("parent_id")
                cache[curr_key] = {
                    "id": curr_id,
                    "name": parent_info["name"],
                    "parent_id": None if curr_id == 0 else p_parent,
                    "children_ids": None,
                    "series": None
                }
                curr_id = p_parent
            else:
                break

    # Ensure Root (0) node is registered
    if "0" not in cache:
        cache["0"] = {
            "id": 0,
            "name": "Categories",
            "parent_id": None,
            "children_ids": None,
            "series": []
        }

    save_category_cache(cache, cache_path)
    crumbs = get_breadcrumbs(target_cat_id, cache_path)
    return target_cat_id, crumbs


def get_breadcrumbs(category_id: int, cache_path: str = CACHE_FILE) -> list[dict]:
    """
    Generates lineage breadcrumb data (Root > Parent > Current).
    Returns list of dicts: [{"id": int, "name": str}, ...] from Root (0) to category_id.
    """
    cache = load_category_cache(cache_path)
    crumbs = []
    curr_id = category_id
    visited = set()

    while curr_id is not None and curr_id not in visited:
        visited.add(curr_id)
        curr_key = str(curr_id)
        if curr_key in cache:
            node = cache[curr_key]
            crumbs.append({"id": node["id"], "name": node["name"]})
            parent_id = node.get("parent_id")
            if curr_id == 0 or parent_id == curr_id or parent_id is None:
                break
            curr_id = parent_id
        else:
            # Fallback: attempt to load node
            info = data_loader.fetch_category_info(curr_id)
            if info:
                crumbs.append({"id": info["id"], "name": info["name"]})
                parent_id = info.get("parent_id")
                if curr_id == 0 or parent_id == curr_id or parent_id is None:
                    break
                curr_id = parent_id
            else:
                crumbs.append({"id": curr_id, "name": f"Category {curr_id}"})
                break

    # Reverse to get Root -> Parent -> Current
    crumbs.reverse()

    # Ensure Root (0) is at start if not present
    if not crumbs or crumbs[0]["id"] != 0:
        root_name = cache.get("0", {}).get("name", "Root")
        crumbs.insert(0, {"id": 0, "name": root_name})

    return crumbs


def get_children_categories(category_id: int, cache_path: str = CACHE_FILE) -> list[dict]:
    """
    Returns list of children category nodes for category_id.
    Lazily loads if not already in cache.
    """
    node = get_category_node(category_id, cache_path=cache_path)
    if not node:
        return []

    child_ids = node.get("children_ids") or []
    cache = load_category_cache(cache_path)
    children = []
    for cid in child_ids:
        cid_key = str(cid)
        if cid_key in cache:
            cnode = cache[cid_key]
            children.append({
                "id": cnode["id"],
                "name": cnode["name"],
                "parent_id": cnode.get("parent_id")
            })
        else:
            children.append({
                "id": cid,
                "name": f"Category {cid}",
                "parent_id": category_id
            })
    return children


# Alias for convenience
get_child_categories = get_children_categories


def get_category_series(category_id: int, cache_path: str = CACHE_FILE) -> list[dict]:
    """
    Returns list of series for category_id.
    Lazily loads if not already in cache.
    """
    node = get_category_node(category_id, cache_path=cache_path)
    if not node:
        return []
    return node.get("series") or []


def get_cache_stats(cache_path: str = CACHE_FILE) -> dict:
    """Returns statistics on the category graph in fred_cache.json."""
    cache = load_category_cache(cache_path)
    total_categories = len(cache)
    visited_categories = sum(1 for n in cache.values() if n.get("children_ids") is not None)
    total_series_indexed = sum(len(n.get("series") or []) for n in cache.values())
    return {
        "total_categories": total_categories,
        "visited_categories": visited_categories,
        "total_series_indexed": total_series_indexed
    }


def get_category_series_paginated(
    category_id: int,
    page: int = 1,
    page_size: int = 50,
    order_by: str = "popularity",
    sort_order: str = "desc",
    filter_text: str = "",
    cache_path: str = CACHE_FILE
) -> dict:
    """
    Retrieves a paginated, sorted list of series for category_id.
    Standardized to page_size=50 results per page.
    Calculates offset = (page - 1) * page_size.
    Returns:
    {
        "total_count": int,
        "page": int,
        "page_size": int,
        "total_pages": int,
        "start_index": int,
        "end_index": int,
        "order_by": str,
        "sort_order": str,
        "series": list[dict],
        "is_fallback": bool
    }
    """
    page = max(1, int(page))
    page_size = 50

    valid_order_by = {
        "popularity",
        "last_updated",
        "observation_end",
        "observation_start",
        "title",
        "frequency",
        "units",
        "seasonal_adjustment"
    }
    if order_by not in valid_order_by:
        order_by = "popularity"

    sort_order = sort_order.lower() if sort_order else "desc"
    if sort_order not in ("asc", "desc"):
        sort_order = "desc"

    if category_id == 0:
        return {
            "total_count": 0,
            "page": 1,
            "page_size": page_size,
            "total_pages": 1,
            "start_index": 0,
            "end_index": 0,
            "order_by": order_by,
            "sort_order": sort_order,
            "series": [],
            "is_fallback": False
        }

    filter_text = (filter_text or "").strip().lower()

    # If the user is filtering by text, search through category series
    if filter_text:
        cache = load_category_cache(cache_path)
        cat_key = str(category_id)
        node = cache.get(cat_key)

        # If node has no series or fewer than 50, attempt to fetch a larger batch for searching
        if not node or not node.get("series") or (len(node.get("series", [])) < 50 and node.get("total_series_count", 0) > len(node.get("series", []))):
            fetch_res = data_loader.fetch_category_series(category_id, limit=1000, offset=0, order_by=order_by, sort_order=sort_order)
            if fetch_res and "series" in fetch_res:
                if not node:
                    node = {
                        "id": category_id,
                        "name": f"Category {category_id}",
                        "parent_id": None,
                        "children_ids": None,
                        "series": []
                    }
                    cache[cat_key] = node
                node["series"] = fetch_res["series"]
                node["total_series_count"] = fetch_res.get("count", len(fetch_res["series"]))
                save_category_cache(cache, cache_path)

        all_series = list((node.get("series") if node else []) or [])
        filtered = [
            s for s in all_series
            if filter_text in s.get("id", "").lower() or filter_text in s.get("title", "").lower()
        ]

        def sort_key_filter(s):
            val = s.get(order_by)
            if val is None:
                return "" if order_by in ("title", "units", "frequency", "seasonal_adjustment") else 0
            return val

        try:
            filtered.sort(key=sort_key_filter, reverse=(sort_order == "desc"))
        except TypeError:
            filtered.sort(key=lambda s: str(s.get(order_by, "")), reverse=(sort_order == "desc"))

        total_count = len(filtered)
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        clamped_page = max(1, min(page, total_pages))
        start_index = (clamped_page - 1) * page_size + 1 if total_count > 0 else 0
        end_index = min(clamped_page * page_size, total_count)
        page_series = filtered[(clamped_page - 1) * page_size : clamped_page * page_size]

        return {
            "total_count": total_count,
            "page": clamped_page,
            "page_size": page_size,
            "total_pages": total_pages,
            "start_index": start_index,
            "end_index": end_index,
            "order_by": order_by,
            "sort_order": sort_order,
            "series": page_series,
            "is_fallback": False
        }

    # Standard category browsing: Query FRED API directly with limit=50 and offset
    offset = (page - 1) * page_size
    api_res = data_loader.fetch_category_series(
        category_id=category_id,
        limit=page_size,
        offset=offset,
        order_by=order_by,
        sort_order=sort_order
    )

    cache = load_category_cache(cache_path)
    cat_key = str(category_id)
    node = cache.get(cat_key)

    if api_res is not None:
        total_count = api_res.get("count", 0)
        series_items = api_res.get("series", [])
        total_pages = max(1, (total_count + page_size - 1) // page_size)

        # If requested page is out of bounds (e.g. category switch), clamp to total_pages
        if page > total_pages and total_count > 0:
            page = total_pages
            offset = (page - 1) * page_size
            api_res = data_loader.fetch_category_series(
                category_id=category_id,
                limit=page_size,
                offset=offset,
                order_by=order_by,
                sort_order=sort_order
            )
            series_items = api_res.get("series", []) if api_res else series_items

        start_index = (page - 1) * page_size + 1 if total_count > 0 else 0
        end_index = min(page * page_size, total_count)

        if node is None:
            node = {
                "id": category_id,
                "name": f"Category {category_id}",
                "parent_id": None,
                "children_ids": None,
                "series": []
            }
            cache[cat_key] = node

        node["total_series_count"] = total_count
        existing_series = node.get("series") or []
        existing_map = {s["id"]: s for s in existing_series}
        for s in series_items:
            existing_map[s["id"]] = s
        node["series"] = list(existing_map.values())
        save_category_cache(cache, cache_path)

        return {
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "start_index": start_index,
            "end_index": end_index,
            "order_by": order_by,
            "sort_order": sort_order,
            "series": series_items,
            "is_fallback": False
        }

    # Offline / Error Fallback: Use locally cached series
    cached_series = list((node.get("series") if node else []) or [])

    def sort_key_cached(s):
        val = s.get(order_by)
        if val is None:
            return "" if order_by in ("title", "units", "frequency", "seasonal_adjustment") else 0
        return val

    try:
        cached_series.sort(key=sort_key_cached, reverse=(sort_order == "desc"))
    except TypeError:
        cached_series.sort(key=lambda s: str(s.get(order_by, "")), reverse=(sort_order == "desc"))

    total_count = len(cached_series)
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    clamped_page = max(1, min(page, total_pages))
    start_index = (clamped_page - 1) * page_size + 1 if total_count > 0 else 0
    end_index = min(clamped_page * page_size, total_count)
    page_series = cached_series[(clamped_page - 1) * page_size : clamped_page * page_size]

    return {
        "total_count": total_count,
        "page": clamped_page,
        "page_size": page_size,
        "total_pages": total_pages,
        "start_index": start_index,
        "end_index": end_index,
        "order_by": order_by,
        "sort_order": sort_order,
        "series": page_series,
        "is_fallback": True
    }
