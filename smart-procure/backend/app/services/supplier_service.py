"""
Supplier service for CRUD operations
"""
import logging
import re
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from app.models.database import Supplier, InquirySheet, SupplierProduct
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


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

    def upsert_supplier_product(
        self,
        supplier_id: int,
        product_name: Optional[str] = None,
        product_model: Optional[str] = None,
        brand: Optional[str] = None,
        price: Optional[float] = None
    ) -> Optional[SupplierProduct]:
        """保存供应商-产品关联信息"""
        if not product_name and not product_model:
            return None

        # 查找是否已存在相同的供应商-产品记录
        query = self.db.query(SupplierProduct).filter(
            SupplierProduct.supplier_id == supplier_id
        )

        if product_name:
            query = query.filter(SupplierProduct.product_name == product_name)
        if product_model:
            query = query.filter(SupplierProduct.product_model == product_model)

        existing = query.first()

        if existing:
            # 更新现有记录
            if brand:
                existing.brand = brand
            if price is not None:
                existing.last_price = price
            existing.quote_count += 1
            existing.updated_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(existing)
            return existing
        else:
            # 创建新记录
            new_record = SupplierProduct(
                supplier_id=supplier_id,
                product_name=product_name,
                product_model=product_model,
                brand=brand,
                last_price=price,
                quote_count=1
            )
            self.db.add(new_record)
            self.db.commit()
            self.db.refresh(new_record)
            return new_record

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

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """Calculate similarity between two strings (0-1)"""
        if not str1 or not str2:
            return 0.0
        return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()

    def _parse_supplier_name(self, supplier_str: str) -> str:
        """Parse supplier string to extract company name
        Format: '公司名称 联系人 电话' -> '公司名称'
        """
        if not supplier_str:
            return ""

        # Remove extra spaces
        supplier_str = " ".join(supplier_str.split())

        # Try to extract company name (before first person name or phone)
        # Pattern: company name usually ends with '公司', '有限公司', '集团' etc.
        match = re.search(r'^(.+?(?:公司|集团|厂|中心|部))', supplier_str)
        if match:
            return match.group(1).strip()

        # Fallback: take first part before space
        parts = supplier_str.split()
        return parts[0] if parts else supplier_str

    def recommend_suppliers(
        self,
        product_name: str,
        spec: str = "",
        brand: str = "",
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """基于 SupplierProduct 表推荐供应商

        匹配策略：
        1. 品牌优先：如果有品牌，优先匹配品牌
        2. 降级匹配：无品牌时，用产品名称或型号模糊匹配
        """
        logger.info("[推荐] 开始推荐供应商")
        logger.info(f"[推荐] 产品名称: {product_name}, 规格: {spec}, 品牌: {brand}")

        matched_products = []

        # 策略1：品牌精确匹配
        if brand and brand.strip():
            brand_clean = brand.strip()
            products = self.db.query(SupplierProduct).filter(
                SupplierProduct.brand == brand_clean
            ).all()
            for p in products:
                matched_products.append({
                    "product": p,
                    "match_type": "brand",
                    "match_score": 1.0
                })
            logger.info(f"[推荐] 品牌匹配找到 {len(products)} 条记录")

        # 策略2：产品名称/型号模糊匹配（当品牌匹配结果不足时）
        if len(matched_products) < limit:
            search_terms = []
            if product_name and product_name.strip():
                search_terms.append(product_name.strip())
            if spec and spec.strip():
                search_terms.append(spec.strip())

            for term in search_terms:
                # 使用 LIKE 进行模糊匹配
                products = self.db.query(SupplierProduct).filter(
                    (SupplierProduct.product_name.like(f"%{term}%")) |
                    (SupplierProduct.product_model.like(f"%{term}%"))
                ).all()

                for p in products:
                    # 避免重复
                    if any(m["product"].id == p.id for m in matched_products):
                        continue
                    # 计算相似度
                    name_sim = self._calculate_similarity(term, p.product_name or "")
                    model_sim = self._calculate_similarity(term, p.product_model or "")
                    score = max(name_sim, model_sim)
                    if score >= 0.3:  # 降低阈值以获得更多结果
                        matched_products.append({
                            "product": p,
                            "match_type": "fuzzy",
                            "match_score": score
                        })

            logger.info(f"[推荐] 模糊匹配后共 {len(matched_products)} 条记录")

        if not matched_products:
            logger.info("[推荐] 没有找到匹配的产品记录")
            return []

        # 按供应商聚合
        supplier_stats: Dict[int, Dict[str, Any]] = {}
        for item in matched_products:
            p = item["product"]
            sid = p.supplier_id
            if sid not in supplier_stats:
                supplier_stats[sid] = {
                    "supplier_id": sid,
                    "products": [],
                    "total_quote_count": 0,
                    "prices": [],
                    "match_scores": [],
                    "brands": set()
                }
            stats = supplier_stats[sid]
            stats["products"].append({
                "name": p.product_name,
                "model": p.product_model,
                "brand": p.brand,
                "price": p.last_price,
                "quote_count": p.quote_count
            })
            stats["total_quote_count"] += p.quote_count
            if p.last_price:
                stats["prices"].append(p.last_price)
            stats["match_scores"].append(item["match_score"])
            if p.brand:
                stats["brands"].add(p.brand)

        # 构建推荐列表 - 批量查询供应商避免N+1问题
        supplier_ids = list(supplier_stats.keys())
        suppliers = self.db.query(Supplier).filter(Supplier.id.in_(supplier_ids)).all()
        supplier_map = {s.id: s for s in suppliers}

        recommendations = []
        for sid, stats in supplier_stats.items():
            supplier = supplier_map.get(sid)
            if not supplier:
                continue

            avg_score = sum(stats["match_scores"]) / len(stats["match_scores"])
            avg_price = sum(stats["prices"]) / len(stats["prices"]) if stats["prices"] else 0

            recommendations.append({
                "supplier_id": sid,
                "supplier_name": supplier.company_name,
                "company_name": supplier.company_name,
                "contact_name": supplier.contact_name,
                "contact_phone": supplier.contact_phone,
                "quote_count": stats["total_quote_count"],
                "avg_price": avg_price,
                "min_price": min(stats["prices"]) if stats["prices"] else 0,
                "max_price": max(stats["prices"]) if stats["prices"] else 0,
                "brands": list(stats["brands"]),
                "products": stats["products"][:5],
                "delivery_times": [],
                "last_quote_date": supplier.last_quote_date or supplier.updated_at,
                "avg_match_score": avg_score,
                "recommendation_score": avg_score * 0.4 + min(stats["total_quote_count"] / 10, 1) * 0.6
            })

        # 按推荐分数排序
        recommendations.sort(key=lambda x: x["recommendation_score"], reverse=True)
        top_recommendations = recommendations[:limit]

        logger.info(f"[推荐] 返回 {len(top_recommendations)} 个供应商")
        return top_recommendations
