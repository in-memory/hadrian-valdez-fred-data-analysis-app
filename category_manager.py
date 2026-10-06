import json
import os
import data_loader

CACHE_FILE = "fred_cache.json"


def load_category_cache(cache_path: str = CACHE_FILE) -> dict:
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            print(
                f"Error loading {cache_path}: {e}. Initializing empty cache.")
    return {}


def save_category_cache(cache: dict, cache_path: str = CACHE_FILE) -> None:
    try:
        temp_path = f"{cache_path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
        os.replace(temp_path, cache_path)
    except Exception as e:
        print(f"Error saving {cache_path}: {e}")


def get_category_node(category_id: int, refresh: bool = False, cache_path: str = CACHE_FILE) -> dict | None:
    cache = load_category_cache(cache_path)
    cat_key = str(category_id)

    if cat_key not in cache or refresh:
        if category_id == 0:
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
                return None
            parent_id = cat_info.get("parent_id")
            cache[cat_key] = {
                "id": category_id,
                "name": cat_info["name"],
                "parent_id": parent_id if parent_id != 0 else None,
                "children_ids": None,
                "series": None
            }

    node = cache[cat_key]

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

    if node.get("series") is None or refresh:
        if category_id == 0:
            node["series"] = []
        else:
            api_res = data_loader.fetch_category_series(category_id, limit=50)
            if api_res is not None:
                series_list = api_res.get("series", []) if isinstance(
                    api_res, dict) else api_res
                node["series"] = [
                    {
                        "id": s["id"],
                        "title": s["title"],
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
                    node["total_series_count"] = api_res["count"]
            else:
                node["series"] = []

    save_category_cache(cache, cache_path)
    return node


def resolve_series_bottom_up(series_id: str, cache_path: str = CACHE_FILE) -> tuple[int | None, list[dict]]:
    series_id = series_id.strip().upper()
    cache = load_category_cache(cache_path)

    for node in cache.values():
        if any(s.get("id", "").upper() == series_id for s in (node.get("series") or [])):
            cat_id = node["id"]
            return cat_id, get_breadcrumbs(cat_id, cache_path)

    categories = data_loader.fetch_series_categories(series_id)
    if not categories:
        return None, []

    primary_cat = categories[0]
    target_cat_id = primary_cat["id"]
    target_name = primary_cat["name"]
    target_parent = primary_cat.get("parent_id")

    target_key = str(target_cat_id)
    if target_key not in cache:
        cache[target_key] = {
            "id": target_cat_id,
            "name": target_name,
            "parent_id": None if target_cat_id == 0 else target_parent,
            "children_ids": None,
            "series": []
        }

    if not any(s["id"].upper() == series_id for s in (cache[target_key].get("series") or [])):
        cache[target_key].setdefault("series", []).append({
            "id": series_id,
            "title": series_id,
            "frequency": None,
            "units": None
        })

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

    if "0" not in cache:
        cache["0"] = {"id": 0, "name": "Categories",
                      "parent_id": None, "children_ids": None, "series": []}

    save_category_cache(cache, cache_path)
    return target_cat_id, get_breadcrumbs(target_cat_id, cache_path)


def get_breadcrumbs(category_id: int, cache_path: str = CACHE_FILE) -> list[dict]:
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

    crumbs.reverse()
    if not crumbs or crumbs[0]["id"] != 0:
        root_name = cache.get("0", {}).get("name", "Root")
        crumbs.insert(0, {"id": 0, "name": root_name})

    return crumbs


def get_child_categories(category_id: int, cache_path: str = CACHE_FILE) -> list[dict]:
    node = get_category_node(category_id, cache_path=cache_path)
    if not node:
        return []

    child_ids = node.get("children_ids") or []
    cache = load_category_cache(cache_path)
    return [
        {
            "id": cache[str(cid)]["id"] if str(cid) in cache else cid,
            "name": cache[str(cid)]["name"] if str(cid) in cache else f"Category {cid}",
            "parent_id": cache[str(cid)].get("parent_id") if str(cid) in cache else category_id
        }
        for cid in child_ids
    ]


def get_cache_stats(cache_path: str = CACHE_FILE) -> dict:
    cache = load_category_cache(cache_path)
    return {
        "total_categories": len(cache),
        "visited_categories": sum(1 for n in cache.values() if n.get("children_ids") is not None),
        "total_series_indexed": sum(len(n.get("series") or []) for n in cache.values())
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
    page = max(1, int(page))
    page_size = 50
    valid_order_by = {
        "popularity", "last_updated", "observation_end", "observation_start",
        "title", "frequency", "units", "seasonal_adjustment"
    }
    if order_by not in valid_order_by:
        order_by = "popularity"

    sort_order = sort_order.lower() if sort_order in ("asc", "desc") else "desc"

    if category_id == 0:
        return {
            "total_count": 0, "page": 1, "page_size": page_size, "total_pages": 1,
            "start_index": 0, "end_index": 0, "order_by": order_by,
            "sort_order": sort_order, "series": [], "is_fallback": False
        }

    filter_text = (filter_text or "").strip().lower()

    if filter_text:
        cache = load_category_cache(cache_path)
        cat_key = str(category_id)
        node = cache.get(cat_key)

        if not node or not node.get("series") or (len(node.get("series", [])) < 50 and node.get("total_series_count", 0) > len(node.get("series", []))):
            fetch_res = data_loader.fetch_category_series(
                category_id, limit=1000, offset=0, order_by=order_by, sort_order=sort_order)
            if fetch_res and "series" in fetch_res:
                if not node:
                    node = {"id": category_id, "name": f"Category {category_id}",
                            "parent_id": None, "children_ids": None, "series": []}
                    cache[cat_key] = node
                node["series"] = fetch_res["series"]
                node["total_series_count"] = fetch_res.get(
                    "count", len(fetch_res["series"]))
                save_category_cache(cache, cache_path)

        all_series = list((node.get("series") if node else []) or [])
        filtered = [s for s in all_series if filter_text in s.get(
            "id", "").lower() or filter_text in s.get("title", "").lower()]

        def sort_key_filter(s):
            val = s.get(order_by)
            return ("" if order_by in ("title", "units", "frequency", "seasonal_adjustment") else 0) if val is None else val

        try:
            filtered.sort(key=sort_key_filter, reverse=(sort_order == "desc"))
        except TypeError:
            filtered.sort(key=lambda s: str(s.get(order_by, "")),
                          reverse=(sort_order == "desc"))

        total_count = len(filtered)
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        clamped_page = max(1, min(page, total_pages))

        return {
            "total_count": total_count,
            "page": clamped_page,
            "page_size": page_size,
            "total_pages": total_pages,
            "start_index": (clamped_page - 1) * page_size + 1 if total_count > 0 else 0,
            "end_index": min(clamped_page * page_size, total_count),
            "order_by": order_by,
            "sort_order": sort_order,
            "series": filtered[(clamped_page - 1) * page_size: clamped_page * page_size],
            "is_fallback": False
        }

    offset = (page - 1) * page_size
    api_res = data_loader.fetch_category_series(
        category_id=category_id, limit=page_size, offset=offset, order_by=order_by, sort_order=sort_order)
    cache = load_category_cache(cache_path)
    cat_key = str(category_id)
    node = cache.get(cat_key)

    if api_res is not None:
        total_count = api_res.get("count", 0)
        series_items = api_res.get("series", [])
        total_pages = max(1, (total_count + page_size - 1) // page_size)

        if page > total_pages and total_count > 0:
            page = total_pages
            offset = (page - 1) * page_size
            api_res = data_loader.fetch_category_series(
                category_id=category_id, limit=page_size, offset=offset, order_by=order_by, sort_order=sort_order)
            series_items = api_res.get(
                "series", []) if api_res else series_items

        if node is None:
            node = {"id": category_id, "name": f"Category {category_id}",
                    "parent_id": None, "children_ids": None, "series": []}
            cache[cat_key] = node

        node["total_series_count"] = total_count
        existing_map = {s["id"]: s for s in (node.get("series") or [])}
        for s in series_items:
            existing_map[s["id"]] = s
        node["series"] = list(existing_map.values())
        save_category_cache(cache, cache_path)

        return {
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "start_index": (page - 1) * page_size + 1 if total_count > 0 else 0,
            "end_index": min(page * page_size, total_count),
            "order_by": order_by,
            "sort_order": sort_order,
            "series": series_items,
            "is_fallback": False
        }

    cached_series = list((node.get("series") if node else []) or [])

    def sort_key_cached(s):
        val = s.get(order_by)
        return ("" if order_by in ("title", "units", "frequency", "seasonal_adjustment") else 0) if val is None else val

    try:
        cached_series.sort(key=sort_key_cached, reverse=(sort_order == "desc"))
    except TypeError:
        cached_series.sort(key=lambda s: str(
            s.get(order_by, "")), reverse=(sort_order == "desc"))

    total_count = len(cached_series)
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    clamped_page = max(1, min(page, total_pages))

    return {
        "total_count": total_count,
        "page": clamped_page,
        "page_size": page_size,
        "total_pages": total_pages,
        "start_index": (clamped_page - 1) * page_size + 1 if total_count > 0 else 0,
        "end_index": min(clamped_page * page_size, total_count),
        "order_by": order_by,
        "sort_order": sort_order,
        "series": cached_series[(clamped_page - 1) * page_size: clamped_page * page_size],
        "is_fallback": True
    }
