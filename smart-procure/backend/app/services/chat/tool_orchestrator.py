from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ...mcp import (
    browser_back,
    browser_click,
    browser_close_session,
    browser_create_session,
    browser_navigate,
    browser_scroll,
    browser_snapshot,
    browser_type,
)
from ..agent_runtime import ToolRegistry
from ..browser_service import browse_page_sync, search_baidu_sync
from ..sheet_schema import get_row_slot_snapshot, locate_rows_by_criteria
from ..supplier_service import SupplierService
from ..web_search import format_search_results, search_suppliers_online


def build_tool_registry(
    db: Session,
    sheet_data: List[List[Any]],
    schema: Dict[str, Any],
    enabled_tools: Optional[List[str]],
    logger,
) -> ToolRegistry:
    tools = ToolRegistry()

    def _locate_row(args: dict) -> dict:
        target_row = args.get("target_row")
        if isinstance(target_row, int) and 1 < target_row <= len(sheet_data):
            return {"candidates": [{"row": target_row}], "ambiguous": False}

        item = args.get("item_name") or args.get("lookup_item")
        brand = args.get("brand") or args.get("lookup_brand")
        model = args.get("model") or args.get("lookup_model")
        spec = args.get("spec") or args.get("lookup_spec")
        return locate_rows_by_criteria(
            sheet_data,
            item_name=item if isinstance(item, str) else None,
            brand=brand if isinstance(brand, str) else None,
            model=model if isinstance(model, str) else None,
            spec=spec if isinstance(spec, str) else None,
            max_candidates=5,
        )

    def _row_snapshot(args: dict) -> dict:
        row = args.get("row")
        if not isinstance(row, int):
            return {"row": None, "snapshot": None}
        return {"row": row, "snapshot": get_row_slot_snapshot(schema, sheet_data, row)}

    def _supplier_lookup(args: dict) -> dict:
        name = args.get("name") or args.get("lookup_supplier")
        if not isinstance(name, str) or not name.strip():
            return {"supplier": None}
        try:
            supplier_service = SupplierService(db)
            results = supplier_service.search_suppliers(name.strip(), limit=1)
            if results:
                supplier = " ".join(
                    [
                        results[0].company_name or "",
                        results[0].contact_name or "",
                        results[0].contact_phone or "",
                    ]
                ).strip()
                return {"supplier": supplier or None}
        except Exception as exc:
            logger.warning("Supplier lookup error for name=%s", name, exc_info=exc)
        return {"supplier": None}

    def _web_search_supplier(args: dict) -> dict:
        brand = args.get("brand")
        if not isinstance(brand, str) or not brand.strip():
            return {"success": False, "message": "品牌名称不能为空"}

        try:
            results = search_suppliers_online(brand.strip(), max_results=5)
            if not results:
                return {
                    "success": False,
                    "message": f"未找到 '{brand}' 的供应商信息",
                    "results": [],
                }
            return {
                "success": True,
                "message": format_search_results(brand, results),
                "results": results,
                "count": len(results),
            }
        except Exception as exc:
            logger.warning("Web search error for brand=%s", brand, exc_info=exc)
            return {"success": False, "message": f"Search failed: {exc}", "results": []}

    def _web_browse(args: dict) -> dict:
        url = args.get("url")
        action = args.get("action", "browse")
        query = args.get("query")
        try:
            if action == "search" and query:
                result = search_baidu_sync(query, max_results=5)
                if result["success"]:
                    return {
                        "success": True,
                        "action": "search",
                        "query": query,
                        "results": result["results"],
                        "message": f"Found {result['count']} results",
                    }
                return {"success": False, "error": result["error"]}

            if url:
                result = browse_page_sync(url, extract_text=True, extract_links=False)
                if result["success"]:
                    return {
                        "success": True,
                        "action": "browse",
                        "title": result["title"],
                        "content": result["text"][:5000],
                        "message": f"成功访问页面: {result['title']}",
                    }
                return {"success": False, "error": result["error"]}

            return {"success": False, "error": "请提供 url 或 query 参数"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    browser_session = {"id": None}

    def _browser_start(args: dict) -> dict:
        result = browser_create_session()
        if result["success"]:
            browser_session["id"] = result["session_id"]
        return result

    def _browser_stop(args: dict) -> dict:
        if not browser_session["id"]:
            return {"success": False, "error": "没有活动的浏览器会话"}
        result = browser_close_session(browser_session["id"])
        browser_session["id"] = None
        return result

    def _browser_goto(args: dict) -> dict:
        if not browser_session["id"]:
            start_result = browser_create_session()
            if not start_result["success"]:
                return start_result
            browser_session["id"] = start_result["session_id"]

        url = args.get("url")
        if not url:
            return {"success": False, "error": "请提供 url 参数"}
        return browser_navigate(browser_session["id"], url)

    def _browser_click_element(args: dict) -> dict:
        if not browser_session["id"]:
            return {"success": False, "error": "Please start a browser session first"}
        element = args.get("element")
        if not element:
            return {"success": False, "error": "请提供 element 参数"}
        return browser_click(browser_session["id"], element)

    def _browser_input(args: dict) -> dict:
        if not browser_session["id"]:
            return {"success": False, "error": "Please start a browser session first"}
        element = args.get("element")
        text = args.get("text")
        if not element or not text:
            return {"success": False, "error": "请提供 element 和 text 参数"}
        return browser_type(browser_session["id"], element, text)

    def _browser_get_snapshot(args: dict) -> dict:
        if not browser_session["id"]:
            return {"success": False, "error": "Please start a browser session first"}
        return browser_snapshot(browser_session["id"])

    def _browser_scroll_page(args: dict) -> dict:
        if not browser_session["id"]:
            return {"success": False, "error": "Please start a browser session first"}
        direction = args.get("direction", "down")
        return browser_scroll(browser_session["id"], direction)

    def _browser_go_back(args: dict) -> dict:
        if not browser_session["id"]:
            return {"success": False, "error": "Please start a browser session first"}
        return browser_back(browser_session["id"])

    all_tools = {
        "locate_row": (
            {"description": "Locate candidate rows by name/brand/model/spec", "args": {"item_name": "str?", "brand": "str?", "model": "str?", "spec": "str?", "target_row": "int?"}},
            _locate_row,
        ),
        "get_row_slot_snapshot": (
            {"description": "Get slot snapshot for a target row", "args": {"row": "int"}},
            _row_snapshot,
        ),
        "supplier_lookup": (
            {"description": "Lookup supplier by name", "args": {"name": "str"}},
            _supplier_lookup,
        ),
        "web_search_supplier": (
            {"description": "Search suppliers on the web by brand", "args": {"brand": "str"}},
            _web_search_supplier,
        ),
        "web_browse": (
            {"description": "Browse a page or run a web search", "args": {"url": "str?", "action": "str?", "query": "str?"}},
            _web_browse,
        ),
        "browser_start": (
            {"description": "Start browser session", "args": {}},
            _browser_start,
        ),
        "browser_stop": (
            {"description": "Stop browser session", "args": {}},
            _browser_stop,
        ),
        "browser_goto": (
            {"description": "Navigate to URL", "args": {"url": "str"}},
            _browser_goto,
        ),
        "browser_click": (
            {"description": "Click an element", "args": {"element": "str"}},
            _browser_click_element,
        ),
        "browser_input": (
            {"description": "Type into an input element", "args": {"element": "str", "text": "str"}},
            _browser_input,
        ),
        "browser_snapshot": (
            {"description": "Get accessibility snapshot of current page", "args": {}},
            _browser_get_snapshot,
        ),
        "browser_scroll": (
            {"description": "Scroll page up/down", "args": {"direction": "str?"}},
            _browser_scroll_page,
        ),
        "browser_back": (
            {"description": "Go back to previous page", "args": {}},
            _browser_go_back,
        ),
    }

    target_tools = enabled_tools if enabled_tools is not None else list(all_tools.keys())
    for tool_name in target_tools:
        if tool_name in all_tools:
            spec, fn = all_tools[tool_name]
            tools.register(tool_name, spec, fn)

    return tools
