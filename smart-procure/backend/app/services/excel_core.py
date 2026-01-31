from ..models.columns import SLOT_TEMPLATE
from ..models.types import UpdateAction
from .sheet_schema import build_sheet_schema, normalize_header
from .supplier_extractor import extract_supplier_info
from .supplier_service import SupplierService
from typing import List, Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

def _ensure_row_len(row: List[Any], length: int):
    while len(row) < length:
        row.append(None)


def _get_slot_index(schema: Dict[str, Any], slot_num: int, field: str) -> Optional[int]:
    slots = schema.get("slots") or {}
    slot = slots.get(slot_num) or {}
    idx = slot.get(field)
    return idx if isinstance(idx, int) else None

def get_slot_values(row: List[Any], schema: Dict[str, Any], slot_num: int) -> Dict[str, Any]:
    values = {}
    for field in SLOT_TEMPLATE:
        idx = _get_slot_index(schema, slot_num, field)
        values[field] = row[idx] if isinstance(idx, int) and idx < len(row) else None
    return values

def set_slot_values(row: List[Any], schema: Dict[str, Any], slot_num: int, values: Dict[str, Any]):
    for field in SLOT_TEMPLATE:
        idx = _get_slot_index(schema, slot_num, field)
        if isinstance(idx, int) and idx >= 0:
            _ensure_row_len(row, idx + 1)
            row[idx] = values.get(field)

def get_price(slot_values: Dict[str, Any]) -> float:
    try:
        val = slot_values.get("单价")
        if val is None or val == "" or val == "None":
            return float('inf')
        return float(val)
    except:
        return float('inf')

def process_update(sheet_data: List[List[Any]], action: UpdateAction, db: Optional["Session"] = None) -> List[List[Any]]:
    # 0-based index for python list, but action.target_row is likely 1-based (Excel row number)
    # If header is row 1 (index 0), then row 2 is index 1.
    target_idx = action.target_row - 1 
    
    if target_idx < 0 or target_idx >= len(sheet_data):
        # In a real app we might handle this, but for now just return
        return sheet_data
    
    row = sheet_data[target_idx]
    schema = build_sheet_schema(sheet_data)
    slots = schema.get("slots") or {}
    if not slots:
        return sheet_data

    slot_numbers = sorted([int(s) for s in slots.keys() if isinstance(s, int)])
    if not slot_numbers:
        return sheet_data

    cols = schema.get("item_columns") or {}
    model_col = cols.get("model")
    spec_col = cols.get("spec")
    brand_col = cols.get("brand")
    row_model = None
    if isinstance(model_col, int) and isinstance(row, list) and 0 <= model_col < len(row):
        v = row[model_col]
        if v is not None:
            s = str(v).strip()
            if s and s.lower() != "none":
                row_model = s

    row_spec = None
    if isinstance(spec_col, int) and isinstance(row, list) and 0 <= spec_col < len(row):
        v = row[spec_col]
        if v is not None:
            s = str(v).strip()
            if s and s.lower() != "none":
                row_spec = s

    row_brand = None
    if isinstance(brand_col, int) and isinstance(row, list) and 0 <= brand_col < len(row):
        v = row[brand_col]
        if v is not None:
            s = str(v).strip()
            if s and s.lower() != "none":
                row_brand = s

    auto_remark = None
    if isinstance(action.quoted_model, str) and action.quoted_model.strip() and row_model:
        qm = action.quoted_model.strip()
        if normalize_header(qm).lower() != normalize_header(row_model).lower():
            auto_remark = f"型号不一致: 报价({qm}) 表内({row_model})"

    auto_spec_remark = None
    if isinstance(action.quoted_spec, str) and action.quoted_spec.strip() and row_spec:
        qs = action.quoted_spec.strip()
        if normalize_header(qs).lower() != normalize_header(row_spec).lower():
            auto_spec_remark = f"规格不一致: 报价({qs}) 表内({row_spec})"
    
    # Construct New Offer
    remarks = action.remarks
    if auto_remark:
        if not isinstance(remarks, str) or not remarks.strip():
            remarks = auto_remark
        elif auto_remark not in remarks:
            remarks = remarks.strip() + "；" + auto_remark
    if auto_spec_remark:
        if not isinstance(remarks, str) or not remarks.strip():
            remarks = auto_spec_remark
        elif auto_spec_remark not in remarks:
            remarks = remarks.strip() + "；" + auto_spec_remark

    offer_brand = action.offer_brand
    if (not isinstance(offer_brand, str) or not offer_brand.strip()) and row_brand:
        offer_brand = row_brand

    new_offer = {
        "品牌": offer_brand,
        "备注": remarks,
        "单价": action.price,
        "含税": "是" if action.tax else "否",
        "含运": action.shipping if isinstance(action.shipping, str) else ("是" if action.shipping else "否"),
        "货期": action.delivery_time,
        "供应商": action.supplier,
    }

    def slot_vals(n: int) -> Dict[str, Any]:
        return get_slot_values(row, schema, n)

    offers: List[Tuple[float, int, Dict[str, Any]]] = []
    for n in slot_numbers:
        vals = slot_vals(n)
        p = get_price(vals)
        if p == float("inf"):
            continue
        offers.append((p, n, vals))

    offers.sort(key=lambda x: (x[0], x[1]))
    sorted_vals = [v for _, __, v in offers]

    print(f"[DEBUG] process_update - action.price: {action.price}, type: {type(action.price)}")
    p_new = float(action.price)
    print(f"[DEBUG] process_update - p_new after float(): {p_new}")
    out_vals: List[Dict[str, Any]] = []
    inserted = False
    for v in sorted_vals:
        if not inserted and p_new < get_price(v):
            out_vals.append(new_offer)
            inserted = True
        out_vals.append(v)
    if not inserted:
        out_vals.append(new_offer)

    out_vals = out_vals[: len(slot_numbers)]
    empty_offer = {k: None for k in SLOT_TEMPLATE}

    for i, slot_num in enumerate(slot_numbers):
        if i < len(out_vals):
            set_slot_values(row, schema, slot_num, out_vals[i])
        else:
            set_slot_values(row, schema, slot_num, empty_offer)

    # Auto-extract and save supplier information
    if db and action.supplier:
        print(f"[供应商沉淀] 开始处理供应商信息: {action.supplier}")
        supplier_info = extract_supplier_info(action.supplier, offer_brand)

        if supplier_info:
            try:
                supplier_service = SupplierService(db)
                saved_supplier = supplier_service.upsert_supplier(
                    company_name=supplier_info["company_name"],
                    contact_phone=supplier_info["contact_phone"],
                    owner="系统自动",
                    contact_name=supplier_info.get("contact_name"),
                    tags=supplier_info.get("tags")
                )
                print(f"✓ [供应商沉淀] 成功保存供应商: {saved_supplier.company_name} (电话: {saved_supplier.contact_phone})")
            except Exception as e:
                # Log error but don't fail the update
                print(f"✗ [供应商沉淀] 保存失败: {e}")
        else:
            print(f"✗ [供应商沉淀] 信息提取失败 - 原因: 供应商文本中未找到有效的电话号码")
            print(f"  提示: 供应商信息必须包含以下格式之一的电话号码：")
            print(f"    - 手机号: 11位数字，1开头（如：13912345678）")
            print(f"    - 座机号: 带区号（如：0512-12345678、021-12345678）")
            print(f"    - 座机号: 7-8位数字（如：12345678）")
            print(f"  示例格式: '苏州比高机电有限公司 张三 0512-12345678'")
    elif action.supplier:
        print(f"✗ [供应商沉淀] 数据库连接不可用，无法保存供应商")
    else:
        print(f"[供应商沉淀] 跳过 - 本次更新未包含供应商信息")

    return sheet_data
