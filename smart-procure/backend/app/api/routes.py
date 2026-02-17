from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from typing import List, Optional
from sqlalchemy.orm import Session
from ..models.types import ChatRequest, ChatResponse, UpdateAction
from ..models.database import get_db, User
from ..services.supplier_service import SupplierService
from ..services.excel_core import process_update
from ..services.web_search import search_suppliers_online, format_search_results
from ..services.browser_service import browse_page_sync, search_baidu_sync
from ..mcp import (
    browser_create_session,
    browser_close_session,
    browser_navigate,
    browser_click,
    browser_type,
    browser_snapshot,
    browser_scroll,
    browser_back,
)
from ..core.llm import call_llm
from ..services.agent_runtime import ToolRegistry, run_two_stage_agent
from ..services.sheet_schema import (
    build_sheet_schema,
    build_writable_fields,
    extract_row_from_message,
    find_candidate_rows,
    locate_rows_by_criteria,
    get_row_slot_snapshot,
    fuzzy_match_rows,
)
from ..auth.utils import get_current_user
import logging
import json
import pandas as pd
import io
import re

router = APIRouter()
logger = logging.getLogger(__name__)

def get_sheet_state_summary(sheet_data):
    if not sheet_data or len(sheet_data) < 2 or not isinstance(sheet_data[0], list):
        return "empty"

    schema = build_sheet_schema(sheet_data)
    slots = schema.get("slots") or {}
    slot_count = len(slots.keys()) if isinstance(slots, dict) else 0
    cols = schema.get("item_columns") or {}
    name_col = cols.get("name")
    brand_col = cols.get("brand")
    model_col = cols.get("model")

    def _cell(row, idx):
        if not isinstance(idx, int):
            return ""
        if not isinstance(row, list) or idx < 0 or idx >= len(row):
            return ""
        v = row[idx]
        if v is None:
            return ""
        s = str(v).strip()
        return "" if s.lower() == "none" else s

    def _has_price(row, slot_num: int) -> bool:
        slot_map = slots.get(slot_num) or {}
        price_idx = slot_map.get("鍗曚环")
        if not isinstance(price_idx, int):
            return False
        v = row[price_idx] if isinstance(row, list) and price_idx < len(row) else None
        if v is None:
            return False
        s = str(v).strip()
        return s != "" and s.lower() != "none"

    slot_nums = sorted([int(k) for k in (slots.keys() if isinstance(slots, dict) else []) if isinstance(k, int)])
    if not slot_nums:
        slot_nums = [1]

    per_brand = {}
    detail_parts = []
    for i, row in enumerate(sheet_data[1:], start=2):
        if not isinstance(row, list):
            continue
        name = _cell(row, name_col)
        brand = _cell(row, brand_col)
        model = _cell(row, model_col)
        if not name and not brand and not model:
            continue
        got = sum(1 for n in slot_nums if _has_price(row, n))
        total = len(slot_nums)
        bkey = brand or "鏈～鍝佺墝"
        stat = per_brand.setdefault(bkey, {"items": 0, "got": 0, "total": 0})
        stat["items"] += 1
        stat["got"] += got
        stat["total"] += total

        base = f"row {i}: {name or 'N/A'}"
        if brand:
            base += f" | 鍝佺墝:{brand}"
        if model:
            base += f" | 鍨嬪彿:{model}"
        base += f" | 宸茶:{got}/{total}"
        detail_parts.append(base)
        if len(detail_parts) >= 12:
            break

    brand_parts = []
    for brand, stat in sorted(per_brand.items(), key=lambda kv: (-kv[1]["items"], kv[0])):
        brand_parts.append(f"{brand} {stat['items']}椤?宸茶{stat['got']}/{stat['total']}")
        if len(brand_parts) >= 6:
            break

    slot_text = f"妲戒綅鏁?{len(slot_nums)}"
    brand_text = " | ".join(brand_parts) if brand_parts else "none"
    detail_text = " | ".join(detail_parts) if detail_parts else "none"
    return f"{slot_text} | brands:{brand_text} | details:{detail_text}"

def get_pending_summary(sheet_data):
    summary = []
    if not sheet_data or len(sheet_data) < 2:
        return "empty"

    schema = build_sheet_schema(sheet_data)
    headers = schema.get("headers") or []
    cols = schema.get("item_columns") or {}
    name_col = cols.get("name")
    spec_col = cols.get("spec")

    for i, row in enumerate(sheet_data[1:], start=2):
        if not isinstance(row, list):
            continue
        name = row[name_col] if isinstance(name_col, int) and name_col < len(row) else None
        spec = row[spec_col] if isinstance(spec_col, int) and spec_col < len(row) else None
        if name is None and spec is None:
            continue
        label = str(name) if name is not None else ""
        spec_text = str(spec) if spec is not None else ""
        if label.strip() == "" and spec_text.strip() == "":
            continue
        if spec_text.strip():
            summary.append(f"row {i}: {label} ({spec_text})")
        else:
            summary.append(f"row {i}: {label}")
        if i >= 8:
            break
    if not summary and headers:
        return "empty"
    return "; ".join(summary) if summary else "empty"


def build_candidate_rows_summary(sheet_data, rows: list) -> str:
    if not sheet_data or not rows:
        return "none"
    schema = build_sheet_schema(sheet_data)
    cols = schema.get("item_columns") or {}
    name_col = cols.get("name")
    brand_col = cols.get("brand")
    spec_col = cols.get("spec")
    parts = []
    for r in rows:
        idx = r - 1
        if idx < 1 or idx >= len(sheet_data):
            continue
        row = sheet_data[idx]
        if not isinstance(row, list):
            continue
        name = row[name_col] if isinstance(name_col, int) and name_col < len(row) else ""
        brand = row[brand_col] if isinstance(brand_col, int) and brand_col < len(row) else ""
        spec = row[spec_col] if isinstance(spec_col, int) and spec_col < len(row) else ""
        text = f"row {r}: {name}"
        if brand:
            text += f" | 鍝佺墝: {brand}"
        if spec:
            text += f" | 瑙勬牸: {spec}"
        parts.append(text)
    return "; ".join(parts) if parts else "none"


def extract_models_from_message(message: str, sheet_data: list) -> list:
    """Extract possible model tokens from user message."""
    if not message or not sheet_data or len(sheet_data) < 2:
        return []

    # 鑾峰彇琛ㄦ牸涓墍鏈夌殑鍨嬪彿
    schema = build_sheet_schema(sheet_data)
    cols = schema.get("item_columns") or {}
    model_col = cols.get("model")

    if not isinstance(model_col, int):
        return []

    # 鎻愬彇琛ㄦ牸涓殑鎵€鏈夊瀷鍙?
    table_models = []
    for row in sheet_data[1:]:
        if isinstance(row, list) and model_col < len(row):
            model = row[model_col]
            if model and str(model).strip():
                table_models.append(str(model).strip())

    # 浠庢秷鎭腑鏌ユ壘鍙兘鐨勫瀷鍙凤紙浣跨敤妯＄硦鍖归厤锛?
    potential_models = []
    words = re.split(r'[\s,锛屻€乚+', message)

    for word in words:
        word = word.strip()
        if not word or len(word) < 3:
            continue
        # 妫€鏌ユ槸鍚︿笌琛ㄦ牸涓殑鍨嬪彿鐩镐技
        for table_model in table_models:
            from ..services.sheet_schema import fuzzy_match_score
            score = fuzzy_match_score(word, table_model)
            if score >= 70:  # 鐩镐技搴﹂槇鍊?
                if word not in potential_models:
                    potential_models.append(word)
                break

    return potential_models


def extract_brand_from_message(message: str, sheet_data: list) -> Optional[str]:
    """浠庣敤鎴锋秷鎭腑鎻愬彇鍝佺墝"""
    if not message or not sheet_data or len(sheet_data) < 2:
        return None

    # 鑾峰彇琛ㄦ牸涓墍鏈夌殑鍝佺墝
    schema = build_sheet_schema(sheet_data)
    cols = schema.get("item_columns") or {}
    brand_col = cols.get("brand")

    if not isinstance(brand_col, int):
        return None

    # 鎻愬彇琛ㄦ牸涓殑鎵€鏈夊搧鐗?
    table_brands = set()
    for row in sheet_data[1:]:
        if isinstance(row, list) and brand_col < len(row):
            brand = row[brand_col]
            if brand and str(brand).strip():
                table_brands.add(str(brand).strip())

    # 浠庢秷鎭腑鏌ユ壘鍝佺墝
    for brand in table_brands:
        if brand in message:
            return brand

    return None


def build_smart_context(message: str, sheet_data: list, max_rows: int = 50) -> dict:
    """
    鏋勫缓鏅鸿兘涓婁笅鏂囨敞鍏ユ暟鎹?

    Args:
        message: 鐢ㄦ埛娑堟伅
        sheet_data: 琛ㄦ牸鏁版嵁
        max_rows: 鏈€澶氭敞鍏ョ殑琛屾暟

    Returns:
        鍖呭惈鍝佺墝涓婁笅鏂囧拰鐩稿叧浜у搧鍒楄〃鐨勫瓧鍏?
    """
    if not sheet_data or len(sheet_data) < 2:
        return {"brand_context": None, "relevant_rows": [], "total_matched": 0}

    # 1. 鎻愬彇鍝佺墝鍜屽瀷鍙?
    brand_context = extract_brand_from_message(message, sheet_data)
    potential_models = extract_models_from_message(message, sheet_data)

    # 2. 浣跨敤妯＄硦鍖归厤鎵惧埌鐩稿叧琛?
    relevant_rows_dict = {}  # 浣跨敤瀛楀吀鍘婚噸锛宬ey涓鸿鍙?

    # 2.1 鏍规嵁鎻愬彇鐨勫瀷鍙疯繘琛屾ā绯婂尮閰?
    for model in potential_models:
        matches = fuzzy_match_rows(
            sheet_data,
            model,
            brand_filter=brand_context,
            threshold=75.0,  # 闄嶄綆闃堝€间互鏀寔鏇村鍙樹綋
            max_results=10
        )
        for match in matches:
            row_num = match["row"]
            if row_num not in relevant_rows_dict:
                relevant_rows_dict[row_num] = match

    # 2.2 濡傛灉璇嗗埆鍒板搧鐗岋紝琛ュ厖璇ュ搧鐗岀殑鎵€鏈変骇鍝?
    if brand_context:
        schema = build_sheet_schema(sheet_data)
        cols = schema.get("item_columns") or {}
        brand_col = cols.get("brand")

        if isinstance(brand_col, int):
            for i, row in enumerate(sheet_data[1:], start=2):
                if not isinstance(row, list) or brand_col >= len(row):
                    continue
                row_brand = row[brand_col]
                if row_brand and str(row_brand).strip() == brand_context:
                    if i not in relevant_rows_dict:
                        # 娣诲姞璇ュ搧鐗岀殑浜у搧
                        relevant_rows_dict[i] = {
                            "row": i,
                            "score": 100.0,  # 鍝佺墝鍖归厤缁欓珮鍒?
                            "match_field": "鍝佺墝",
                            "name": row[cols.get("name")] if isinstance(cols.get("name"), int) and cols.get("name") < len(row) else None,
                            "brand": brand_context,
                            "model": row[cols.get("model")] if isinstance(cols.get("model"), int) and cols.get("model") < len(row) else None,
                            "spec": row[cols.get("spec")] if isinstance(cols.get("spec"), int) and cols.get("spec") < len(row) else None,
                        }

    # 3. 杞崲涓哄垪琛ㄥ苟鎺掑簭
    relevant_rows = list(relevant_rows_dict.values())
    relevant_rows.sort(key=lambda x: (-x["score"], x["row"]))

    # 4. 闄愬埗鏁伴噺
    relevant_rows = relevant_rows[:max_rows]

    return {
        "brand_context": brand_context,
        "relevant_rows": relevant_rows,
        "total_matched": len(relevant_rows)
    }


def build_history_messages(chat_history, max_messages: int = 12, max_chars_per_message: int = 1200):
    if not chat_history:
        return None

    items = []
    for m in chat_history:
        role = getattr(m, "role", None)
        content = getattr(m, "content", None)
        if role not in ("user", "assistant"):
            continue
        if not isinstance(content, str):
            continue
        c = content.strip()
        if not c:
            continue
        if len(c) > max_chars_per_message:
            c = c[:max_chars_per_message]
        items.append({"role": role, "content": c})

    if not items:
        return None

    return items[-max_messages:]

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    sheet_data = request.current_sheet_data or []
    schema = build_sheet_schema(sheet_data)
    headers = schema.get("headers") or []
    headers_preview = [str(h) for h in headers[:40]]
    writable_fields_json = json.dumps(build_writable_fields(schema), ensure_ascii=False)

    required_fields = []
    slots = schema.get("slots") or {}
    slot_num = sorted(slots.keys())[0] if slots else None
    if slot_num is not None:
        required_fields = [k for k in ("鍗曚环", "鍚◣", "鍚繍", "璐ф湡") if k in slots.get(slot_num, {})]
    else:
        required_fields = ["鍗曚环", "鍚◣", "鍚繍", "璐ф湡"]

    has_price_col = any("鍗曚环" in (slot or {}) for slot in (slots.values() if isinstance(slots, dict) else []))
    if not has_price_col:
        return ChatResponse(action="ASK", content="No writable quote columns detected in this sheet. Please upload a valid inquiry sheet template.")

    # 浣跨敤鏅鸿兘涓婁笅鏂囨敞鍏?
    smart_context = build_smart_context(request.message, sheet_data, max_rows=50)

    summary = get_pending_summary(sheet_data)
    sheet_state_summary = get_sheet_state_summary(sheet_data)
    history_messages = build_history_messages(request.chat_history)

    # 鏋勫缓鐩稿叧琛岀殑璇︾粏淇℃伅锛堢敤浜庢敞鍏ョ粰AI锛?
    relevant_rows_detail = []
    for row_info in smart_context["relevant_rows"]:
        # 鑾峰彇璇ヨ鐨勬姤浠锋Ы浣嶇姸鎬?
        row_num = row_info["row"]
        slot_status = []
        for slot_num in sorted(slots.keys())[:3]:  # 鏈€澶?涓Ы浣?
            slot_map = slots.get(slot_num) or {}
            price_idx = slot_map.get("鍗曚环")
            if isinstance(price_idx, int) and row_num - 1 < len(sheet_data):
                row_data = sheet_data[row_num - 1]
                if isinstance(row_data, list) and price_idx < len(row_data):
                    price_val = row_data[price_idx]
                    has_price = price_val is not None and str(price_val).strip() not in ("", "none", "None")
                    slot_status.append(f"slot {slot_num} {'filled' if has_price else 'empty'}")

        relevant_rows_detail.append({
            "琛屽彿": row_num,
            "鍝佺墝": row_info.get("brand"),
            "浜у搧鍚嶇О": row_info.get("name"),
            "鍨嬪彿": row_info.get("model"),
            "瑙勬牸": row_info.get("spec"),
            "match_score": f"{row_info['score']:.0f}%",
            "鍖归厤瀛楁": row_info.get("match_field"),
            "slot_status": ", ".join(slot_status) if slot_status else "no slots",
        })

    context = {
        "sheet_state_summary": sheet_state_summary,
        "pending_items_summary": summary,
        "headers_preview_json": json.dumps(headers_preview, ensure_ascii=False),
        "writable_fields_json": writable_fields_json,
        "required_fields_json": json.dumps(required_fields, ensure_ascii=False),
        "brand_context": smart_context["brand_context"] or "unknown",
        "relevant_rows_json": json.dumps(relevant_rows_detail, ensure_ascii=False),
        "total_relevant_rows": smart_context["total_matched"],
    }

    tools = ToolRegistry()

    def _locate_row(args: dict) -> dict:
        target_row = args.get("target_row")
        if isinstance(target_row, int) and 1 < target_row <= len(sheet_data):
            return {"candidates": [{"row": target_row}], "ambiguous": False}

        item = args.get("item_name") or args.get("lookup_item")
        brand = args.get("brand") or args.get("lookup_brand")
        model = args.get("model") or args.get("lookup_model")
        spec = args.get("spec") or args.get("lookup_spec")
        located = locate_rows_by_criteria(
            sheet_data,
            item_name=item if isinstance(item, str) else None,
            brand=brand if isinstance(brand, str) else None,
            model=model if isinstance(model, str) else None,
            spec=spec if isinstance(spec, str) else None,
            max_candidates=5,
        )
        return located

    def _row_snapshot(args: dict) -> dict:
        row = args.get("row")
        if not isinstance(row, int):
            return {"row": None, "snapshot": None}
        return {"row": row, "snapshot": get_row_slot_snapshot(schema, sheet_data, row)}

    def _supplier_lookup(args: dict) -> dict:
        name = args.get("name") or args.get("lookup_supplier")
        if not isinstance(name, str) or not name.strip():
            return {"supplier": None}

        # Search database for supplier
        try:
            supplier_service = SupplierService(db)
            results = supplier_service.search_suppliers(name.strip(), limit=1)
            if results:
                s = results[0]
                supplier = " ".join([
                    s.company_name or "",
                    s.contact_name or "",
                    s.contact_phone or ""
                ]).strip()
                return {"supplier": supplier or None}
        except Exception as e:
            logger.warning("Supplier lookup error for name=%s", name, exc_info=e)

        return {"supplier": None}

    def _web_search_supplier(args: dict) -> dict:
        """缃戠粶鎼滅储鍝佺墝鐨勪緵搴斿晢淇℃伅"""
        brand = args.get("brand")
        if not isinstance(brand, str) or not brand.strip():
            return {"success": False, "message": "鍝佺墝鍚嶇О涓嶈兘涓虹┖"}

        try:
            results = search_suppliers_online(brand.strip(), max_results=5)
            if not results:
                return {
                    "success": False,
                    "message": f"鏈壘鍒?{brand}'鐨勪緵搴斿晢淇℃伅",
                    "results": []
                }

            formatted_text = format_search_results(brand, results)
            return {
                "success": True,
                "message": formatted_text,
                "results": results,
                "count": len(results)
            }
        except Exception as e:
            logger.warning("Web search error for brand=%s", brand, exc_info=e)
            return {
                "success": False,
                "message": f"Search failed: {str(e)}",
                "results": []
            }

    def _web_browse(args: dict) -> dict:
        """浣跨敤娴忚鍣ㄨ闂綉椤垫垨鎼滅储"""
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
                else:
                    return {"success": False, "error": result["error"]}

            elif url:
                result = browse_page_sync(url, extract_text=True, extract_links=False)
                if result["success"]:
                    return {
                        "success": True,
                        "action": "browse",
                        "title": result["title"],
                        "content": result["text"][:5000],
                        "message": f"鎴愬姛璁块棶椤甸潰: {result['title']}"
                    }
                else:
                    return {"success": False, "error": result["error"]}

            else:
                return {"success": False, "error": "璇锋彁渚?url 鎴?query 鍙傛暟"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    # ========== 杩唬寮忔祻瑙堝櫒宸ュ叿 ==========
    # 鐢ㄤ簬瀛樺偍褰撳墠浼氳瘽鐨勬祻瑙堝櫒 session_id
    browser_session = {"id": None}

    def _browser_start(args: dict) -> dict:
        """Start a browser session."""
        result = browser_create_session()
        if result["success"]:
            browser_session["id"] = result["session_id"]
        return result

    def _browser_stop(args: dict) -> dict:
        """Close the current browser session."""
        if not browser_session["id"]:
            return {"success": False, "error": "娌℃湁娲诲姩鐨勬祻瑙堝櫒浼氳瘽"}
        result = browser_close_session(browser_session["id"])
        browser_session["id"] = None
        return result

    def _browser_goto(args: dict) -> dict:
        """瀵艰埅鍒版寚瀹?URL"""
        if not browser_session["id"]:
            # 鑷姩鍒涘缓浼氳瘽
            start_result = browser_create_session()
            if not start_result["success"]:
                return start_result
            browser_session["id"] = start_result["session_id"]

        url = args.get("url")
        if not url:
            return {"success": False, "error": "璇锋彁渚?url 鍙傛暟"}
        return browser_navigate(browser_session["id"], url)

    def _browser_click_element(args: dict) -> dict:
        """鐐瑰嚮椤甸潰鍏冪礌"""
        if not browser_session["id"]:
            return {"success": False, "error": "Please start a browser session first"}
        element = args.get("element")
        if not element:
            return {"success": False, "error": "璇锋彁渚?element 鍙傛暟"}
        return browser_click(browser_session["id"], element)

    def _browser_input(args: dict) -> dict:
        """鍦ㄥ厓绱犱腑杈撳叆鏂囨湰"""
        if not browser_session["id"]:
            return {"success": False, "error": "Please start a browser session first"}
        element = args.get("element")
        text = args.get("text")
        if not element or not text:
            return {"success": False, "error": "璇锋彁渚?element 鍜?text 鍙傛暟"}
        return browser_type(browser_session["id"], element, text)

    def _browser_get_snapshot(args: dict) -> dict:
        """鑾峰彇褰撳墠椤甸潰蹇収"""
        if not browser_session["id"]:
            return {"success": False, "error": "Please start a browser session first"}
        return browser_snapshot(browser_session["id"])

    def _browser_scroll_page(args: dict) -> dict:
        """婊氬姩椤甸潰"""
        if not browser_session["id"]:
            return {"success": False, "error": "Please start a browser session first"}
        direction = args.get("direction", "down")
        return browser_scroll(browser_session["id"], direction)

    def _browser_go_back(args: dict) -> dict:
        """Navigate back to previous page."""
        if not browser_session["id"]:
            return {"success": False, "error": "Please start a browser session first"}
        return browser_back(browser_session["id"])

    # Define all available tools
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

    # 鏍规嵁 enabled_tools 鍙傛暟閫夋嫨鎬ф敞鍐屽伐鍏?
    enabled_tools = request.enabled_tools if request.enabled_tools is not None else list(all_tools.keys())
    for tool_name in enabled_tools:
        if tool_name in all_tools:
            spec, fn = all_tools[tool_name]
            tools.register(tool_name, spec, fn)

    # 璋冭瘯鏃ュ織
    logger.debug("Registered tools: %s", [t["name"] for t in tools.describe()])
    logger.debug("User message: %s", request.message)
    agent_out = run_two_stage_agent(
        call_llm=call_llm,
        user_message=request.message,
        history_messages=history_messages,
        context=context,
        tools=tools,
        max_tool_steps=3,
    )

    if agent_out.get("action") == "ASK":
        return ChatResponse(action="ASK", content=agent_out.get("content") or "Please provide more details.")

    if agent_out.get("action") == "WRITE":
        updates = agent_out.get("updates")
        if isinstance(updates, list):
            if not updates:
                return ChatResponse(action="ASK", content="LLM did not return executable updates.")

            current_sheet = sheet_data
            updated_rows = []
            for item in updates[:50]:
                if not isinstance(item, dict):
                    continue
                data_dict = dict(item)

                explicit_row = extract_row_from_message(request.message)
                if not data_dict.get("target_row") and explicit_row:
                    data_dict["target_row"] = explicit_row

                missing = []
                required = set(required_fields)
                if "鍗曚环" in required and (not data_dict.get("price") and data_dict.get("price") != 0):
                    missing.append("鍗曚环")
                if "鍚◣" in required and "tax" not in data_dict:
                    missing.append("鍚◣")
                if "鍚繍" in required and "shipping" not in data_dict:
                    missing.append("鍚繍")
                if "璐ф湡" in required and not data_dict.get("delivery_time"):
                    missing.append("璐ф湡")
                if not data_dict.get("target_row"):
                    missing.append("琛屽彿/鐗╂枡鍚嶇О")
                if missing:
                    return ChatResponse(action="ASK", content=f"璇疯ˉ鍏咃細{', '.join(missing)}")

                lookup_name = data_dict.get("lookup_supplier")
                if lookup_name and not data_dict.get("supplier"):
                    # 灏濊瘯浠庢暟鎹簱鏌ユ壘渚涘簲鍟?
                    try:
                        supplier_service = SupplierService(db)
                        results = supplier_service.search_suppliers(str(lookup_name).strip(), limit=1)
                        if results:
                            s = results[0]
                            supplier_info = " ".join([
                                s.company_name or "",
                                s.contact_name or "",
                                s.contact_phone or ""
                            ]).strip()
                            if supplier_info:
                                data_dict["supplier"] = supplier_info
                    except Exception as e:
                        logger.warning("Supplier lookup failed during batch update", exc_info=e)

                field_names = getattr(UpdateAction, "model_fields", None)
                if isinstance(field_names, dict):
                    allowed = set(field_names.keys())
                else:
                    allowed = set(getattr(UpdateAction, "__fields__", {}).keys())
                cleaned = {k: v for k, v in data_dict.items() if k in allowed}
                update_action = UpdateAction(**cleaned)
                current_sheet = process_update(current_sheet, update_action)
                updated_rows.append(update_action.target_row)

            if not updated_rows:
                return ChatResponse(action="ASK", content="鏇存柊鍒楄〃涓病鏈夊彲鎵ц鐨勬洿鏂伴」")

            # 妫€鏌ョ己澶卞瓧娈靛苟鐢熸垚鎻愰啋
            missing_fields = set()
            for data_dict in updates:
                if not data_dict.get("supplier"):
                    missing_fields.add("supplier")
                if data_dict.get("shipping") is None:
                    missing_fields.add("鍚繍")

            # 鐢熸垚鍝嶅簲娑堟伅
            success_msg = f"鉁?鎶ヤ环宸叉洿鏂?(琛?{', '.join(str(r) for r in updated_rows[:10])})"
            if missing_fields:
                reminder = f"\n\n馃挕 鎻愮ず锛氱己灏戜互涓嬩俊鎭紝濡傞渶琛ュ厖璇风户缁緭鍏ワ細{', '.join(missing_fields)}"
                success_msg += reminder

            response = ChatResponse(
                action="WRITE",
                content=success_msg,
                data=updates,
                updated_sheet=current_sheet,
            )
            return response

        data_dict = agent_out.get("data") or {}
        if not isinstance(data_dict, dict):
            return ChatResponse(action="ASK", content="LLM杩斿洖鐨勬暟鎹牸寮忎笉姝ｇ‘")

        explicit_row = extract_row_from_message(request.message)
        if not data_dict.get("target_row") and explicit_row:
            data_dict["target_row"] = explicit_row

        if not explicit_row:
            tool_results = agent_out.get("tool_results") or []
            locate = None
            for tr in reversed(tool_results if isinstance(tool_results, list) else []):
                if isinstance(tr, dict) and tr.get("ok") and tr.get("tool") == "locate_row":
                    locate = tr
                    break
            if locate:
                result = locate.get("result") or {}
                candidates = result.get("candidates") or []
                ambiguous = bool(result.get("ambiguous"))
                if (ambiguous or (isinstance(candidates, list) and len(candidates) > 1)) and not data_dict.get("target_row"):
                    lines = []
                    for c in candidates[:3]:
                        if not isinstance(c, dict):
                            continue
                        row = c.get("row")
                        name = c.get("name")
                        brand = c.get("brand")
                        model = c.get("model")
                        spec = c.get("spec")
                        text = f"row {row}: {name or ''}"
                        if brand:
                            text += f" | 鍝佺墝:{brand}"
                        if model:
                            text += f" | 鍨嬪彿:{model}"
                        if spec:
                            text += f" | 瑙勬牸:{spec}"
                        lines.append(text)
                    tip = " | ".join(lines) if lines else "multiple candidates"
                    return ChatResponse(action="ASK", content=f"Multiple candidate rows matched. Please specify row number or provide more details. {tip}")

        missing = []
        required = set(required_fields)
        if "鍗曚环" in required and (not data_dict.get("price") and data_dict.get("price") != 0):
            missing.append("鍗曚环")
        if "鍚◣" in required and "tax" not in data_dict:
            missing.append("鍚◣")
        if "鍚繍" in required and "shipping" not in data_dict:
            missing.append("鍚繍")
        if "璐ф湡" in required and not data_dict.get("delivery_time"):
            missing.append("璐ф湡")
        if not data_dict.get("target_row"):
            missing.append("琛屽彿/鐗╂枡鍚嶇О")
        if missing:
            return ChatResponse(action="ASK", content=f"璇疯ˉ鍏咃細{', '.join(missing)}")
        
        try:
            lookup_name = data_dict.get("lookup_supplier")
            if lookup_name and not data_dict.get("supplier"):
                # 灏濊瘯浠庢暟鎹簱鏌ユ壘渚涘簲鍟?
                try:
                    supplier_service = SupplierService(db)
                    results = supplier_service.search_suppliers(str(lookup_name).strip(), limit=1)
                    if results:
                        s = results[0]
                        supplier_info = " ".join([
                            s.company_name or "",
                            s.contact_name or "",
                            s.contact_phone or ""
                        ]).strip()
                        if supplier_info:
                            data_dict["supplier"] = supplier_info
                except Exception as e:
                    logger.warning("Supplier lookup failed during single update", exc_info=e)

            field_names = getattr(UpdateAction, "model_fields", None)
            if isinstance(field_names, dict):
                allowed = set(field_names.keys())
            else:
                allowed = set(getattr(UpdateAction, "__fields__", {}).keys())
            cleaned = {k: v for k, v in data_dict.items() if k in allowed}
            update_action = UpdateAction(**cleaned)
            new_sheet = process_update(sheet_data, update_action)

            # 妫€鏌ョ己澶卞瓧娈靛苟鐢熸垚鎻愰啋
            missing_fields = []
            if not update_action.supplier:
                missing_fields.append("supplier")
            if update_action.shipping is None:
                missing_fields.append("鍚繍")

            # 鐢熸垚鍝嶅簲娑堟伅
            success_msg = f"鉁?鎶ヤ环宸叉洿鏂?(琛?{update_action.target_row})"
            if missing_fields:
                reminder = f"\n\n馃挕 鎻愮ず锛氱己灏戜互涓嬩俊鎭紝濡傞渶琛ュ厖璇风户缁緭鍏ワ細{', '.join(missing_fields)}"
                success_msg += reminder

            return ChatResponse(
                action="WRITE",
                content=success_msg,
                data=update_action,
                updated_sheet=new_sheet
            )
        except Exception as e:
            return ChatResponse(action="ASK", content=f"鏇存柊琛ㄦ牸澶辫触: {str(e)}")

    return ChatResponse(action="ASK", content="鏈煡鎸囦护")

# 鏂囦欢涓婁紶澶у皬闄愬埗 (10MB)
MAX_UPLOAD_SIZE = 10 * 1024 * 1024
ALLOWED_MIME_TYPES = [
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # xlsx
    "application/vnd.ms-excel",  # xls
]

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 楠岃瘉鏂囦欢鎵╁睍鍚?
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="浠呮敮鎸?Excel 鏂囦欢鏍煎紡 (.xlsx, .xls)")

    # 楠岃瘉 MIME 绫诲瀷
    if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail="鏂囦欢绫诲瀷涓嶆纭紝璇蜂笂浼?Excel 鏂囦欢")

    try:
        # 璇诲彇鏂囦欢骞舵鏌ュぇ灏?
        contents = await file.read()
        if len(contents) > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=400, detail="鏂囦欢澶у皬瓒呰繃闄愬埗 (鏈€澶?10MB)")

        df = pd.read_excel(io.BytesIO(contents))

        # Replace NaN with empty string
        df = df.fillna("")

        # Convert to list of lists
        # Include headers as the first row
        headers = df.columns.tolist()
        data = df.values.tolist()

        result_data = [headers] + data

        # Analyze and recommend suppliers based on brands and product names
        recommended_suppliers = []
        try:
            schema = build_sheet_schema(result_data)
            cols = schema.get("item_columns") or {}
            brand_col = cols.get("brand")
            name_col = cols.get("name")

            # Collect unique brands and product names
            brands = set()
            product_names = set()

            for row in result_data[1:]:  # Skip header row
                if not isinstance(row, list):
                    continue

                # Extract brand
                if isinstance(brand_col, int) and brand_col < len(row):
                    brand = row[brand_col]
                    if brand and str(brand).strip() and str(brand).strip().lower() != "none":
                        brands.add(str(brand).strip())

                # Extract product name
                if isinstance(name_col, int) and name_col < len(row):
                    name = row[name_col]
                    if name and str(name).strip() and str(name).strip().lower() != "none":
                        product_names.add(str(name).strip())

            # Search suppliers by brands and product names
            supplier_service = SupplierService(db)
            seen_suppliers = set()

            # Search by brands
            for brand in brands:
                results = supplier_service.search_suppliers(brand, limit=3)
                for supplier in results:
                    if supplier.id not in seen_suppliers:
                        seen_suppliers.add(supplier.id)
                        recommended_suppliers.append({
                            "company_name": supplier.company_name,
                            "contact_name": supplier.contact_name,
                            "contact_phone": supplier.contact_phone,
                            "match_reason": f"鍝佺墝鍖归厤: {brand}",
                            "quote_count": supplier.quote_count,
                            "last_quote_date": supplier.last_quote_date.isoformat() if supplier.last_quote_date else None
                        })

            # Limit to top 10 recommendations
            recommended_suppliers = recommended_suppliers[:10]

        except Exception as e:
            logger.warning("Failed to analyze suppliers from uploaded file", exc_info=e)
            # Don't fail the upload if supplier analysis fails

        return {
            "data": result_data,
            "recommended_suppliers": recommended_suppliers
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")




