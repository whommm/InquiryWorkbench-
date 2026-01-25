from fastapi import APIRouter, HTTPException, UploadFile, File
from ..models.types import ChatRequest, ChatResponse, UpdateAction
from ..services.excel_core import process_update
from ..services.supplier_mock import MOCK_SUPPLIERS
from ..core.llm import call_llm
from ..services.agent_runtime import ToolRegistry, run_two_stage_agent
from ..services.sheet_schema import (
    build_sheet_schema,
    build_writable_fields,
    extract_row_from_message,
    find_candidate_rows,
    locate_rows_by_criteria,
    get_row_slot_snapshot,
)
import json
import pandas as pd
import io

router = APIRouter()

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
async def chat_endpoint(request: ChatRequest):
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

    candidate_rows = find_candidate_rows(sheet_data, request.message, max_candidates=3)
    row_snapshot = None

    summary = get_pending_summary(sheet_data)
    sheet_state_summary = get_sheet_state_summary(sheet_data)
    history_messages = build_history_messages(request.chat_history)
    context = {
        "sheet_state_summary": sheet_state_summary,
        "pending_items_summary": summary,
        "headers_preview_json": json.dumps(headers_preview, ensure_ascii=False),
        "writable_fields_json": writable_fields_json,
        "required_fields_json": json.dumps(required_fields, ensure_ascii=False),
        "candidate_rows_summary": build_candidate_rows_summary(sheet_data, candidate_rows),
        "row_snapshot_json": json.dumps(row_snapshot, ensure_ascii=False) if row_snapshot else "null",
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
        info = MOCK_SUPPLIERS.get(name.strip())
        if not info:
            return {"supplier": None}
        supplier = " ".join([str(info.get("full_name") or "").strip(), str(info.get("contact") or "").strip(), str(info.get("phone") or "").strip()]).strip()
        return {"supplier": supplier or None}

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
                current_sheet = process_update(current_sheet, update_action)
                updated_rows.append(update_action.target_row)

            if not updated_rows:
                return ChatResponse(action="ASK", content="更新列表中没有可执行的更新项")
            return ChatResponse(
                action="WRITE",
                content=f"报价已更新 (行 {', '.join(str(r) for r in updated_rows[:10])})",
                data=updates,
                updated_sheet=current_sheet,
            )

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
            new_sheet = process_update(sheet_data, update_action)
            return ChatResponse(
                action="WRITE",
                content=f"报价已更新 (行 {update_action.target_row})",
                data=update_action,
                updated_sheet=new_sheet
            )
        except Exception as e:
            return ChatResponse(action="ASK", content=f"更新表格失败: {str(e)}")

    return ChatResponse(action="ASK", content="未知指令")

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
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
        
        # Ensure result matches expected structure (optional: validate columns)
        # For now, we trust the uploaded file or just return it as is
        
        result_data = [headers] + data
        
        return {"data": result_data}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")
