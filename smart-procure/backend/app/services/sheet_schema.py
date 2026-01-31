import re
from typing import Any, Dict, List, Optional, Tuple
from difflib import SequenceMatcher

from ..models.columns import BASIC_COLS


def normalize_header(text: Any) -> str:
    if text is None:
        return ""
    s = str(text).strip()
    s = re.sub(r"\s+", "", s)
    s = s.replace("（", "(").replace("）", ")")
    s = s.replace("：", ":")
    return s


def fuzzy_match_score(str1: str, str2: str) -> float:
    """计算两个字符串的相似度（0-100）"""
    if not str1 or not str2:
        return 0.0
    # 标准化后比较
    norm1 = normalize_header(str1)
    norm2 = normalize_header(str2)
    if not norm1 or not norm2:
        return 0.0
    return SequenceMatcher(None, norm1, norm2).ratio() * 100


CANONICAL_FIELD_SYNONYMS: Dict[str, List[str]] = {
    "品牌": ["品牌", "报价品牌", "品牌(报价)"],
    "备注": ["备注", "说明", "备注说明"],
    "单价": ["单价", "价格", "报价", "含税单价", "不含税单价"],
    "含税": ["含税", "是否含税", "税", "税率", "含税?", "是否含税?", "含税/不含税"],
    "含运": ["含运", "是否含运", "运费", "含运?", "含运费", "是否含运?", "含运/不含运"],
    "货期": ["货期", "交期", "交货期", "交货时间", "发货时间", "到货时间"],
    "供应商": ["供应商", "供应商名称", "供应商全称", "供应商姓名", "供应商手机", "公司名称"],
}

ITEM_NAME_COL_SYNONYMS = ["物料名称", "物品名称", "品名", "名称", "物料", "产品名称", "材料名称"]
ITEM_SPEC_COL_SYNONYMS = ["规格", "规格型号", "规格型号", "型号", "规格/型号", "规格型号/型号"]
ITEM_BRAND_COL_SYNONYMS = ["品牌", "牌", "品牌名称"]
ITEM_MODEL_COL_SYNONYMS = ["产品型号", "型号", "物料型号", "规格型号", "产品编码", "物料编码", "料号", "型号/编码", "规格型号/编码"]


def _best_header_index(headers: List[Any], candidates: List[str]) -> Optional[int]:
    norm_headers = [normalize_header(h) for h in headers]
    candidate_norm = [normalize_header(c) for c in candidates]
    for c in candidate_norm:
        for i, h in enumerate(norm_headers):
            if not h:
                continue
            if h == c:
                return i
    for c in candidate_norm:
        for i, h in enumerate(norm_headers):
            if not h:
                continue
            if c and (c in h or h in c):
                return i
    return None


def infer_item_columns(headers: List[Any]) -> Dict[str, Optional[int]]:
    return {
        "name": _best_header_index(headers, ITEM_NAME_COL_SYNONYMS),
        "spec": _best_header_index(headers, ITEM_SPEC_COL_SYNONYMS),
        "brand": _best_header_index(headers, ITEM_BRAND_COL_SYNONYMS),
        "model": _best_header_index(headers, ITEM_MODEL_COL_SYNONYMS),
    }


def _detect_slot_suffix(norm_header: str) -> Tuple[str, Optional[int]]:
    m = re.match(r"^(.*?)(\d+)$", norm_header)
    if not m:
        return norm_header, None
    base = m.group(1)
    try:
        return base, int(m.group(2))
    except Exception:
        return norm_header, None


def _canonical_field_from_base(base: str) -> Optional[str]:
    for canonical, syns in CANONICAL_FIELD_SYNONYMS.items():
        for s in syns:
            if not s:
                continue
            if base == normalize_header(s):
                return canonical
    for canonical, syns in CANONICAL_FIELD_SYNONYMS.items():
        for s in syns:
            sn = normalize_header(s)
            if not sn:
                continue
            if len(sn) >= 2 and sn in base:
                return canonical
    return None


def build_sheet_schema(sheet_data: Optional[List[List[Any]]]) -> Dict[str, Any]:
    """
    构建表格schema - 使用固定位置模式

    表格结构：
    - 前5列：基础列（物品名称、型号、品牌、数量、单位，顺序可能不同）
    - 从第6列开始：每7列为一个报价槽位
    - 槽位内固定顺序：品牌、单价、含税、含运、货期、备注、供应商
    """
    headers: List[Any] = []
    if sheet_data and len(sheet_data) >= 1 and isinstance(sheet_data[0], list):
        headers = sheet_data[0]

    header_index: Dict[str, int] = {}
    for idx, h in enumerate(headers):
        nh = normalize_header(h)
        if nh and nh not in header_index:
            header_index[nh] = idx

    # 固定位置模式：前5列为基础列
    BASIC_COLS_COUNT = 5

    # 识别基础列（通过字段名匹配）
    item_cols = infer_item_columns(headers[:BASIC_COLS_COUNT])

    # 从第6列开始，每7列为一个报价槽位
    SLOT_SIZE = 7
    SLOT_START = BASIC_COLS_COUNT

    # 槽位内的固定顺序
    SLOT_FIELDS = ["品牌", "单价", "含税", "含运", "货期", "备注", "供应商"]

    slots: Dict[int, Dict[str, int]] = {}
    slot_num = 1
    col_idx = SLOT_START

    while col_idx + SLOT_SIZE <= len(headers):
        slot_mapping = {}
        for i, field in enumerate(SLOT_FIELDS):
            slot_mapping[field] = col_idx + i
        slots[slot_num] = slot_mapping
        slot_num += 1
        col_idx += SLOT_SIZE

    return {
        "headers": headers,
        "header_index": header_index,
        "slots": slots,
        "item_columns": item_cols,
    }


def get_row_snapshot(sheet_data: List[List[Any]], row_index_1_based: int) -> Optional[Dict[str, Any]]:
    if not sheet_data or row_index_1_based <= 0:
        return None
    if row_index_1_based - 1 >= len(sheet_data):
        return None
    headers = sheet_data[0] if sheet_data else []
    row = sheet_data[row_index_1_based - 1]
    if not isinstance(headers, list) or not isinstance(row, list):
        return None
    out: Dict[str, Any] = {}
    for i, h in enumerate(headers):
        key = str(h) if h is not None else ""
        if not key:
            continue
        out[key] = row[i] if i < len(row) else None
    return out


def get_row_snapshot_reduced(schema: Dict[str, Any], sheet_data: List[List[Any]], row_index_1_based: int, max_fields: int = 80) -> Optional[Dict[str, Any]]:
    if not sheet_data or row_index_1_based <= 0:
        return None
    if row_index_1_based - 1 >= len(sheet_data):
        return None
    headers = sheet_data[0] if sheet_data else []
    row = sheet_data[row_index_1_based - 1]
    if not isinstance(headers, list) or not isinstance(row, list):
        return None

    include: List[int] = []

    cols = schema.get("item_columns") or {}
    for key in ("name", "brand", "spec", "model"):
        idx = cols.get(key)
        if isinstance(idx, int):
            include.append(idx)

    slots: Dict[int, Dict[str, int]] = schema.get("slots") or {}
    for slot_num in sorted(slots.keys()):
        slot_map = slots.get(slot_num) or {}
        for _, idx in slot_map.items():
            if isinstance(idx, int):
                include.append(idx)

    include_set = set([i for i in include if 0 <= i < len(headers)])

    for i in range(min(len(headers), len(row))):
        if len(include_set) >= max_fields:
            break
        if i in include_set:
            continue
        v = row[i]
        if v is None:
            continue
        s = str(v).strip()
        if s == "" or s.lower() == "none":
            continue
        include_set.add(i)

    ordered = [i for i in include if i in include_set]
    for i in sorted(include_set):
        if i not in ordered:
            ordered.append(i)
        if len(ordered) >= max_fields:
            break

    out: Dict[str, Any] = {}
    for i in ordered:
        if i < 0 or i >= len(headers):
            continue
        key = str(headers[i]) if headers[i] is not None else ""
        if not key:
            continue
        out[key] = row[i] if i < len(row) else None
    return out


def _cell_text(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()

SLOT_FIELDS_ORDER = ["品牌", "备注", "单价", "含税", "含运", "货期", "供应商"]


def find_row_by_item_name(sheet_data: List[List[Any]], query: str, max_scan_rows: int = 3000) -> Optional[int]:
    if not sheet_data or len(sheet_data) < 2:
        return None
    headers = sheet_data[0]
    cols = infer_item_columns(headers)
    name_col = cols.get("name")
    if name_col is None:
        return None
    q = normalize_header(query)
    if not q:
        return None

    best: Optional[Tuple[int, int]] = None
    for i, row in enumerate(sheet_data[1:], start=2):
        if i > max_scan_rows:
            break
        if not isinstance(row, list):
            continue
        cell = _cell_text(row[name_col] if name_col < len(row) else "")
        if not cell:
            continue
        nh = normalize_header(cell)
        if q == nh:
            return i
        if q in nh:
            score = len(q) * 10
            if best is None or score > best[1]:
                best = (i, score)
        elif nh and nh in q:
            score = len(nh)
            if best is None or score > best[1]:
                best = (i, score)
    return best[0] if best else None


def find_row_by_item_criteria(
    sheet_data: List[List[Any]],
    item_name: Optional[str] = None,
    brand: Optional[str] = None,
    model: Optional[str] = None,
    max_scan_rows: int = 3000,
) -> Optional[int]:
    if not sheet_data or len(sheet_data) < 2:
        return None
    headers = sheet_data[0]
    cols = infer_item_columns(headers)
    name_col = cols.get("name")
    brand_col = cols.get("brand")
    model_col = cols.get("model")

    q_name = normalize_header(item_name) if isinstance(item_name, str) else ""
    q_brand = normalize_header(brand) if isinstance(brand, str) else ""
    q_model = normalize_header(model) if isinstance(model, str) else ""

    if not q_name and not q_brand and not q_model:
        return None

    best: Optional[Tuple[int, int]] = None
    for i, row in enumerate(sheet_data[1:], start=2):
        if i > max_scan_rows:
            break
        if not isinstance(row, list):
            continue

        score = 0
        if isinstance(name_col, int) and name_col < len(row):
            nh = normalize_header(_cell_text(row[name_col]))
            if q_name and nh:
                if q_name == nh:
                    score += 1000
                elif q_name in nh or nh in q_name:
                    score += 400 + min(len(q_name), 50)

        if isinstance(brand_col, int) and brand_col < len(row):
            bh = normalize_header(_cell_text(row[brand_col]))
            if q_brand and bh:
                if q_brand == bh:
                    score += 600
                elif q_brand in bh or bh in q_brand:
                    score += 250 + min(len(q_brand), 30)

        if isinstance(model_col, int) and model_col < len(row):
            mh = normalize_header(_cell_text(row[model_col]))
            if q_model and mh:
                if q_model == mh:
                    score += 800
                elif q_model in mh or mh in q_model:
                    score += 300 + min(len(q_model), 30)

        if score <= 0:
            continue
        if best is None or score > best[1]:
            best = (i, score)

        if score >= 2300:
            return i

    return best[0] if best else None


def locate_rows_by_criteria(
    sheet_data: List[List[Any]],
    item_name: Optional[str] = None,
    brand: Optional[str] = None,
    model: Optional[str] = None,
    spec: Optional[str] = None,
    max_candidates: int = 5,
    max_scan_rows: int = 3000,
) -> Dict[str, Any]:
    if not sheet_data or len(sheet_data) < 2:
        return {"candidates": [], "ambiguous": False}
    headers = sheet_data[0]
    cols = infer_item_columns(headers)
    name_col = cols.get("name")
    brand_col = cols.get("brand")
    model_col = cols.get("model")
    spec_col = cols.get("spec")

    q_name = normalize_header(item_name) if isinstance(item_name, str) else ""
    q_brand = normalize_header(brand) if isinstance(brand, str) else ""
    q_model = normalize_header(model) if isinstance(model, str) else ""
    q_spec = normalize_header(spec) if isinstance(spec, str) else ""

    if not q_name and not q_brand and not q_model and not q_spec:
        return {"candidates": [], "ambiguous": False}

    weak_only = False
    if q_model or q_spec:
        weak_only = False
    elif q_name and len(q_name) <= 2 and not q_brand:
        weak_only = True
    elif q_brand and not q_name:
        weak_only = True

    scored: List[Tuple[int, int]] = []
    for i, row in enumerate(sheet_data[1:], start=2):
        if i > max_scan_rows:
            break
        if not isinstance(row, list):
            continue
        score = 0

        def _col_norm(idx: Optional[int]) -> str:
            if not isinstance(idx, int) or idx < 0 or idx >= len(row):
                return ""
            return normalize_header(_cell_text(row[idx]))

        nh = _col_norm(name_col)
        bh = _col_norm(brand_col)
        mh = _col_norm(model_col)
        sh = _col_norm(spec_col)

        if q_name and nh:
            if q_name == nh:
                score += 1200
            elif q_name in nh:
                score += 350 + min(len(q_name), 50)
            elif nh in q_name:
                score += 200 + min(len(nh), 50)

        if q_brand and bh:
            if q_brand == bh:
                score += 800
            elif q_brand in bh or bh in q_brand:
                score += 250 + min(len(q_brand), 30)

        if q_model and mh:
            if q_model == mh:
                score += 1600
            elif q_model in mh or mh in q_model:
                score += 500 + min(len(q_model), 30)
            else:
                score = 0

        if q_spec and sh:
            if q_spec == sh:
                score += 900
            elif q_spec in sh or sh in q_spec:
                score += 250 + min(len(q_spec), 30)
            else:
                if q_model:
                    score = 0

        if score <= 0:
            continue
        scored.append((i, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:max_candidates]
    candidates = []
    for row_idx, s in top:
        row = sheet_data[row_idx - 1] if row_idx - 1 < len(sheet_data) else []
        def _raw(idx: Optional[int]):
            if not isinstance(idx, int) or not isinstance(row, list) or idx < 0 or idx >= len(row):
                return None
            v = row[idx]
            if v is None:
                return None
            t = str(v).strip()
            return None if t == "" or t.lower() == "none" else v
        candidates.append({
            "row": row_idx,
            "score": s,
            "name": _raw(name_col),
            "brand": _raw(brand_col),
            "model": _raw(model_col),
            "spec": _raw(spec_col),
        })

    ambiguous = weak_only and len(candidates) > 1
    return {"candidates": candidates, "ambiguous": ambiguous}


def find_candidate_rows(sheet_data: List[List[Any]], query: str, max_candidates: int = 3) -> List[int]:
    if not sheet_data or len(sheet_data) < 2:
        return []
    q = normalize_header(query)
    if not q:
        return []

    headers = sheet_data[0]
    cols = infer_item_columns(headers)
    name_col = cols.get("name")
    spec_col = cols.get("spec")
    brand_col = cols.get("brand")
    if name_col is None:
        return []

    scored: List[Tuple[int, int]] = []
    for i, row in enumerate(sheet_data[1:], start=2):
        if not isinstance(row, list):
            continue
        name_val = _cell_text(row[name_col] if name_col < len(row) else "")
        if not name_val:
            continue
        nh = normalize_header(name_val)
        if q == nh:
            return [i]
        if q in nh:
            score = 1000 + len(q)
        else:
            brand_val = _cell_text(row[brand_col] if isinstance(brand_col, int) and brand_col < len(row) else "")
            spec_val = _cell_text(row[spec_col] if isinstance(spec_col, int) and spec_col < len(row) else "")
            hay = normalize_header("|".join([name_val, brand_val, spec_val]))
            if q not in hay:
                continue
            score = 100 + min(len(q), 20)
        scored.append((i, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [i for i, _ in scored[:max_candidates]]


def extract_row_from_message(message: str) -> Optional[int]:
    m = re.search(r"第?\s*(\d+)\s*行", message)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def build_writable_fields(schema: Dict[str, Any], max_slots: int = 5) -> Dict[str, Dict[str, str]]:
    headers = schema.get("headers") or []
    slots: Dict[int, Dict[str, int]] = schema.get("slots") or {}
    out: Dict[str, Dict[str, str]] = {}
    for slot_num in sorted(slots.keys())[:max_slots]:
        mapping: Dict[str, str] = {}
        for canonical, idx in slots[slot_num].items():
            if 0 <= idx < len(headers):
                mapping[canonical] = str(headers[idx])
        out[str(slot_num)] = mapping
    return out


def get_row_slot_snapshot(schema: Dict[str, Any], sheet_data: List[List[Any]], row_index_1_based: int, max_slots: int = 5) -> Optional[Dict[str, Any]]:
    if not sheet_data or row_index_1_based <= 0:
        return None
    if row_index_1_based - 1 >= len(sheet_data):
        return None
    headers = sheet_data[0] if sheet_data else []
    row = sheet_data[row_index_1_based - 1]
    if not isinstance(headers, list) or not isinstance(row, list):
        return None

    cols = schema.get("item_columns") or {}
    name_col = cols.get("name")
    brand_col = cols.get("brand")
    spec_col = cols.get("spec")
    model_col = cols.get("model")

    def _get(idx):
        if not isinstance(idx, int):
            return None
        if idx < 0 or idx >= len(row):
            return None
        v = row[idx]
        if v is None:
            return None
        s = str(v).strip()
        return None if s == "" or s.lower() == "none" else v

    slots: Dict[int, Dict[str, int]] = schema.get("slots") or {}
    out_slots: Dict[str, Dict[str, Any]] = {}
    for slot_num in sorted(slots.keys())[:max_slots]:
        slot_map = slots.get(slot_num) or {}
        values: Dict[str, Any] = {}
        for field in SLOT_FIELDS_ORDER:
            idx = slot_map.get(field)
            if isinstance(idx, int):
                values[field] = _get(idx)
        out_slots[str(slot_num)] = values

    return {
        "row": row_index_1_based,
        "物品名称": _get(name_col),
        "品牌": _get(brand_col),
        "规格": _get(spec_col),
        "型号": _get(model_col),
        "slots": out_slots,
    }


def fuzzy_match_rows(
    sheet_data: List[List[Any]],
    query: str,
    brand_filter: Optional[str] = None,
    threshold: float = 80.0,
    max_results: int = 20,
) -> List[Dict[str, Any]]:
    """
    使用模糊匹配查找与查询字符串相似的行

    Args:
        sheet_data: 表格数据
        query: 查询字符串（型号、产品名称等）
        brand_filter: 可选的品牌过滤
        threshold: 相似度阈值（0-100）
        max_results: 最多返回的结果数

    Returns:
        匹配的行列表，每个元素包含行号、相似度、字段信息
    """
    if not sheet_data or len(sheet_data) < 2:
        return []
    if not query or not query.strip():
        return []

    headers = sheet_data[0]
    cols = infer_item_columns(headers)
    name_col = cols.get("name")
    brand_col = cols.get("brand")
    model_col = cols.get("model")
    spec_col = cols.get("spec")

    results = []

    for i, row in enumerate(sheet_data[1:], start=2):
        if not isinstance(row, list):
            continue

        # 获取各字段值
        def _get_val(idx):
            if not isinstance(idx, int) or idx < 0 or idx >= len(row):
                return ""
            v = row[idx]
            return str(v).strip() if v is not None else ""

        name = _get_val(name_col)
        brand = _get_val(brand_col)
        model = _get_val(model_col)
        spec = _get_val(spec_col)

        # 品牌过滤
        if brand_filter:
            brand_score = fuzzy_match_score(brand_filter, brand)
            if brand_score < 70:  # 品牌相似度要求较低
                continue

        # 计算各字段的相似度
        max_score = 0.0
        match_field = ""

        if model:
            model_score = fuzzy_match_score(query, model)
            if model_score > max_score:
                max_score = model_score
                match_field = "型号"

        if name:
            name_score = fuzzy_match_score(query, name)
            if name_score > max_score:
                max_score = name_score
                match_field = "产品名称"

        if spec:
            spec_score = fuzzy_match_score(query, spec)
            if spec_score > max_score:
                max_score = spec_score
                match_field = "规格"

        # 如果相似度超过阈值，加入结果
        if max_score >= threshold:
            results.append({
                "row": i,
                "score": max_score,
                "match_field": match_field,
                "name": name or None,
                "brand": brand or None,
                "model": model or None,
                "spec": spec or None,
            })

    # 按相似度降序排序
    results.sort(key=lambda x: x["score"], reverse=True)

    return results[:max_results]

