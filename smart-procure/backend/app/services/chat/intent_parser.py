from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ...models.columns import (
    REQUIRED_QUOTE_FIELDS,
    SLOT_FIELD_BRAND,
    SLOT_FIELD_PRICE,
)
from ...models.types import ChatRequest
from ..sheet_schema import (
    build_sheet_schema,
    build_writable_fields,
    fuzzy_match_rows,
    fuzzy_match_score,
)


@dataclass
class ChatIntentContext:
    sheet_data: List[List[Any]]
    schema: Dict[str, Any]
    required_fields: List[str]
    history_messages: Optional[List[Dict[str, str]]]
    context: Dict[str, Any]
    ask_message: Optional[str] = None


def _safe_cell(row: List[Any], index: Optional[int]) -> str:
    if not isinstance(index, int):
        return ""
    if index < 0 or index >= len(row):
        return ""
    value = row[index]
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "none" else text


def _has_price(row: List[Any], slots: Dict[int, Dict[str, int]], slot_num: int) -> bool:
    slot_map = slots.get(slot_num) or {}
    price_idx = slot_map.get(SLOT_FIELD_PRICE)
    if not isinstance(price_idx, int):
        return False
    if price_idx < 0 or price_idx >= len(row):
        return False
    value = row[price_idx]
    if value is None:
        return False
    text = str(value).strip()
    return text != "" and text.lower() != "none"


def get_sheet_state_summary(sheet_data: List[List[Any]]) -> str:
    if not sheet_data or len(sheet_data) < 2 or not isinstance(sheet_data[0], list):
        return "empty"

    schema = build_sheet_schema(sheet_data)
    slots = schema.get("slots") or {}
    cols = schema.get("item_columns") or {}
    name_col = cols.get("name")
    brand_col = cols.get("brand")
    model_col = cols.get("model")

    slot_nums = sorted([int(k) for k in slots.keys() if isinstance(k, int)])
    if not slot_nums:
        slot_nums = [1]

    per_brand: Dict[str, Dict[str, int]] = {}
    detail_parts: List[str] = []

    for i, row in enumerate(sheet_data[1:], start=2):
        if not isinstance(row, list):
            continue

        name = _safe_cell(row, name_col)
        brand = _safe_cell(row, brand_col)
        model = _safe_cell(row, model_col)
        if not name and not brand and not model:
            continue

        got = sum(1 for slot_num in slot_nums if _has_price(row, slots, slot_num))
        total = len(slot_nums)
        brand_key = brand or "未填品牌"
        stat = per_brand.setdefault(brand_key, {"items": 0, "got": 0, "total": 0})
        stat["items"] += 1
        stat["got"] += got
        stat["total"] += total

        base = f"row {i}: {name or 'N/A'}"
        if brand:
            base += f" | 品牌:{brand}"
        if model:
            base += f" | 型号:{model}"
        base += f" | 已询:{got}/{total}"
        detail_parts.append(base)
        if len(detail_parts) >= 12:
            break

    brand_parts: List[str] = []
    for brand, stat in sorted(per_brand.items(), key=lambda kv: (-kv[1]["items"], kv[0])):
        brand_parts.append(f"{brand} {stat['items']}项 已询{stat['got']}/{stat['total']}")
        if len(brand_parts) >= 6:
            break

    slot_text = f"槽位数:{len(slot_nums)}"
    brand_text = " | ".join(brand_parts) if brand_parts else "none"
    detail_text = " | ".join(detail_parts) if detail_parts else "none"
    return f"{slot_text} | brands:{brand_text} | details:{detail_text}"


def get_pending_summary(sheet_data: List[List[Any]]) -> str:
    if not sheet_data or len(sheet_data) < 2:
        return "empty"

    schema = build_sheet_schema(sheet_data)
    headers = schema.get("headers") or []
    cols = schema.get("item_columns") or {}
    name_col = cols.get("name")
    spec_col = cols.get("spec")

    summary: List[str] = []
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
        summary.append(f"row {i}: {label}" + (f" ({spec_text})" if spec_text.strip() else ""))
        if i >= 8:
            break

    if not summary and headers:
        return "empty"
    return "; ".join(summary) if summary else "empty"


def extract_models_from_message(message: str, sheet_data: List[List[Any]]) -> List[str]:
    if not message or not sheet_data or len(sheet_data) < 2:
        return []

    schema = build_sheet_schema(sheet_data)
    cols = schema.get("item_columns") or {}
    model_col = cols.get("model")
    if not isinstance(model_col, int):
        return []

    table_models: List[str] = []
    for row in sheet_data[1:]:
        if isinstance(row, list) and model_col < len(row):
            model = row[model_col]
            if model and str(model).strip():
                table_models.append(str(model).strip())

    potential_models: List[str] = []
    words = re.split(r"[\s,，、；;]+", message)
    for word in words:
        token = word.strip()
        if len(token) < 3:
            continue
        for table_model in table_models:
            score = fuzzy_match_score(token, table_model)
            if score >= 70:
                if token not in potential_models:
                    potential_models.append(token)
                break
    return potential_models


def extract_brand_from_message(message: str, sheet_data: List[List[Any]]) -> Optional[str]:
    if not message or not sheet_data or len(sheet_data) < 2:
        return None

    schema = build_sheet_schema(sheet_data)
    cols = schema.get("item_columns") or {}
    brand_col = cols.get("brand")
    if not isinstance(brand_col, int):
        return None

    table_brands = set()
    for row in sheet_data[1:]:
        if isinstance(row, list) and brand_col < len(row):
            brand = row[brand_col]
            if brand and str(brand).strip():
                table_brands.add(str(brand).strip())

    for brand in table_brands:
        if brand in message:
            return brand
    return None


def build_smart_context(message: str, sheet_data: List[List[Any]], max_rows: int = 50) -> Dict[str, Any]:
    if not sheet_data or len(sheet_data) < 2:
        return {"brand_context": None, "relevant_rows": [], "total_matched": 0}

    brand_context = extract_brand_from_message(message, sheet_data)
    potential_models = extract_models_from_message(message, sheet_data)
    relevant_rows_dict: Dict[int, Dict[str, Any]] = {}

    for model in potential_models:
        matches = fuzzy_match_rows(
            sheet_data,
            model,
            brand_filter=brand_context,
            threshold=75.0,
            max_results=10,
        )
        for match in matches:
            row_num = match["row"]
            if row_num not in relevant_rows_dict:
                relevant_rows_dict[row_num] = match

    # 只有当用户消息中没有具体产品名称时，才按品牌匹配所有产品
    # 如果已经有模糊匹配的结果，说明用户提到了具体产品，不需要按品牌扩展
    if brand_context and not relevant_rows_dict:
        schema = build_sheet_schema(sheet_data)
        cols = schema.get("item_columns") or {}
        brand_col = cols.get("brand")
        if isinstance(brand_col, int):
            for i, row in enumerate(sheet_data[1:], start=2):
                if not isinstance(row, list) or brand_col >= len(row):
                    continue
                row_brand = row[brand_col]
                if row_brand and str(row_brand).strip() == brand_context and i not in relevant_rows_dict:
                    relevant_rows_dict[i] = {
                        "row": i,
                        "score": 100.0,
                        "match_field": SLOT_FIELD_BRAND,
                        "name": row[cols.get("name")] if isinstance(cols.get("name"), int) and cols.get("name") < len(row) else None,
                        "brand": brand_context,
                        "model": row[cols.get("model")] if isinstance(cols.get("model"), int) and cols.get("model") < len(row) else None,
                        "spec": row[cols.get("spec")] if isinstance(cols.get("spec"), int) and cols.get("spec") < len(row) else None,
                    }

    relevant_rows = list(relevant_rows_dict.values())
    relevant_rows.sort(key=lambda x: (-x["score"], x["row"]))
    relevant_rows = relevant_rows[:max_rows]
    return {
        "brand_context": brand_context,
        "relevant_rows": relevant_rows,
        "total_matched": len(relevant_rows),
    }


def build_history_messages(
    chat_history: Optional[List[Any]],
    max_messages: int = 12,
    max_chars_per_message: int = 1200,
) -> Optional[List[Dict[str, str]]]:
    if not chat_history:
        return None

    items: List[Dict[str, str]] = []
    for m in chat_history:
        role = getattr(m, "role", None)
        content = getattr(m, "content", None)
        if role not in ("user", "assistant"):
            continue
        if not isinstance(content, str):
            continue
        text = content.strip()
        if not text:
            continue
        if len(text) > max_chars_per_message:
            text = text[:max_chars_per_message]
        items.append({"role": role, "content": text})

    return items[-max_messages:] if items else None


def infer_required_fields(schema: Dict[str, Any]) -> List[str]:
    slots = schema.get("slots") or {}
    first_slot_num = sorted(slots.keys())[0] if slots else None
    if first_slot_num is not None:
        first_slot = slots.get(first_slot_num, {})
        return [field for field in REQUIRED_QUOTE_FIELDS if field in first_slot]
    return list(REQUIRED_QUOTE_FIELDS)


def _build_relevant_rows_detail(
    schema: Dict[str, Any],
    sheet_data: List[List[Any]],
    smart_context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    slots = schema.get("slots") or {}
    relevant_rows_detail: List[Dict[str, Any]] = []
    for row_info in smart_context["relevant_rows"]:
        row_num = row_info["row"]
        slot_status = []
        for slot_num in sorted(slots.keys())[:3]:
            slot_map = slots.get(slot_num) or {}
            price_idx = slot_map.get(SLOT_FIELD_PRICE)
            if isinstance(price_idx, int) and row_num - 1 < len(sheet_data):
                row_data = sheet_data[row_num - 1]
                if isinstance(row_data, list) and price_idx < len(row_data):
                    price_val = row_data[price_idx]
                    has_price = price_val is not None and str(price_val).strip() not in ("", "none", "None")
                    slot_status.append(f"slot {slot_num} {'filled' if has_price else 'empty'}")

        relevant_rows_detail.append(
            {
                "行号": row_num,
                "品牌": row_info.get("brand"),
                "产品名称": row_info.get("name"),
                "型号": row_info.get("model"),
                "规格": row_info.get("spec"),
                "match_score": f"{row_info['score']:.0f}%",
                "匹配字段": row_info.get("match_field"),
                "slot_status": ", ".join(slot_status) if slot_status else "no slots",
            }
        )

    return relevant_rows_detail


def parse_chat_intent(request: ChatRequest) -> ChatIntentContext:
    sheet_data = request.current_sheet_data or []
    schema = build_sheet_schema(sheet_data)
    slots = schema.get("slots") or {}
    required_fields = infer_required_fields(schema)

    has_price_col = any(SLOT_FIELD_PRICE in (slot or {}) for slot in (slots.values() if isinstance(slots, dict) else []))
    if not has_price_col:
        return ChatIntentContext(
            sheet_data=sheet_data,
            schema=schema,
            required_fields=required_fields,
            history_messages=build_history_messages(request.chat_history),
            context={},
            ask_message="No writable quote columns detected in this sheet. Please upload a valid inquiry sheet template.",
        )

    headers = schema.get("headers") or []
    headers_preview = [str(h) for h in headers[:40]]
    writable_fields_json = json.dumps(build_writable_fields(schema), ensure_ascii=False)

    smart_context = build_smart_context(request.message, sheet_data, max_rows=50)
    summary = get_pending_summary(sheet_data)
    sheet_state_summary = get_sheet_state_summary(sheet_data)
    history_messages = build_history_messages(request.chat_history)
    relevant_rows_detail = _build_relevant_rows_detail(schema, sheet_data, smart_context)

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

    return ChatIntentContext(
        sheet_data=sheet_data,
        schema=schema,
        required_fields=required_fields,
        history_messages=history_messages,
        context=context,
    )
