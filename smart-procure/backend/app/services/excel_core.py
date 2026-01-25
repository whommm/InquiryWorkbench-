from ..models.columns import SLOT_TEMPLATE
from ..models.types import UpdateAction
from .sheet_schema import build_sheet_schema, normalize_header
from typing import List, Any, Dict, Optional

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

def process_update(sheet_data: List[List[Any]], action: UpdateAction) -> List[List[Any]]:
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

    p_new = float(action.price)
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

    return sheet_data
