from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from typing import List, Optional
from sqlalchemy.orm import Session
from ..models.types import ChatRequest, ChatResponse, UpdateAction
from ..models.database import get_db, init_db, User
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
import json
import pandas as pd
import io
import re

router = APIRouter()

# Initialize database on startup
init_db()

def get_sheet_state_summary(sheet_data):
    if not sheet_data or len(sheet_data) < 2 or not isinstance(sheet_data[0], list):
        return "空"

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
        price_idx = slot_map.get("单价")
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
        bkey = brand or "未填品牌"
        stat = per_brand.setdefault(bkey, {"items": 0, "got": 0, "total": 0})
        stat["items"] += 1
        stat["got"] += got
        stat["total"] += total

        base = f"行{i}: {name or '未填名称'}"
        if brand:
            base += f" | 品牌:{brand}"
        if model:
            base += f" | 型号:{model}"
        base += f" | 已询:{got}/{total}"
        detail_parts.append(base)
        if len(detail_parts) >= 12:
            break

    brand_parts = []
    for brand, stat in sorted(per_brand.items(), key=lambda kv: (-kv[1]["items"], kv[0])):
        brand_parts.append(f"{brand} {stat['items']}项 已询{stat['got']}/{stat['total']}")
        if len(brand_parts) >= 6:
            break

    slot_text = f"槽位数:{len(slot_nums)}"
    brand_text = "；".join(brand_parts) if brand_parts else "无"
    detail_text = "；".join(detail_parts) if detail_parts else "无"
    return f"{slot_text} | 品牌汇总:{brand_text} | 明细:{detail_text}"

def get_pending_summary(sheet_data):
    summary = []
    if not sheet_data or len(sheet_data) < 2:
        return "空"

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
            summary.append(f"行{i}: {label} ({spec_text})")
        else:
            summary.append(f"行{i}: {label}")
        if i >= 8:
            break
    if not summary and headers:
        return "空"
    return "; ".join(summary) if summary else "空"


def build_candidate_rows_summary(sheet_data, rows: list) -> str:
    if not sheet_data or not rows:
        return "无"
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
        text = f"行{r}: {name}"
        if brand:
            text += f" | 品牌: {brand}"
        if spec:
            text += f" | 规格: {spec}"
        parts.append(text)
    return "; ".join(parts) if parts else "无"


def extract_models_from_message(message: str, sheet_data: list) -> list:
    """从用户消息中提取可能的型号"""
    if not message or not sheet_data or len(sheet_data) < 2:
        return []

    # 获取表格中所有的型号
    schema = build_sheet_schema(sheet_data)
    cols = schema.get("item_columns") or {}
    model_col = cols.get("model")

    if not isinstance(model_col, int):
        return []

    # 提取表格中的所有型号
    table_models = []
    for row in sheet_data[1:]:
        if isinstance(row, list) and model_col < len(row):
            model = row[model_col]
            if model and str(model).strip():
                table_models.append(str(model).strip())

    # 从消息中查找可能的型号（使用模糊匹配）
    potential_models = []
    words = re.split(r'[\s,，、]+', message)

    for word in words:
        word = word.strip()
        if not word or len(word) < 3:
            continue
        # 检查是否与表格中的型号相似
        for table_model in table_models:
            from ..services.sheet_schema import fuzzy_match_score
            score = fuzzy_match_score(word, table_model)
            if score >= 70:  # 相似度阈值
                if word not in potential_models:
                    potential_models.append(word)
                break

    return potential_models


def extract_brand_from_message(message: str, sheet_data: list) -> Optional[str]:
    """从用户消息中提取品牌"""
    if not message or not sheet_data or len(sheet_data) < 2:
        return None

    # 获取表格中所有的品牌
    schema = build_sheet_schema(sheet_data)
    cols = schema.get("item_columns") or {}
    brand_col = cols.get("brand")

    if not isinstance(brand_col, int):
        return None

    # 提取表格中的所有品牌
    table_brands = set()
    for row in sheet_data[1:]:
        if isinstance(row, list) and brand_col < len(row):
            brand = row[brand_col]
            if brand and str(brand).strip():
                table_brands.add(str(brand).strip())

    # 从消息中查找品牌
    for brand in table_brands:
        if brand in message:
            return brand

    return None


def build_smart_context(message: str, sheet_data: list, max_rows: int = 50) -> dict:
    """
    构建智能上下文注入数据

    Args:
        message: 用户消息
        sheet_data: 表格数据
        max_rows: 最多注入的行数

    Returns:
        包含品牌上下文和相关产品列表的字典
    """
    if not sheet_data or len(sheet_data) < 2:
        return {"brand_context": None, "relevant_rows": [], "total_matched": 0}

    # 1. 提取品牌和型号
    brand_context = extract_brand_from_message(message, sheet_data)
    potential_models = extract_models_from_message(message, sheet_data)

    # 2. 使用模糊匹配找到相关行
    relevant_rows_dict = {}  # 使用字典去重，key为行号

    # 2.1 根据提取的型号进行模糊匹配
    for model in potential_models:
        matches = fuzzy_match_rows(
            sheet_data,
            model,
            brand_filter=brand_context,
            threshold=75.0,  # 降低阈值以支持更多变体
            max_results=10
        )
        for match in matches:
            row_num = match["row"]
            if row_num not in relevant_rows_dict:
                relevant_rows_dict[row_num] = match

    # 2.2 如果识别到品牌，补充该品牌的所有产品
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
                        # 添加该品牌的产品
                        relevant_rows_dict[i] = {
                            "row": i,
                            "score": 100.0,  # 品牌匹配给高分
                            "match_field": "品牌",
                            "name": row[cols.get("name")] if isinstance(cols.get("name"), int) and cols.get("name") < len(row) else None,
                            "brand": brand_context,
                            "model": row[cols.get("model")] if isinstance(cols.get("model"), int) and cols.get("model") < len(row) else None,
                            "spec": row[cols.get("spec")] if isinstance(cols.get("spec"), int) and cols.get("spec") < len(row) else None,
                        }

    # 3. 转换为列表并排序
    relevant_rows = list(relevant_rows_dict.values())
    relevant_rows.sort(key=lambda x: (-x["score"], x["row"]))

    # 4. 限制数量
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
        required_fields = [k for k in ("单价", "含税", "含运", "货期") if k in slots.get(slot_num, {})]
    else:
        required_fields = ["单价", "含税", "含运", "货期"]

    has_price_col = any("单价" in (slot or {}) for slot in (slots.values() if isinstance(slots, dict) else []))
    if not has_price_col:
        return ChatResponse(action="ASK", content="当前表格未检测到可写入的报价列（例如：单价1/是否含税1/是否含运1/货期1）。请上传包含报价列的询价表，或调整表头命名。")

    # 使用智能上下文注入
    smart_context = build_smart_context(request.message, sheet_data, max_rows=50)

    summary = get_pending_summary(sheet_data)
    sheet_state_summary = get_sheet_state_summary(sheet_data)
    history_messages = build_history_messages(request.chat_history)

    # 构建相关行的详细信息（用于注入给AI）
    relevant_rows_detail = []
    for row_info in smart_context["relevant_rows"]:
        # 获取该行的报价槽位状态
        row_num = row_info["row"]
        slot_status = []
        for slot_num in sorted(slots.keys())[:3]:  # 最多3个槽位
            slot_map = slots.get(slot_num) or {}
            price_idx = slot_map.get("单价")
            if isinstance(price_idx, int) and row_num - 1 < len(sheet_data):
                row_data = sheet_data[row_num - 1]
                if isinstance(row_data, list) and price_idx < len(row_data):
                    price_val = row_data[price_idx]
                    has_price = price_val is not None and str(price_val).strip() not in ("", "none", "None")
                    slot_status.append(f"槽位{slot_num}{'已填' if has_price else '空'}")

        relevant_rows_detail.append({
            "行号": row_num,
            "品牌": row_info.get("brand"),
            "产品名称": row_info.get("name"),
            "型号": row_info.get("model"),
            "规格": row_info.get("spec"),
            "匹配度": f"{row_info['score']:.0f}%",
            "匹配字段": row_info.get("match_field"),
            "报价状态": ", ".join(slot_status) if slot_status else "无槽位"
        })

    context = {
        "sheet_state_summary": sheet_state_summary,
        "pending_items_summary": summary,
        "headers_preview_json": json.dumps(headers_preview, ensure_ascii=False),
        "writable_fields_json": writable_fields_json,
        "required_fields_json": json.dumps(required_fields, ensure_ascii=False),
        "brand_context": smart_context["brand_context"] or "未识别",
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
            print(f"Supplier lookup error: {e}")

        return {"supplier": None}

    def _web_search_supplier(args: dict) -> dict:
        """网络搜索品牌的供应商信息"""
        brand = args.get("brand")
        if not isinstance(brand, str) or not brand.strip():
            return {"success": False, "message": "品牌名称不能为空"}

        try:
            results = search_suppliers_online(brand.strip(), max_results=5)
            if not results:
                return {
                    "success": False,
                    "message": f"未找到'{brand}'的供应商信息",
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
            print(f"Web search error: {e}")
            return {
                "success": False,
                "message": f"搜索出错：{str(e)}",
                "results": []
            }

    def _web_browse(args: dict) -> dict:
        """使用浏览器访问网页或搜索"""
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
                        "message": f"搜索到 {result['count']} 条结果"
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
                        "message": f"成功访问页面: {result['title']}"
                    }
                else:
                    return {"success": False, "error": result["error"]}

            else:
                return {"success": False, "error": "请提供 url 或 query 参数"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    # ========== 迭代式浏览器工具 ==========
    # 用于存储当前会话的浏览器 session_id
    browser_session = {"id": None}

    def _browser_start(args: dict) -> dict:
        """启动浏览器会话"""
        result = browser_create_session()
        if result["success"]:
            browser_session["id"] = result["session_id"]
        return result

    def _browser_stop(args: dict) -> dict:
        """关闭浏览器会话"""
        if not browser_session["id"]:
            return {"success": False, "error": "没有活动的浏览器会话"}
        result = browser_close_session(browser_session["id"])
        browser_session["id"] = None
        return result

    def _browser_goto(args: dict) -> dict:
        """导航到指定 URL"""
        if not browser_session["id"]:
            # 自动创建会话
            start_result = browser_create_session()
            if not start_result["success"]:
                return start_result
            browser_session["id"] = start_result["session_id"]

        url = args.get("url")
        if not url:
            return {"success": False, "error": "请提供 url 参数"}
        return browser_navigate(browser_session["id"], url)

    def _browser_click_element(args: dict) -> dict:
        """点击页面元素"""
        if not browser_session["id"]:
            return {"success": False, "error": "请先启动浏览器会话"}
        element = args.get("element")
        if not element:
            return {"success": False, "error": "请提供 element 参数"}
        return browser_click(browser_session["id"], element)

    def _browser_input(args: dict) -> dict:
        """在元素中输入文本"""
        if not browser_session["id"]:
            return {"success": False, "error": "请先启动浏览器会话"}
        element = args.get("element")
        text = args.get("text")
        if not element or not text:
            return {"success": False, "error": "请提供 element 和 text 参数"}
        return browser_type(browser_session["id"], element, text)

    def _browser_get_snapshot(args: dict) -> dict:
        """获取当前页面快照"""
        if not browser_session["id"]:
            return {"success": False, "error": "请先启动浏览器会话"}
        return browser_snapshot(browser_session["id"])

    def _browser_scroll_page(args: dict) -> dict:
        """滚动页面"""
        if not browser_session["id"]:
            return {"success": False, "error": "请先启动浏览器会话"}
        direction = args.get("direction", "down")
        return browser_scroll(browser_session["id"], direction)

    def _browser_go_back(args: dict) -> dict:
        """返回上一页"""
        if not browser_session["id"]:
            return {"success": False, "error": "请先启动浏览器会话"}
        return browser_back(browser_session["id"])

    # 定义所有可用工具
    all_tools = {
        "locate_row": (
            {"description": "按物料/品牌/型号或明确行号定位候选行", "args": {"item_name": "str?", "brand": "str?", "model": "str?", "spec": "str?", "target_row": "int?"}},
            _locate_row,
        ),
        "get_row_slot_snapshot": (
            {"description": "获取指定行的slot分组快照", "args": {"row": "int"}},
            _row_snapshot,
        ),
        "supplier_lookup": (
            {"description": "按人名/简称查供应商字符串（一个单元格）", "args": {"name": "str"}},
            _supplier_lookup,
        ),
        "web_search_supplier": (
            {"description": "在互联网上搜索品牌的供应商、代理商、经销商信息。当用户询问某个品牌的供应商，或者数据库中没有该品牌的供应商时使用。", "args": {"brand": "str"}},
            _web_search_supplier,
        ),
        "web_browse": (
            {"description": "使用浏览器访问网页提取内容，或使用搜索引擎搜索信息。当需要查看具体网页内容或搜索详细信息时使用。", "args": {"url": "str?", "action": "str?", "query": "str?"}},
            _web_browse,
        ),
        # 迭代式浏览器工具
        "browser_start": (
            {"description": "启动浏览器会话，用于迭代式浏览。返回 session_id。", "args": {}},
            _browser_start,
        ),
        "browser_stop": (
            {"description": "关闭浏览器会话", "args": {}},
            _browser_stop,
        ),
        "browser_goto": (
            {"description": "导航到指定 URL（会自动启动会话）", "args": {"url": "str"}},
            _browser_goto,
        ),
        "browser_click": (
            {"description": "点击页面上的元素。element 参数是元素的描述文本或可访问性标签。", "args": {"element": "str"}},
            _browser_click_element,
        ),
        "browser_input": (
            {"description": "在输入框中输入文本。element 是输入框描述，text 是要输入的内容。", "args": {"element": "str", "text": "str"}},
            _browser_input,
        ),
        "browser_snapshot": (
            {"description": "获取当前页面的可访问性快照，用于了解页面结构和内容。", "args": {}},
            _browser_get_snapshot,
        ),
        "browser_scroll": (
            {"description": "滚动页面。direction 可以是 'up' 或 'down'。", "args": {"direction": "str?"}},
            _browser_scroll_page,
        ),
        "browser_back": (
            {"description": "返回上一页", "args": {}},
            _browser_go_back,
        ),
    }

    # 根据 enabled_tools 参数选择性注册工具
    enabled_tools = request.enabled_tools if request.enabled_tools is not None else list(all_tools.keys())
    for tool_name in enabled_tools:
        if tool_name in all_tools:
            spec, fn = all_tools[tool_name]
            tools.register(tool_name, spec, fn)

    # 调试日志
    import logging
    logging.warning(f"[DEBUG] 已注册工具: {[t['name'] for t in tools.describe()]}")
    logging.warning(f"[DEBUG] 用户消息: {request.message}")

    agent_out = run_two_stage_agent(
        call_llm=call_llm,
        user_message=request.message,
        history_messages=history_messages,
        context=context,
        tools=tools,
        max_tool_steps=3,
    )

    if agent_out.get("action") == "ASK":
        return ChatResponse(action="ASK", content=agent_out.get("content") or "请提供更多信息")

    if agent_out.get("action") == "WRITE":
        updates = agent_out.get("updates")
        if isinstance(updates, list):
            if not updates:
                return ChatResponse(action="ASK", content="LLM未返回可执行的更新列表")

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
                if "单价" in required and (not data_dict.get("price") and data_dict.get("price") != 0):
                    missing.append("单价")
                if "含税" in required and "tax" not in data_dict:
                    missing.append("含税")
                if "含运" in required and "shipping" not in data_dict:
                    missing.append("含运")
                if "货期" in required and not data_dict.get("delivery_time"):
                    missing.append("货期")
                if not data_dict.get("target_row"):
                    missing.append("行号/物料名称")
                if missing:
                    return ChatResponse(action="ASK", content=f"请补充：{', '.join(missing)}")

                lookup_name = data_dict.get("lookup_supplier")
                if lookup_name and not data_dict.get("supplier"):
                    # 尝试从数据库查找供应商
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
                        print(f"Supplier lookup failed: {e}")

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
                return ChatResponse(action="ASK", content="更新列表中没有可执行的更新项")

            # 检查缺失字段并生成提醒
            missing_fields = set()
            for data_dict in updates:
                if not data_dict.get("supplier"):
                    missing_fields.add("供应商")
                if data_dict.get("shipping") is None:
                    missing_fields.add("含运")

            # 生成响应消息
            success_msg = f"✓ 报价已更新 (行 {', '.join(str(r) for r in updated_rows[:10])})"
            if missing_fields:
                reminder = f"\n\n💡 提示：缺少以下信息，如需补充请继续输入：{', '.join(missing_fields)}"
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
            return ChatResponse(action="ASK", content="LLM返回的数据格式不正确")

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
                        text = f"行{row}: {name or ''}"
                        if brand:
                            text += f" | 品牌:{brand}"
                        if model:
                            text += f" | 型号:{model}"
                        if spec:
                            text += f" | 规格:{spec}"
                        lines.append(text)
                    tip = "；".join(lines) if lines else "存在多个候选行"
                    return ChatResponse(action="ASK", content=f"匹配到多个候选，请指定第X行或补充型号/规格：{tip}")

        missing = []
        required = set(required_fields)
        if "单价" in required and (not data_dict.get("price") and data_dict.get("price") != 0):
            missing.append("单价")
        if "含税" in required and "tax" not in data_dict:
            missing.append("含税")
        if "含运" in required and "shipping" not in data_dict:
            missing.append("含运")
        if "货期" in required and not data_dict.get("delivery_time"):
            missing.append("货期")
        if not data_dict.get("target_row"):
            missing.append("行号/物料名称")
        if missing:
            return ChatResponse(action="ASK", content=f"请补充：{', '.join(missing)}")
        
        try:
            lookup_name = data_dict.get("lookup_supplier")
            if lookup_name and not data_dict.get("supplier"):
                # 尝试从数据库查找供应商
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
                    print(f"Supplier lookup failed: {e}")

            field_names = getattr(UpdateAction, "model_fields", None)
            if isinstance(field_names, dict):
                allowed = set(field_names.keys())
            else:
                allowed = set(getattr(UpdateAction, "__fields__", {}).keys())
            cleaned = {k: v for k, v in data_dict.items() if k in allowed}
            update_action = UpdateAction(**cleaned)
            new_sheet = process_update(sheet_data, update_action)

            # 检查缺失字段并生成提醒
            missing_fields = []
            if not update_action.supplier:
                missing_fields.append("供应商")
            if update_action.shipping is None:
                missing_fields.append("含运")

            # 生成响应消息
            success_msg = f"✓ 报价已更新 (行 {update_action.target_row})"
            if missing_fields:
                reminder = f"\n\n💡 提示：缺少以下信息，如需补充请继续输入：{', '.join(missing_fields)}"
                success_msg += reminder

            return ChatResponse(
                action="WRITE",
                content=success_msg,
                data=update_action,
                updated_sheet=new_sheet
            )
        except Exception as e:
            return ChatResponse(action="ASK", content=f"更新表格失败: {str(e)}")

    return ChatResponse(action="ASK", content="未知指令")

# 文件上传大小限制 (10MB)
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
    # 验证文件扩展名
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="仅支持 Excel 文件格式 (.xlsx, .xls)")

    # 验证 MIME 类型
    if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail="文件类型不正确，请上传 Excel 文件")

    try:
        # 读取文件并检查大小
        contents = await file.read()
        if len(contents) > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=400, detail="文件大小超过限制 (最大 10MB)")

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
                            "match_reason": f"品牌匹配: {brand}",
                            "quote_count": supplier.quote_count,
                            "last_quote_date": supplier.last_quote_date.isoformat() if supplier.last_quote_date else None
                        })

            # Limit to top 10 recommendations
            recommended_suppliers = recommended_suppliers[:10]

        except Exception as e:
            print(f"Failed to analyze suppliers: {e}")
            # Don't fail the upload if supplier analysis fails

        return {
            "data": result_data,
            "recommended_suppliers": recommended_suppliers
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")



