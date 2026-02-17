from __future__ import annotations

from typing import Iterable, Sequence


def build_missing_fields_prompt(missing_fields: Sequence[str]) -> str:
    return f"请补充：{', '.join(missing_fields)}"


def build_multiple_candidates_prompt(candidates: Iterable[dict]) -> str:
    lines = []
    for candidate in list(candidates)[:3]:
        if not isinstance(candidate, dict):
            continue
        row = candidate.get("row")
        name = candidate.get("name") or ""
        brand = candidate.get("brand")
        model = candidate.get("model")
        spec = candidate.get("spec")
        text = f"row {row}: {name}"
        if brand:
            text += f" | 品牌:{brand}"
        if model:
            text += f" | 型号:{model}"
        if spec:
            text += f" | 规格:{spec}"
        lines.append(text)

    tip = " | ".join(lines) if lines else "multiple candidates"
    return f"Multiple candidate rows matched. Please specify row number or provide more details. {tip}"


def build_write_success_message(updated_rows: Sequence[int], missing_fields: Sequence[str]) -> str:
    row_text = ", ".join(str(r) for r in list(updated_rows)[:10])
    message = f"报价已更新（行 {row_text}）"
    if missing_fields:
        message += (
            "\n\n提示：缺少以下信息，如需补充请继续输入："
            + ", ".join(missing_fields)
        )
    return message
