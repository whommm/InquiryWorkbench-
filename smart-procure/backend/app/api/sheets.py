import re
import uuid
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth.utils import get_current_user
from ..models.database import User, get_db
from ..services.db_service import DBService
from ..services.excel_export import export_sheet_to_excel
from ..services.notification_service import add_notification
from ..services.sheet_schema import build_sheet_schema
from ..services.supplier_service import SupplierService

router = APIRouter()


class SaveSheetRequest(BaseModel):
    id: Optional[str] = None
    name: str
    sheet_data: list
    chat_history: list


class ExtractSuppliersRequest(BaseModel):
    sheet_data: list


@router.post("/sheets/save")
async def save_sheet(
    request: SaveSheetRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save or update an inquiry sheet."""
    try:
        sheet_id = request.id or str(uuid.uuid4())

        schema = build_sheet_schema(request.sheet_data)
        slots = schema.get("slots") or {}
        slot_count = len(slots)
        item_count = len(request.sheet_data) - 1 if len(request.sheet_data) > 1 else 0

        total_cells = item_count * slot_count
        filled_cells = 0
        if total_cells > 0:
            for row in request.sheet_data[1:]:
                if not isinstance(row, list):
                    continue
                for slot_num in slots.keys():
                    slot_map = slots.get(slot_num) or {}
                    price_idx = slot_map.get("单价")
                    if isinstance(price_idx, int) and price_idx < len(row):
                        val = row[price_idx]
                        if val and str(val).strip() and str(val).strip().lower() != "none":
                            filled_cells += 1

        completion_rate = filled_cells / total_cells if total_cells > 0 else 0.0
        db_service = DBService(db)
        sheet = db_service.save_sheet(
            sheet_id=sheet_id,
            name=request.name,
            sheet_data=request.sheet_data,
            chat_history=request.chat_history,
            user_id=current_user.id,
            item_count=item_count,
            completion_rate=completion_rate,
        )

        return {
            "id": sheet.id,
            "message": "保存成功",
            "completion_rate": completion_rate,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save sheet: {str(e)}")


@router.get("/sheets/list")
async def list_sheets(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get list of saved inquiry sheets."""
    try:
        db_service = DBService(db)
        sheets = db_service.list_sheets(user_id=current_user.id, limit=limit, offset=offset)

        result = []
        for sheet in sheets:
            result.append(
                {
                    "id": sheet.id,
                    "name": sheet.name,
                    "item_count": sheet.item_count,
                    "completion_rate": sheet.completion_rate,
                    "created_at": sheet.created_at.isoformat() + "Z" if sheet.created_at else "",
                    "updated_at": sheet.updated_at.isoformat() + "Z" if sheet.updated_at else "",
                }
            )

        return {"sheets": result, "total": len(result)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list sheets: {str(e)}")


@router.get("/sheets/{sheet_id}")
async def get_sheet(
    sheet_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single inquiry sheet by ID."""
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
            "updated_at": sheet.updated_at.isoformat() if sheet.updated_at else "",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get sheet: {str(e)}")


@router.delete("/sheets/{sheet_id}")
async def delete_sheet(
    sheet_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an inquiry sheet."""
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
    current_user: User = Depends(get_current_user),
):
    """Export an inquiry sheet to Excel."""
    try:
        db_service = DBService(db)
        sheet = db_service.get_sheet(sheet_id, user_id=current_user.id)
        if not sheet:
            raise HTTPException(status_code=404, detail="Sheet not found")

        excel_file = export_sheet_to_excel(sheet.sheet_data, f"{sheet.name}.xlsx")
        encoded_filename = quote(f"{sheet.name}.xlsx")
        return StreamingResponse(
            excel_file,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export sheet: {str(e)}")


def _extract_phones_from_text(text: str) -> list:
    """Extract phone numbers from supplier text."""
    if not text:
        return []
    patterns = [
        r"1[3-9]\d{9}",
        r"0\d{2,3}-?\d{7,8}",
    ]
    phones = []
    for pattern in patterns:
        phones.extend(re.findall(pattern, text))
    return phones


def _extract_suppliers_background(supplier_entries: list, user_id: str):
    """Background task: extract and persist suppliers from free-form text."""
    from ..core.llm import extract_suppliers_with_llm
    from ..models.database import get_db_session

    if not supplier_entries:
        return

    supplier_texts = [e["text"] for e in supplier_entries]

    try:
        ai_results = extract_suppliers_with_llm(supplier_texts)
        if not ai_results:
            return

        text_to_entries = {}
        for entry in supplier_entries:
            text = entry["text"]
            if text not in text_to_entries:
                text_to_entries[text] = []
            text_to_entries[text].append(entry)

        db = next(get_db_session())
        try:
            supplier_service = SupplierService(db)
            seen_phones = set()
            saved_count = 0

            for info in ai_results:
                phone = info.get("contact_phone")
                company = info.get("company_name")
                original_text = info.get("original_text")

                if not phone and not company:
                    continue
                if phone and phone in seen_phones:
                    continue
                if phone:
                    seen_phones.add(phone)

                related_entries = text_to_entries.get(original_text, [])
                brands = set()
                for entry in related_entries:
                    if entry.get("brand"):
                        brands.add(entry["brand"])
                tags = list(brands) if brands else None

                try:
                    saved_supplier = supplier_service.upsert_supplier(
                        company_name=company or "未知公司",
                        contact_phone=phone,
                        owner="手动录入",
                        contact_name=info.get("contact_name"),
                        tags=tags,
                        created_by=user_id,
                    )
                    saved_count += 1

                    for entry in related_entries:
                        if entry.get("product_name") or entry.get("product_model"):
                            supplier_service.upsert_supplier_product(
                                supplier_id=saved_supplier.id,
                                product_name=entry.get("product_name"),
                                product_model=entry.get("product_model"),
                                brand=entry.get("brand"),
                                price=entry.get("price"),
                            )
                except Exception:
                    continue

            if saved_count > 0:
                add_notification(user_id, f"已成功新增 {saved_count} 个供应商", "success")
        finally:
            db.close()
    except Exception:
        return


@router.post("/sheets/extract-suppliers")
async def extract_suppliers_from_sheet(
    request: ExtractSuppliersRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    从表格数据中提取供应商信息并保存到数据库。
    先用算法预检查是否有新供应商，有才触发 LLM 提取。
    """
    sheet_data = request.sheet_data
    if not sheet_data or len(sheet_data) < 2:
        return {"status": "skipped", "new_count": 0}

    schema = build_sheet_schema(sheet_data)
    slots = schema.get("slots") or {}
    cols = schema.get("item_columns") or {}
    name_col = cols.get("name")
    brand_col = cols.get("brand")
    model_col = cols.get("model")

    def _get_cell(row, idx):
        if not isinstance(idx, int) or idx >= len(row):
            return None
        v = row[idx]
        if v and str(v).strip() and str(v).strip().lower() != "none":
            return str(v).strip()
        return None

    supplier_entries = []
    for row in sheet_data[1:]:
        if not isinstance(row, list):
            continue

        row_name = _get_cell(row, name_col)
        row_brand = _get_cell(row, brand_col)
        row_model = _get_cell(row, model_col)

        for slot_num in sorted(slots.keys()):
            slot_map = slots.get(slot_num) or {}
            supplier_idx = slot_map.get("供应商")
            brand_slot_idx = slot_map.get("品牌")
            price_idx = slot_map.get("单价")

            supplier_text = _get_cell(row, supplier_idx)
            if not supplier_text:
                continue

            slot_brand = _get_cell(row, brand_slot_idx) or row_brand
            price_val = None
            if isinstance(price_idx, int) and price_idx < len(row):
                try:
                    price_val = float(row[price_idx])
                except Exception:
                    pass

            supplier_entries.append(
                {
                    "text": supplier_text,
                    "brand": slot_brand,
                    "product_name": row_name,
                    "product_model": row_model,
                    "price": price_val,
                }
            )

    if not supplier_entries:
        return {"status": "skipped", "new_count": 0}

    all_phones = set()
    for entry in supplier_entries:
        all_phones.update(_extract_phones_from_text(entry["text"]))
    if not all_phones:
        return {"status": "skipped", "new_count": 0}

    supplier_service = SupplierService(db)
    existing_phones = supplier_service.get_existing_phones(list(all_phones))
    new_phones = all_phones - existing_phones
    if not new_phones:
        return {"status": "skipped", "new_count": 0}

    entries_with_new_phones = []
    for entry in supplier_entries:
        phones = _extract_phones_from_text(entry["text"])
        if any(p in new_phones for p in phones):
            entries_with_new_phones.append(entry)
    if not entries_with_new_phones:
        return {"status": "skipped", "new_count": 0}

    background_tasks.add_task(
        _extract_suppliers_background,
        entries_with_new_phones,
        current_user.id,
    )
    return {"status": "processing", "new_count": len(new_phones)}

