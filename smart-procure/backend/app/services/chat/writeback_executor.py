from __future__ import annotations

from typing import Any, Dict, List, Sequence

from sqlalchemy.orm import Session

from ...models.columns import (
    SLOT_FIELD_DELIVERY,
    SLOT_FIELD_PRICE,
    SLOT_FIELD_SHIPPING,
    SLOT_FIELD_TAX,
)
from ...models.types import ChatResponse, UpdateAction
from ..excel_core import process_update
from ..sheet_schema import extract_row_from_message
from ..supplier_service import SupplierService
from .result_explainer import (
    build_missing_fields_prompt,
    build_multiple_candidates_prompt,
    build_write_success_message,
)

ROW_HINT_FIELD = "行号/定位信息"


def _collect_missing_fields(data_dict: Dict[str, Any], required_fields: Sequence[str]) -> List[str]:
    missing: List[str] = []
    required = set(required_fields)
    if SLOT_FIELD_PRICE in required and (not data_dict.get("price") and data_dict.get("price") != 0):
        missing.append(SLOT_FIELD_PRICE)
    if SLOT_FIELD_TAX in required and "tax" not in data_dict:
        missing.append(SLOT_FIELD_TAX)
    if SLOT_FIELD_SHIPPING in required and "shipping" not in data_dict:
        missing.append(SLOT_FIELD_SHIPPING)
    if SLOT_FIELD_DELIVERY in required and not data_dict.get("delivery_time"):
        missing.append(SLOT_FIELD_DELIVERY)
    if not data_dict.get("target_row"):
        missing.append(ROW_HINT_FIELD)
    return missing


def _try_fill_supplier(data_dict: Dict[str, Any], db: Session, logger, scope: str) -> None:
    lookup_name = data_dict.get("lookup_supplier")
    if not lookup_name or data_dict.get("supplier"):
        return
    try:
        supplier_service = SupplierService(db)
        results = supplier_service.search_suppliers(str(lookup_name).strip(), limit=1)
        if results:
            supplier_info = " ".join(
                [
                    results[0].company_name or "",
                    results[0].contact_name or "",
                    results[0].contact_phone or "",
                ]
            ).strip()
            if supplier_info:
                data_dict["supplier"] = supplier_info
    except Exception as exc:
        logger.warning("Supplier lookup failed during %s update", scope, exc_info=exc)


def _allowed_update_fields() -> set:
    field_names = getattr(UpdateAction, "model_fields", None)
    if isinstance(field_names, dict):
        return set(field_names.keys())
    return set(getattr(UpdateAction, "__fields__", {}).keys())


def _build_update_action(payload: Dict[str, Any]) -> UpdateAction:
    allowed = _allowed_update_fields()
    cleaned = {k: v for k, v in payload.items() if k in allowed}
    return UpdateAction(**cleaned)


def _resolve_ambiguous_row_prompt(data_dict: Dict[str, Any], tool_results: List[Dict[str, Any]]) -> str | None:
    locate = None
    for tr in reversed(tool_results if isinstance(tool_results, list) else []):
        if isinstance(tr, dict) and tr.get("ok") and tr.get("tool") == "locate_row":
            locate = tr
            break
    if not locate:
        return None

    result = locate.get("result") or {}
    candidates = result.get("candidates") or []
    ambiguous = bool(result.get("ambiguous"))
    if (ambiguous or (isinstance(candidates, list) and len(candidates) > 1)) and not data_dict.get("target_row"):
        return build_multiple_candidates_prompt(candidates)
    return None


def _build_missing_fields_hint_from_updates(updates: Sequence[Dict[str, Any]]) -> List[str]:
    missing_fields = set()
    for data_dict in updates:
        if not data_dict.get("supplier"):
            missing_fields.add("supplier")
        if data_dict.get("shipping") is None:
            missing_fields.add(SLOT_FIELD_SHIPPING)
    return list(missing_fields)


def execute_write_action(
    agent_out: Dict[str, Any],
    user_message: str,
    sheet_data: List[List[Any]],
    required_fields: Sequence[str],
    db: Session,
    logger,
) -> ChatResponse:
    updates = agent_out.get("updates")
    explicit_row = extract_row_from_message(user_message)

    if isinstance(updates, list):
        if not updates:
            return ChatResponse(action="ASK", content="LLM did not return executable updates.")

        current_sheet = sheet_data
        updated_rows: List[int] = []
        applied_payloads: List[Dict[str, Any]] = []

        for item in updates[:50]:
            if not isinstance(item, dict):
                continue

            data_dict = dict(item)
            if not data_dict.get("target_row") and explicit_row:
                data_dict["target_row"] = explicit_row

            missing = _collect_missing_fields(data_dict, required_fields)
            if missing:
                return ChatResponse(action="ASK", content=build_missing_fields_prompt(missing))

            _try_fill_supplier(data_dict, db, logger, scope="batch")

            update_action = _build_update_action(data_dict)
            current_sheet = process_update(current_sheet, update_action)
            updated_rows.append(update_action.target_row)
            applied_payloads.append(data_dict)

        if not updated_rows:
            return ChatResponse(action="ASK", content="更新列表中没有可执行的更新项")

        missing_fields = _build_missing_fields_hint_from_updates(applied_payloads)
        return ChatResponse(
            action="WRITE",
            content=build_write_success_message(updated_rows, missing_fields),
            data=updates,
            updated_sheet=current_sheet,
        )

    data_dict = agent_out.get("data") or {}
    if not isinstance(data_dict, dict):
        return ChatResponse(action="ASK", content="LLM返回的数据格式不正确")

    if not data_dict.get("target_row") and explicit_row:
        data_dict["target_row"] = explicit_row

    if not explicit_row:
        prompt = _resolve_ambiguous_row_prompt(
            data_dict,
            agent_out.get("tool_results") or [],
        )
        if prompt:
            return ChatResponse(action="ASK", content=prompt)

    missing = _collect_missing_fields(data_dict, required_fields)
    if missing:
        return ChatResponse(action="ASK", content=build_missing_fields_prompt(missing))

    try:
        _try_fill_supplier(data_dict, db, logger, scope="single")
        update_action = _build_update_action(data_dict)
        new_sheet = process_update(sheet_data, update_action)

        missing_fields = []
        if not update_action.supplier:
            missing_fields.append("supplier")
        if update_action.shipping is None:
            missing_fields.append(SLOT_FIELD_SHIPPING)

        return ChatResponse(
            action="WRITE",
            content=build_write_success_message([update_action.target_row], missing_fields),
            data=update_action,
            updated_sheet=new_sheet,
        )
    except Exception as exc:
        return ChatResponse(action="ASK", content=f"更新表格失败: {str(exc)}")
