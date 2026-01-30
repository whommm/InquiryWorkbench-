"""
Database service for inquiry sheet operations
"""
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from app.models.database import InquirySheet


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
        item_count: int = 0,
        completion_rate: float = 0.0
    ) -> InquirySheet:
        """Save or update an inquiry sheet"""
        existing = self.db.query(InquirySheet).filter(InquirySheet.id == sheet_id).first()

        if existing:
            # Update existing sheet
            existing.name = name
            existing.sheet_data = sheet_data
            existing.chat_history = chat_history
            existing.item_count = item_count
            existing.completion_rate = completion_rate
            existing.updated_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(existing)
            return existing
        else:
            # Create new sheet
            new_sheet = InquirySheet(
                id=sheet_id,
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

    def get_sheet(self, sheet_id: str) -> Optional[InquirySheet]:
        """Get a single inquiry sheet by ID"""
        return self.db.query(InquirySheet).filter(InquirySheet.id == sheet_id).first()

    def list_sheets(self, limit: int = 50, offset: int = 0) -> List[InquirySheet]:
        """Get list of inquiry sheets, ordered by updated_at descending"""
        return (
            self.db.query(InquirySheet)
            .order_by(InquirySheet.updated_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def delete_sheet(self, sheet_id: str) -> bool:
        """Delete an inquiry sheet"""
        sheet = self.get_sheet(sheet_id)
        if sheet:
            self.db.delete(sheet)
            self.db.commit()
            return True
        return False
