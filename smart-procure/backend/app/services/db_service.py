"""
Database service for inquiry sheet operations
"""
from sqlalchemy.orm import Session
from typing import List, Optional
from app.models.database import InquirySheet
from app.core.datetime_utils import ensure_utc, utc_now


class SheetConflictError(Exception):
    """Raised when optimistic concurrency check fails for a sheet save."""

    def __init__(self, sheet: InquirySheet, reason: str = "stale_base"):
        super().__init__(reason)
        self.sheet = sheet
        self.reason = reason


class DBService:
    """Service for managing inquiry sheets in database"""

    def __init__(self, db: Session):
        self.db = db

    def save_sheet(
        self,
        sheet_id: str,
        name: str,
        sheet_data: list,
        chat_history: list,
        user_id: str,
        item_count: int = 0,
        completion_rate: float = 0.0,
        expected_updated_at=None,
        force_overwrite: bool = False,
    ) -> InquirySheet:
        """Save or update an inquiry sheet"""
        existing = self.db.query(InquirySheet).filter(
            InquirySheet.id == sheet_id,
            InquirySheet.user_id == user_id
        ).first()

        if existing:
            existing_updated_at = ensure_utc(existing.updated_at)
            expected = ensure_utc(expected_updated_at) if expected_updated_at is not None else None
            if not force_overwrite:
                if expected is None:
                    raise SheetConflictError(existing, reason="missing_base")
                if existing_updated_at and existing_updated_at > expected:
                    raise SheetConflictError(existing, reason="stale_base")

            # Update existing sheet
            existing.name = name
            existing.sheet_data = sheet_data
            existing.chat_history = chat_history
            existing.item_count = item_count
            existing.completion_rate = completion_rate
            existing.updated_at = utc_now()
            self.db.commit()
            self.db.refresh(existing)
            return existing
        else:
            # Create new sheet
            new_sheet = InquirySheet(
                id=sheet_id,
                user_id=user_id,
                name=name,
                sheet_data=sheet_data,
                chat_history=chat_history,
                item_count=item_count,
                completion_rate=completion_rate
            )
            self.db.add(new_sheet)
            self.db.commit()
            self.db.refresh(new_sheet)
            return new_sheet

    def get_sheet(self, sheet_id: str, user_id: str) -> Optional[InquirySheet]:
        """Get a single inquiry sheet by ID"""
        return self.db.query(InquirySheet).filter(
            InquirySheet.id == sheet_id,
            InquirySheet.user_id == user_id
        ).first()

    def list_sheets(self, user_id: str, limit: int = 50, offset: int = 0) -> List[InquirySheet]:
        """Get list of inquiry sheets, ordered by updated_at descending"""
        return (
            self.db.query(InquirySheet)
            .filter(InquirySheet.user_id == user_id)
            .order_by(InquirySheet.updated_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def delete_sheet(self, sheet_id: str, user_id: str) -> bool:
        """Delete an inquiry sheet"""
        sheet = self.get_sheet(sheet_id, user_id)
        if sheet:
            self.db.delete(sheet)
            self.db.commit()
            return True
        return False
