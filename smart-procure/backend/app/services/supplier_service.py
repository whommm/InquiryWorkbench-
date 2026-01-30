"""
Supplier service for CRUD operations
"""
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional
from datetime import datetime
from app.models.database import Supplier


class SupplierService:
    """Service for managing suppliers in database"""

    def __init__(self, db: Session):
        self.db = db

    def upsert_supplier(
        self,
        company_name: str,
        contact_phone: str,
        owner: str = "系统自动",
        contact_name: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Supplier:
        """Insert or update a supplier based on company_name"""
        existing = self.db.query(Supplier).filter(
            Supplier.company_name == company_name
        ).first()

        if existing:
            # Update existing supplier
            existing.contact_phone = contact_phone
            existing.owner = owner
            if contact_name:
                existing.contact_name = contact_name
            if tags:
                # Merge tags (avoid duplicates)
                existing_tags = existing.tags or []
                merged_tags = list(set(existing_tags + tags))
                existing.tags = merged_tags
            existing.quote_count += 1
            existing.last_quote_date = datetime.utcnow()
            existing.updated_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(existing)
            return existing
        else:
            # Create new supplier
            new_supplier = Supplier(
                company_name=company_name,
                contact_phone=contact_phone,
                owner=owner,
                contact_name=contact_name,
                tags=tags or [],
                quote_count=1,
                last_quote_date=datetime.utcnow()
            )
            self.db.add(new_supplier)
            self.db.commit()
            self.db.refresh(new_supplier)
            return new_supplier

    def search_suppliers(self, query: str, limit: int = 10) -> List[Supplier]:
        """Search suppliers by name, phone, or contact name"""
        return (
            self.db.query(Supplier)
            .filter(
                or_(
                    Supplier.company_name.like(f"%{query}%"),
                    Supplier.contact_phone.like(f"%{query}%"),
                    Supplier.contact_name.like(f"%{query}%")
                )
            )
            .order_by(Supplier.quote_count.desc())
            .limit(limit)
            .all()
        )

    def get_supplier(self, supplier_id: int) -> Optional[Supplier]:
        """Get a single supplier by ID"""
        return self.db.query(Supplier).filter(Supplier.id == supplier_id).first()

    def list_suppliers(self, limit: int = 50, offset: int = 0) -> List[Supplier]:
        """Get list of suppliers, ordered by quote_count descending"""
        return (
            self.db.query(Supplier)
            .order_by(Supplier.quote_count.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def delete_supplier(self, supplier_id: int) -> bool:
        """Delete a supplier"""
        supplier = self.get_supplier(supplier_id)
        if supplier:
            self.db.delete(supplier)
            self.db.commit()
            return True
        return False
