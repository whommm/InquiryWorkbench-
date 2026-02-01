from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional
from sqlalchemy.orm import Session
from urllib.parse import quote
from datetime import datetime
from ..models.types import ChatRequest, ChatResponse, UpdateAction
from ..models.database import get_db, init_db, User
from ..services.db_service import DBService
from ..services.supplier_service import SupplierService
from ..services.excel_core import process_update
from ..services.excel_export import export_sheet_to_excel
from ..services.supplier_mock import MOCK_SUPPLIERS
from ..services.web_search import search_suppliers_online, format_search_results
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
import uuid
import re

router = APIRouter()

# Initialize database on startup
init_db()


# Pydantic models for sheet save/load
class SaveSheetRequest(BaseModel):
    id: Optional[str] = None
    name: str
    sheet_data: list
    chat_history: list


class SheetListItem(BaseModel):
    id: str
    name: str
    item_count: int
    completion_rate: float
    created_at: str
    updated_at: str


class RecommendRequest(BaseModel):
    product_name: str = Field("", max_length=200, description="产品名称")
    spec: Optional[str] = Field("", max_length=500, description="规格型号")
    brand: Optional[str] = Field("", max_length=100, description="品牌")
    limit: Optional[int] = Field(5, ge=1, le=20, description="返回数量限制")


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
        return {"brand_context": None, "relevant_rows": []}

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
    print(f"[DEBUG] ========== 开始处理chat请求 ==========")
    print(f"[DEBUG] 用户消息: {request.message}")
    sheet_data = request.current_sheet_data or []
    print(f"[DEBUG] 表格数据行数: {len(sheet_data)}")
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

    tools.register(
        "locate_row",
        {
            "description": "按物料/品牌/型号或明确行号定位候选行",
            "args": {"item_name": "str?", "brand": "str?", "model": "str?", "spec": "str?", "target_row": "int?"},
        },
        _locate_row,
    )
    tools.register(
        "get_row_slot_snapshot",
        {"description": "获取指定行的slot分组快照", "args": {"row": "int"}},
        _row_snapshot,
    )
    tools.register(
        "supplier_lookup",
        {"description": "按人名/简称查供应商字符串（一个单元格）", "args": {"name": "str"}},
        _supplier_lookup,
    )
    tools.register(
        "web_search_supplier",
        {
            "description": "在互联网上搜索品牌的供应商、代理商、经销商信息。当用户询问某个品牌的供应商，或者数据库中没有该品牌的供应商时使用。",
            "args": {"brand": "str"}
        },
        _web_search_supplier,
    )

    agent_out = run_two_stage_agent(
        call_llm=call_llm,
        user_message=request.message,
        history_messages=history_messages,
        context=context,
        tools=tools,
        max_tool_steps=3,
    )

    print(f"[DEBUG] Agent返回结果:")
    print(f"[DEBUG] - action: {agent_out.get('action')}")
    print(f"[DEBUG] - updates存在: {agent_out.get('updates') is not None}")
    if agent_out.get('updates'):
        print(f"[DEBUG] - updates数量: {len(agent_out.get('updates'))}")
        print(f"[DEBUG] - updates内容: {agent_out.get('updates')}")

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
                    info = MOCK_SUPPLIERS.get(str(lookup_name).strip())
                    if info:
                        supplier = " ".join(
                            [
                                str(info.get("full_name") or "").strip(),
                                str(info.get("contact") or "").strip(),
                                str(info.get("phone") or "").strip(),
                            ]
                        ).strip()
                        if supplier:
                            data_dict["supplier"] = supplier

                field_names = getattr(UpdateAction, "model_fields", None)
                if isinstance(field_names, dict):
                    allowed = set(field_names.keys())
                else:
                    allowed = set(getattr(UpdateAction, "__fields__", {}).keys())
                cleaned = {k: v for k, v in data_dict.items() if k in allowed}
                print(f"[DEBUG] 批量更新 - data_dict: {data_dict}")
                print(f"[DEBUG] 批量更新 - cleaned: {cleaned}")
                update_action = UpdateAction(**cleaned)
                print(f"[DEBUG] 批量更新 - update_action.price: {update_action.price}, type: {type(update_action.price)}")
                current_sheet = process_update(current_sheet, update_action, db, user_id=current_user.id)
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

            print(f"[DEBUG] 准备返回响应:")
            print(f"[DEBUG] - action: WRITE")
            print(f"[DEBUG] - content: {success_msg}")
            print(f"[DEBUG] - updated_rows: {updated_rows}")
            print(f"[DEBUG] - current_sheet行数: {len(current_sheet)}")
            print(f"[DEBUG] - current_sheet第一行: {current_sheet[0] if current_sheet else 'None'}")
            print(f"[DEBUG] - updates数量: {len(updates)}")

            # 打印更新的行的详细信息
            for row_num in updated_rows[:3]:  # 只打印前3行
                if 0 < row_num <= len(current_sheet):
                    row_data = current_sheet[row_num - 1]
                    print(f"[DEBUG] - 行{row_num}数据（前10列）: {row_data[:10] if isinstance(row_data, list) else row_data}")

            response = ChatResponse(
                action="WRITE",
                content=success_msg,
                data=updates,
                updated_sheet=current_sheet,
            )
            print(f"[DEBUG] ChatResponse对象创建成功")
            print(f"[DEBUG] response.updated_sheet行数: {len(response.updated_sheet) if response.updated_sheet else 'None'}")
            print(f"[DEBUG] response.content长度: {len(response.content) if response.content else 0}")
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
                info = MOCK_SUPPLIERS.get(str(lookup_name).strip())
                if info:
                    supplier = " ".join(
                        [
                            str(info.get("full_name") or "").strip(),
                            str(info.get("contact") or "").strip(),
                            str(info.get("phone") or "").strip(),
                        ]
                    ).strip()
                    if supplier:
                        data_dict["supplier"] = supplier

            field_names = getattr(UpdateAction, "model_fields", None)
            if isinstance(field_names, dict):
                allowed = set(field_names.keys())
            else:
                allowed = set(getattr(UpdateAction, "__fields__", {}).keys())
            cleaned = {k: v for k, v in data_dict.items() if k in allowed}
            update_action = UpdateAction(**cleaned)
            new_sheet = process_update(sheet_data, update_action, db, user_id=current_user.id)

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

@router.post("/upload")
async def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Invalid file format. Please upload an Excel file.")

    try:
        contents = await file.read()
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


@router.post("/sheets/save")
async def save_sheet(
    request: SaveSheetRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Save or update an inquiry sheet"""
    try:
        # Generate ID if not provided
        sheet_id = request.id or str(uuid.uuid4())

        # Calculate metadata
        schema = build_sheet_schema(request.sheet_data)
        slots = schema.get("slots") or {}
        slot_count = len(slots)

        item_count = len(request.sheet_data) - 1 if len(request.sheet_data) > 1 else 0

        # Calculate completion rate
        total_cells = item_count * slot_count
        filled_cells = 0

        if total_cells > 0:
            for row in request.sheet_data[1:]:
                if isinstance(row, list):
                    for slot_num in slots.keys():
                        slot_map = slots.get(slot_num) or {}
                        price_idx = slot_map.get("单价")
                        if isinstance(price_idx, int) and price_idx < len(row):
                            val = row[price_idx]
                            if val and str(val).strip() and str(val).strip().lower() != "none":
                                filled_cells += 1

        completion_rate = filled_cells / total_cells if total_cells > 0 else 0.0

        # Save to database
        db_service = DBService(db)
        sheet = db_service.save_sheet(
            sheet_id=sheet_id,
            name=request.name,
            sheet_data=request.sheet_data,
            chat_history=request.chat_history,
            user_id=current_user.id,
            item_count=item_count,
            completion_rate=completion_rate
        )

        return {
            "id": sheet.id,
            "message": "保存成功",
            "completion_rate": completion_rate
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save sheet: {str(e)}")


@router.get("/sheets/list")
async def list_sheets(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get list of saved inquiry sheets"""
    try:
        db_service = DBService(db)
        sheets = db_service.list_sheets(user_id=current_user.id, limit=limit, offset=offset)

        result = []
        for sheet in sheets:
            result.append({
                "id": sheet.id,
                "name": sheet.name,
                "item_count": sheet.item_count,
                "completion_rate": sheet.completion_rate,
                "created_at": sheet.created_at.isoformat() if sheet.created_at else "",
                "updated_at": sheet.updated_at.isoformat() if sheet.updated_at else ""
            })

        return {"sheets": result, "total": len(result)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list sheets: {str(e)}")


@router.get("/sheets/{sheet_id}")
async def get_sheet(
    sheet_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a single inquiry sheet by ID"""
    try:
        db_service = DBService(db)
        sheet = db_service.get_sheet(sheet_id, user_id=current_user.id)

        if not sheet:
            raise HTTPException(status_code=404, detail="Sheet not found")

        return {
            "id": sheet.id,
            "name": sheet.name,
            "sheet_data": sheet.sheet_data,
            "chat_history": sheet.chat_history,
            "item_count": sheet.item_count,
            "completion_rate": sheet.completion_rate,
            "created_at": sheet.created_at.isoformat() if sheet.created_at else "",
            "updated_at": sheet.updated_at.isoformat() if sheet.updated_at else ""
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get sheet: {str(e)}")


@router.delete("/sheets/{sheet_id}")
async def delete_sheet(
    sheet_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete an inquiry sheet"""
    try:
        db_service = DBService(db)
        success = db_service.delete_sheet(sheet_id, user_id=current_user.id)

        if not success:
            raise HTTPException(status_code=404, detail="Sheet not found")

        return {"message": "删除成功"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete sheet: {str(e)}")


@router.get("/sheets/{sheet_id}/export")
async def export_sheet(
    sheet_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Export an inquiry sheet to Excel"""
    try:
        db_service = DBService(db)
        sheet = db_service.get_sheet(sheet_id, user_id=current_user.id)

        if not sheet:
            raise HTTPException(status_code=404, detail="Sheet not found")

        # Generate Excel file (returns BytesIO)
        excel_file = export_sheet_to_excel(sheet.sheet_data, f"{sheet.name}.xlsx")

        # Encode filename for Content-Disposition header (RFC 5987)
        encoded_filename = quote(f"{sheet.name}.xlsx")

        # Return as streaming response
        return StreamingResponse(
            excel_file,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export sheet: {str(e)}")


# Supplier API endpoints
@router.get("/suppliers/search")
async def search_suppliers(q: str, limit: int = 10, db: Session = Depends(get_db)):
    """Search suppliers by name, phone, or contact"""
    try:
        supplier_service = SupplierService(db)
        suppliers = supplier_service.search_suppliers(q, limit=limit)

        result = []
        for s in suppliers:
            result.append({
                "id": s.id,
                "company_name": s.company_name,
                "contact_phone": s.contact_phone,
                "contact_name": s.contact_name,
                "owner": s.owner,
                "tags": s.tags or [],
                "quote_count": s.quote_count,
                "last_quote_date": s.last_quote_date.isoformat() if s.last_quote_date else None
            })

        return {"suppliers": result}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to search suppliers: {str(e)}")


@router.get("/suppliers/list")
async def list_suppliers_endpoint(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    """Get list of suppliers"""
    try:
        supplier_service = SupplierService(db)
        suppliers = supplier_service.list_suppliers(limit=limit, offset=offset)

        result = []
        for s in suppliers:
            # 查询创建者信息
            created_by_name = None
            if s.created_by:
                creator = db.query(User).filter(User.id == s.created_by).first()
                if creator:
                    created_by_name = creator.display_name or creator.username

            result.append({
                "id": s.id,
                "company_name": s.company_name,
                "contact_phone": s.contact_phone,
                "contact_name": s.contact_name,
                "owner": s.owner,
                "tags": s.tags or [],
                "quote_count": s.quote_count,
                "last_quote_date": s.last_quote_date.isoformat() if s.last_quote_date else None,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "created_by_name": created_by_name
            })

        return {"suppliers": result, "total": len(result)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list suppliers: {str(e)}")


@router.delete("/suppliers/{supplier_id}")
async def delete_supplier_endpoint(supplier_id: int, db: Session = Depends(get_db)):
    """Delete a supplier"""
    try:
        supplier_service = SupplierService(db)
        success = supplier_service.delete_supplier(supplier_id)

        if not success:
            raise HTTPException(status_code=404, detail="Supplier not found")

        return {"message": "删除成功"}

    except HTTPException:
        raise


@router.post("/suppliers/recommend")
async def recommend_suppliers_endpoint(request: RecommendRequest, db: Session = Depends(get_db)):
    """Recommend top suppliers for a specific product"""
    try:
        supplier_service = SupplierService(db)
        recommendations = supplier_service.recommend_suppliers(
            product_name=request.product_name,
            spec=request.spec or "",
            brand=request.brand or "",
            limit=request.limit or 5
        )

        # Format response
        result = []

        # 批量查询创建者信息
        creator_ids = [rec.get("created_by") for rec in recommendations if rec.get("created_by")]
        creators = {}
        if creator_ids:
            from ..models.database import User
            users = db.query(User).filter(User.id.in_(creator_ids)).all()
            creators = {u.id: u.display_name or u.username for u in users}

        for idx, rec in enumerate(recommendations, start=1):
            # Calculate star rating (1-5 stars based on recommendation score)
            star_rating = max(1, min(5, int(rec["recommendation_score"] * 5) + 1))

            # Format last quote date
            days_ago = (datetime.utcnow() - rec["last_quote_date"]).days
            if days_ago == 0:
                last_quote_text = "今天"
            elif days_ago == 1:
                last_quote_text = "1天前"
            elif days_ago < 30:
                last_quote_text = f"{days_ago}天前"
            elif days_ago < 365:
                last_quote_text = f"{days_ago // 30}个月前"
            else:
                last_quote_text = f"{days_ago // 365}年前"

            result.append({
                "rank": idx,
                "supplier_id": rec.get("supplier_id"),
                "company_name": rec.get("company_name", rec["supplier_name"]),
                "contact_name": rec.get("contact_name"),
                "contact_phone": rec.get("contact_phone"),
                "quote_count": rec["quote_count"],
                "avg_price": round(rec["avg_price"], 2),
                "min_price": round(rec["min_price"], 2),
                "max_price": round(rec["max_price"], 2),
                "last_quote_date": rec["last_quote_date"].isoformat(),
                "last_quote_text": last_quote_text,
                "star_rating": star_rating,
                "recommendation_score": round(rec["recommendation_score"], 3),
                "brands": rec["brands"],
                "products": rec.get("products", []),
                "delivery_times": rec.get("delivery_times", [])[:3],
                "created_by_name": creators.get(rec.get("created_by"))
            })

        return {
            "recommendations": result,
            "total": len(result),
            "query": {
                "product_name": request.product_name,
                "spec": request.spec,
                "brand": request.brand
            }
        }

    except Exception as e:
        print(f"[ERROR] Failed to recommend suppliers: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to recommend suppliers: {str(e)}")
