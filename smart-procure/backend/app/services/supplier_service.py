"""
Supplier service for CRUD operations
"""
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from app.models.database import Supplier, InquirySheet
from difflib import SequenceMatcher
import re


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
        import re
        match = re.search(r'^(.+?(?:公司|集团|厂|中心|部))', supplier_str)
        if match:
            return match.group(1).strip()

        # Fallback: take first part before space
        parts = supplier_str.split()
        return parts[0] if parts else supplier_str

    def _extract_quote_history(
        self,
        product_name: str,
        spec: str = "",
        brand: str = ""
    ) -> List[Dict[str, Any]]:
        """Extract quote history for a specific product from all inquiry sheets"""
        quote_history = []

        # Get all inquiry sheets
        sheets = self.db.query(InquirySheet).all()
        print(f"[推荐-历史] 数据库中有 {len(sheets)} 个询价单")

        for sheet in sheets:
            sheet_data = sheet.sheet_data
            if not sheet_data or len(sheet_data) < 2:
                print(f"[推荐-历史] 跳过询价单 {sheet.id}：数据为空或行数不足")
                continue

            print(f"[推荐-历史] 处理询价单 {sheet.id}，共 {len(sheet_data)} 行")

            # Dynamically identify column indices from headers
            headers = sheet_data[0]
            brand_col = next((i for i, h in enumerate(headers) if str(h) == '品牌'), None)
            name_col = next((i for i, h in enumerate(headers) if str(h) in ['物料名称', '产品名称', '名称']), None)
            spec_col = next((i for i, h in enumerate(headers) if str(h) in ['规格型号', '型号', '规格']), None)

            print(f"[推荐-历史] 识别到的列索引: 品牌={brand_col}, 名称={name_col}, 规格={spec_col}")

            # Skip header row
            for row_idx, row in enumerate(sheet_data[1:], start=2):
                if len(row) < 5:
                    continue

                # Extract product info from row using dynamic column indices
                row_product_name = str(row[name_col]) if name_col is not None and len(row) > name_col else ""
                row_brand = str(row[brand_col]) if brand_col is not None and len(row) > brand_col else ""
                row_spec = str(row[spec_col]) if spec_col is not None and len(row) > spec_col else ""

                # Smart matching strategy: prioritize brand exact match, fallback to fuzzy match
                matched = False
                match_score = 0.0

                if brand and row_brand:
                    # Priority: Brand exact match
                    if brand.lower() == row_brand.lower():
                        matched = True
                        match_score = 1.0
                        if row_idx <= 3:
                            print(f"[推荐-历史] 行{row_idx}: ✓ 品牌匹配 '{brand}' - 产品={row_product_name}")
                else:
                    # Fallback: Fuzzy matching by product name or spec
                    name_similarity = self._calculate_similarity(product_name, row_product_name) if product_name and row_product_name else 0.0
                    spec_similarity = self._calculate_similarity(spec, row_spec) if spec and row_spec else 0.0

                    # Require at least one field to have decent similarity (threshold: 0.6)
                    if name_similarity >= 0.6 or spec_similarity >= 0.6:
                        matched = True
                        match_score = max(name_similarity, spec_similarity)
                        if row_idx <= 3:
                            print(f"[推荐-历史] 行{row_idx}: ✓ 模糊匹配 - 产品={row_product_name}, 相似度={name_similarity:.2f}/{spec_similarity:.2f}")

                if not matched:
                    continue

                # Extract quotes from the 3 slots (columns 8-28)
                # Slot structure: 品牌, 单价, 含税, 含运, 货期, 备注, 供应商 (7 columns per slot)
                for slot_idx in range(3):
                    base_col = 8 + slot_idx * 7
                    if len(row) <= base_col + 6:
                        continue

                    slot_brand = str(row[base_col]) if row[base_col] else ""
                    slot_price = row[base_col + 1]
                    slot_supplier = str(row[base_col + 6]) if row[base_col + 6] else ""
                    slot_delivery = str(row[base_col + 4]) if row[base_col + 4] else ""

                    # Skip empty slots
                    if not slot_supplier or not slot_price:
                        continue

                    try:
                        price_value = float(slot_price)
                    except:
                        continue

                    # Parse and match supplier to database
                    parsed_name = self._parse_supplier_name(slot_supplier)

                    # Try exact match first
                    supplier = self.db.query(Supplier).filter(
                        Supplier.company_name == parsed_name
                    ).first()

                    # If no exact match, try fuzzy match
                    if not supplier:
                        all_suppliers = self.db.query(Supplier).all()
                        best_match = None
                        best_score = 0.0

                        for s in all_suppliers:
                            score = self._calculate_similarity(parsed_name, s.company_name)
                            if score > best_score and score >= 0.7:
                                best_score = score
                                best_match = s

                        supplier = best_match

                    # Only record if supplier exists in database
                    if supplier:
                        quote_history.append({
                            "supplier_id": supplier.id,
                            "supplier_name": supplier.company_name,
                            "price": price_value,
                            "brand": slot_brand,
                            "delivery_time": slot_delivery,
                            "product_name": row_product_name,
                            "spec": row_spec,
                            "quote_date": sheet.updated_at,
                            "match_score": match_score
                        })

        return quote_history

    def recommend_suppliers(
        self,
        product_name: str,
        spec: str = "",
        brand: str = "",
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Recommend top suppliers for a specific product"""
        print(f"[推荐] 开始推荐供应商")
        print(f"[推荐] 产品名称: {product_name}")
        print(f"[推荐] 规格: {spec}")
        print(f"[推荐] 品牌: {brand}")

        # Extract quote history
        quote_history = self._extract_quote_history(product_name, spec, brand)

        print(f"[推荐] 找到 {len(quote_history)} 条历史报价记录")
        if quote_history:
            print(f"[推荐] 前3条记录:")
            for i, quote in enumerate(quote_history[:3], 1):
                print(f"  {i}. 供应商: {quote['supplier_name']}, 价格: {quote['price']}, 匹配分数: {quote['match_score']:.2f}")

        if not quote_history:
            # No history found, return empty list
            print(f"[推荐] 没有找到历史报价记录，返回空列表")
            return []

        # Aggregate by supplier_id
        supplier_stats = {}
        for quote in quote_history:
            supplier_id = quote["supplier_id"]
            if supplier_id not in supplier_stats:
                supplier_stats[supplier_id] = {
                    "supplier_id": supplier_id,
                    "supplier_name": quote["supplier_name"],
                    "quote_count": 0,
                    "prices": [],
                    "delivery_times": [],
                    "brands": set(),
                    "last_quote_date": quote["quote_date"],
                    "match_scores": []
                }

            stats = supplier_stats[supplier_id]
            stats["quote_count"] += 1
            stats["prices"].append(quote["price"])
            stats["delivery_times"].append(quote["delivery_time"])
            stats["brands"].add(quote["brand"])
            stats["match_scores"].append(quote["match_score"])

            # Update last quote date
            if quote["quote_date"] > stats["last_quote_date"]:
                stats["last_quote_date"] = quote["quote_date"]

        # Calculate recommendation scores
        recommendations = []
        for supplier_id, stats in supplier_stats.items():
            avg_price = sum(stats["prices"]) / len(stats["prices"])
            avg_match_score = sum(stats["match_scores"]) / len(stats["match_scores"])

            # Calculate time freshness (0-1, more recent = higher)
            days_since_last_quote = (datetime.utcnow() - stats["last_quote_date"]).days
            time_freshness = max(0, 1 - days_since_last_quote / 365)

            # Normalize values for scoring
            # We'll calculate relative scores after collecting all suppliers
            recommendations.append({
                "supplier_id": supplier_id,
                "supplier_name": stats["supplier_name"],
                "quote_count": stats["quote_count"],
                "avg_price": avg_price,
                "min_price": min(stats["prices"]),
                "max_price": max(stats["prices"]),
                "brands": list(stats["brands"]),
                "last_quote_date": stats["last_quote_date"],
                "time_freshness": time_freshness,
                "avg_match_score": avg_match_score,
                "delivery_times": stats["delivery_times"]
            })

        if not recommendations:
            return []

        # Normalize and calculate final scores
        max_quote_count = max(r["quote_count"] for r in recommendations)
        min_price = min(r["avg_price"] for r in recommendations)
        max_price = max(r["avg_price"] for r in recommendations)
        price_range = max_price - min_price if max_price > min_price else 1

        for rec in recommendations:
            # Normalize values (0-1)
            norm_quote_count = rec["quote_count"] / max_quote_count
            norm_price = 1 - (rec["avg_price"] - min_price) / price_range  # Lower price = higher score

            # Calculate final score with weights
            score = (
                0.3 * norm_quote_count +      # Experience weight
                0.4 * norm_price +             # Price weight (most important)
                0.2 * rec["time_freshness"] +  # Recency weight
                0.1 * rec["avg_match_score"]   # Match quality weight
            )
            rec["recommendation_score"] = score

        # Sort by score and return top N
        recommendations.sort(key=lambda x: x["recommendation_score"], reverse=True)
        top_recommendations = recommendations[:limit]

        # Enrich with contact details from database
        for rec in top_recommendations:
            supplier = self.db.query(Supplier).filter(
                Supplier.id == rec["supplier_id"]
            ).first()

            if supplier:
                rec["contact_name"] = supplier.contact_name
                rec["contact_phone"] = supplier.contact_phone
                rec["company_name"] = supplier.company_name

        return top_recommendations
