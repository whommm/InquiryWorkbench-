from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from ..core.datetime_utils import ensure_utc
from ..models.database import InquirySheet, User
from ..models.columns import SLOT_FIELD_PRICE
from .admin_progress_stream import publish_admin_progress_sync
from .sheet_schema import build_sheet_schema


DEFAULT_TZ = "Asia/Shanghai"


@dataclass
class TimeWindow:
    date_label: str
    tz_name: str
    start_utc: datetime
    end_utc: datetime


def _safe_zoneinfo(tz_name: Optional[str]) -> Tuple[ZoneInfo, str]:
    if isinstance(tz_name, str) and tz_name.strip():
        try:
            return ZoneInfo(tz_name.strip()), tz_name.strip()
        except Exception:
            pass
    return ZoneInfo(DEFAULT_TZ), DEFAULT_TZ


def _parse_date(value: Optional[str], tz: ZoneInfo) -> date:
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip())
        except Exception:
            pass
    return datetime.now(tz).date()


def build_time_window(date_str: Optional[str], tz_name: Optional[str]) -> TimeWindow:
    tz, normalized_tz_name = _safe_zoneinfo(tz_name)
    target_date = _parse_date(date_str, tz)
    day_start = datetime.combine(target_date, time.min, tzinfo=tz)
    day_end = day_start + timedelta(days=1)
    return TimeWindow(
        date_label=target_date.isoformat(),
        tz_name=normalized_tz_name,
        start_utc=day_start.astimezone(timezone.utc),
        end_utc=day_end.astimezone(timezone.utc),
    )


def _is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return text != "" and text.lower() != "none"


def _sheet_rows_progress(sheet_data: Any) -> Dict[str, Any]:
    if not isinstance(sheet_data, list) or len(sheet_data) < 2:
        return {"total_rows": 0, "quoted_rows": 0, "progress": 0.0}

    schema = build_sheet_schema(sheet_data)
    item_cols = schema.get("item_columns") or {}
    slots = schema.get("slots") or {}
    name_col = item_cols.get("name")
    model_col = item_cols.get("model")
    spec_col = item_cols.get("spec")

    candidate_cols = [idx for idx in (name_col, model_col, spec_col) if isinstance(idx, int)]

    def _is_product_row(row: List[Any]) -> bool:
        if candidate_cols:
            return any(idx < len(row) and _is_non_empty(row[idx]) for idx in candidate_cols)
        return any(idx < len(row) and _is_non_empty(row[idx]) for idx in range(min(5, len(row))))

    def _has_price(row: List[Any]) -> bool:
        for slot_num in sorted(slots.keys()):
            slot_map = slots.get(slot_num) or {}
            price_idx = slot_map.get(SLOT_FIELD_PRICE)
            if isinstance(price_idx, int) and price_idx < len(row) and _is_non_empty(row[price_idx]):
                return True
        return False

    total_rows = 0
    quoted_rows = 0
    for row in sheet_data[1:]:
        if not isinstance(row, list):
            continue
        if not _is_product_row(row):
            continue
        total_rows += 1
        if _has_price(row):
            quoted_rows += 1

    progress = (quoted_rows / total_rows) if total_rows else 0.0
    return {
        "total_rows": total_rows,
        "quoted_rows": quoted_rows,
        "progress": round(progress, 4),
    }


def _serialize_time(value: Optional[datetime]) -> Optional[str]:
    normalized = ensure_utc(value)
    return normalized.isoformat() if normalized else None


def _query_updated_sheets(
    db: Session,
    start_utc: datetime,
    end_utc: datetime,
    user_id: Optional[str] = None,
) -> List[InquirySheet]:
    query = db.query(InquirySheet).filter(
        InquirySheet.updated_at >= start_utc,
        InquirySheet.updated_at < end_utc,
    )
    if user_id:
        query = query.filter(InquirySheet.user_id == user_id)
    return query.order_by(InquirySheet.updated_at.desc()).all()


def _build_user_summary(user: User, sheets: List[InquirySheet]) -> Dict[str, Any]:
    sheet_details: List[Dict[str, Any]] = []
    total_rows = 0
    quoted_rows = 0
    last_update_at: Optional[datetime] = None
    updated_sheet_names: List[str] = []

    for sheet in sheets:
        metrics = _sheet_rows_progress(sheet.sheet_data)
        total_rows += metrics["total_rows"]
        quoted_rows += metrics["quoted_rows"]
        updated_at = ensure_utc(sheet.updated_at)
        if updated_at and (last_update_at is None or updated_at > last_update_at):
            last_update_at = updated_at

        sheet_details.append(
            {
                "sheet_id": sheet.id,
                "sheet_name": sheet.name,
                "updated_at": _serialize_time(updated_at),
                "total_rows": metrics["total_rows"],
                "quoted_rows": metrics["quoted_rows"],
                "progress": metrics["progress"],
            }
        )
        if isinstance(sheet.name, str) and sheet.name.strip():
            updated_sheet_names.append(sheet.name.strip())

    progress = round((quoted_rows / total_rows), 4) if total_rows else 0.0
    unique_names: List[str] = []
    for name in updated_sheet_names:
        if name not in unique_names:
            unique_names.append(name)

    return {
        "user_id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "today_updated_sheet_count": len(sheets),
        "today_total_rows": total_rows,
        "today_quoted_rows": quoted_rows,
        "today_progress": progress,
        "last_update_at": _serialize_time(last_update_at),
        "updated_sheet_names": unique_names,
        "latest_sheet_name": unique_names[0] if unique_names else None,
        "sheets": sheet_details,
    }


def get_user_daily_progress(
    db: Session,
    user_id: str,
    date_str: Optional[str] = None,
    tz_name: Optional[str] = None,
) -> Dict[str, Any]:
    window = build_time_window(date_str, tz_name)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {
            "date": window.date_label,
            "tz": window.tz_name,
            "user": None,
        }

    sheets = _query_updated_sheets(db, window.start_utc, window.end_utc, user_id=user_id)
    summary = _build_user_summary(user, sheets)
    return {
        "date": window.date_label,
        "tz": window.tz_name,
        "user": {k: v for k, v in summary.items() if k != "sheets"},
        "sheets": summary["sheets"],
    }


def get_overview_daily_progress(
    db: Session,
    date_str: Optional[str] = None,
    tz_name: Optional[str] = None,
) -> Dict[str, Any]:
    window = build_time_window(date_str, tz_name)
    sheets = _query_updated_sheets(db, window.start_utc, window.end_utc)
    by_user: Dict[str, List[InquirySheet]] = {}
    for sheet in sheets:
        by_user.setdefault(sheet.user_id, []).append(sheet)

    users = db.query(User).filter(User.id.in_(list(by_user.keys()))).all() if by_user else []
    user_map = {u.id: u for u in users}

    summaries: List[Dict[str, Any]] = []
    total_rows = 0
    total_quoted_rows = 0
    for uid, user_sheets in by_user.items():
        user = user_map.get(uid)
        if not user:
            continue
        summary = _build_user_summary(user, user_sheets)
        total_rows += summary["today_total_rows"]
        total_quoted_rows += summary["today_quoted_rows"]
        summaries.append({k: v for k, v in summary.items() if k != "sheets"})

    summaries.sort(key=lambda x: (-x["today_progress"], -(x["today_total_rows"])))
    overall_progress = round((total_quoted_rows / total_rows), 4) if total_rows else 0.0
    return {
        "date": window.date_label,
        "tz": window.tz_name,
        "kpis": {
            "active_user_count": len(summaries),
            "updated_sheet_count": len(sheets),
            "total_rows": total_rows,
            "quoted_rows": total_quoted_rows,
            "overall_progress": overall_progress,
        },
        "users": summaries,
    }


def publish_user_progress_update(
    db: Session,
    user_id: str,
    date_str: Optional[str] = None,
    tz_name: Optional[str] = None,
) -> None:
    snapshot = get_user_daily_progress(db, user_id=user_id, date_str=date_str, tz_name=tz_name)
    payload = {
        "type": "progress_update",
        "date": snapshot.get("date"),
        "tz": snapshot.get("tz"),
        "user": snapshot.get("user"),
    }
    publish_admin_progress_sync(payload)
