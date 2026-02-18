import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth.utils import get_current_user, require_admin_user
from ..core.datetime_utils import ensure_utc, utc_now
from ..models.database import User, get_db
from ..services.supplier_service import SupplierService

logger = logging.getLogger(__name__)

router = APIRouter()


class RecommendRequest(BaseModel):
    product_name: str = Field("", max_length=200, description="产品名称")
    spec: Optional[str] = Field("", max_length=500, description="规格型号")
    brand: Optional[str] = Field("", max_length=100, description="品牌")
    limit: Optional[int] = Field(5, ge=1, le=20, description="返回数量限制")


@router.get("/suppliers/search")
async def search_suppliers(
    q: str,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search suppliers by name, phone, or contact."""
    try:
        supplier_service = SupplierService(db)
        suppliers = supplier_service.search_suppliers(q, limit=limit)
        result = []
        for s in suppliers:
            result.append(
                {
                    "id": s.id,
                    "company_name": s.company_name,
                    "contact_phone": s.contact_phone,
                    "contact_name": s.contact_name,
                    "owner": s.owner,
                    "tags": s.tags or [],
                    "quote_count": s.quote_count,
                    "last_quote_date": s.last_quote_date.isoformat() if s.last_quote_date else None,
                }
            )
        return {"suppliers": result}
    except Exception as e:
        logger.exception("Failed to search suppliers")
        raise HTTPException(status_code=500, detail="Failed to search suppliers")


@router.get("/suppliers/list")
async def list_suppliers_endpoint(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get list of suppliers."""
    try:
        supplier_service = SupplierService(db)
        suppliers = supplier_service.list_suppliers(limit=limit, offset=offset)

        result = []
        for s in suppliers:
            created_by_name = None
            if s.created_by:
                creator = db.query(User).filter(User.id == s.created_by).first()
                if creator:
                    created_by_name = creator.display_name or creator.username

            result.append(
                {
                    "id": s.id,
                    "company_name": s.company_name,
                    "contact_phone": s.contact_phone,
                    "contact_name": s.contact_name,
                    "owner": s.owner,
                    "tags": s.tags or [],
                    "quote_count": s.quote_count,
                    "last_quote_date": s.last_quote_date.isoformat() if s.last_quote_date else None,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                    "created_by_name": created_by_name,
                }
            )

        return {"suppliers": result, "total": len(result)}
    except Exception as e:
        logger.exception("Failed to list suppliers")
        raise HTTPException(status_code=500, detail="Failed to list suppliers")


@router.delete("/suppliers/{supplier_id}")
async def delete_supplier_endpoint(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user),
):
    """Delete a supplier."""
    try:
        supplier_service = SupplierService(db)
        success = supplier_service.delete_supplier(supplier_id)
        if not success:
            raise HTTPException(status_code=404, detail="Supplier not found")
        return {"message": "删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to delete supplier")
        raise HTTPException(status_code=500, detail="Failed to delete supplier")


@router.post("/suppliers/recommend")
async def recommend_suppliers_endpoint(
    request: RecommendRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recommend top suppliers for a specific product."""
    try:
        supplier_service = SupplierService(db)
        recommendations = supplier_service.recommend_suppliers(
            product_name=request.product_name,
            spec=request.spec or "",
            brand=request.brand or "",
            limit=request.limit or 5,
        )

        result = []
        creator_ids = [rec.get("created_by") for rec in recommendations if rec.get("created_by")]
        creators = {}
        if creator_ids:
            users = db.query(User).filter(User.id.in_(creator_ids)).all()
            creators = {u.id: u.display_name or u.username for u in users}

        for idx, rec in enumerate(recommendations, start=1):
            star_rating = max(1, min(5, int(rec["recommendation_score"] * 5) + 1))
            last_quote_date = ensure_utc(rec.get("last_quote_date"))
            if last_quote_date is None:
                days_ago = None
            else:
                days_ago = (utc_now() - last_quote_date).days

            if days_ago == 0:
                last_quote_text = "today"
            elif days_ago == 1:
                last_quote_text = "1 day ago"
            elif isinstance(days_ago, int) and days_ago < 30:
                last_quote_text = f"{days_ago} days ago"
            elif isinstance(days_ago, int) and days_ago < 365:
                last_quote_text = f"{days_ago // 30} months ago"
            elif isinstance(days_ago, int):
                last_quote_text = f"{days_ago // 365} years ago"
            else:
                last_quote_text = "unknown"

            result.append(
                {
                    "rank": idx,
                    "supplier_id": rec.get("supplier_id"),
                    "company_name": rec.get("company_name", rec["supplier_name"]),
                    "contact_name": rec.get("contact_name"),
                    "contact_phone": rec.get("contact_phone"),
                    "quote_count": rec["quote_count"],
                    "avg_price": round(rec["avg_price"], 2),
                    "min_price": round(rec["min_price"], 2),
                    "max_price": round(rec["max_price"], 2),
                    "last_quote_date": rec["last_quote_date"].isoformat(),
                    "last_quote_text": last_quote_text,
                    "star_rating": star_rating,
                    "recommendation_score": round(rec["recommendation_score"], 3),
                    "brands": rec["brands"],
                    "products": rec.get("products", []),
                    "delivery_times": rec.get("delivery_times", [])[:3],
                    "created_by_name": creators.get(rec.get("created_by")),
                }
            )

        return {
            "recommendations": result,
            "total": len(result),
            "query": {
                "product_name": request.product_name,
                "spec": request.spec,
                "brand": request.brand,
            },
        }
    except Exception as e:
        logger.exception("Failed to recommend suppliers")
        raise HTTPException(status_code=500, detail="Failed to recommend suppliers")


@router.post("/suppliers/recommend/v2")
async def recommend_suppliers_v2_endpoint(
    request: RecommendRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recommend top suppliers using vector search (V2)."""
    try:
        supplier_service = SupplierService(db)
        recommendations = supplier_service.recommend_suppliers_v2(
            product_name=request.product_name,
            spec=request.spec or "",
            brand=request.brand or "",
            limit=request.limit or 5,
        )

        result = []
        for idx, rec in enumerate(recommendations, start=1):
            star_rating = max(1, min(5, int(rec["recommendation_score"] * 5) + 1))
            last_quote_date = ensure_utc(rec.get("last_quote_date"))
            if last_quote_date is None:
                days_ago = None
            else:
                days_ago = (utc_now() - last_quote_date).days

            if days_ago == 0:
                last_quote_text = "today"
            elif days_ago == 1:
                last_quote_text = "1 day ago"
            elif isinstance(days_ago, int) and days_ago < 30:
                last_quote_text = f"{days_ago} days ago"
            elif isinstance(days_ago, int) and days_ago < 365:
                last_quote_text = f"{days_ago // 30} months ago"
            elif isinstance(days_ago, int):
                last_quote_text = f"{days_ago // 365} years ago"
            else:
                last_quote_text = "unknown"

            result.append(
                {
                    "rank": idx,
                    "supplier_id": rec["supplier_id"],
                    "company_name": rec["company_name"],
                    "contact_name": rec["contact_name"],
                    "contact_phone": rec["contact_phone"],
                    "quote_count": rec["quote_count"],
                    "star_rating": star_rating,
                    "recommendation_score": round(rec["recommendation_score"], 3),
                    "avg_similarity": round(rec.get("avg_similarity", 0), 3),
                    "max_similarity": round(rec.get("max_similarity", 0), 3),
                    "brands": rec["brands"],
                    "products": rec.get("products", []),
                }
            )

        return {
            "recommendations": result,
            "total": len(result),
            "version": "v2",
            "query": {
                "product_name": request.product_name,
                "spec": request.spec,
                "brand": request.brand,
            },
        }
    except Exception as e:
        logger.exception("Failed to recommend suppliers")
        raise HTTPException(status_code=500, detail="Failed to recommend suppliers")

