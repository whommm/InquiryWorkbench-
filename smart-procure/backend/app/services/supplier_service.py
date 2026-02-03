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

# 品牌别名映射表（中英文、常见变体）
BRAND_ALIASES = {
    "festo": ["festo", "费斯托", "德国festo", "festo德国"],
    "smc": ["smc", "日本smc", "smc日本"],
    "parker": ["parker", "派克", "美国派克"],
    "bosch": ["bosch", "博世", "力士乐", "rexroth", "bosch rexroth"],
    "siemens": ["siemens", "西门子"],
    "abb": ["abb"],
    "schneider": ["schneider", "施耐德"],
    "omron": ["omron", "欧姆龙"],
    "mitsubishi": ["mitsubishi", "三菱"],
    "keyence": ["keyence", "基恩士"],
    "ifm": ["ifm", "易福门"],
    "sick": ["sick", "西克"],
    "balluff": ["balluff", "巴鲁夫"],
    "turck": ["turck", "图尔克"],
    "phoenix": ["phoenix", "菲尼克斯", "phoenix contact"],
    "wago": ["wago", "万可"],
    "pilz": ["pilz", "皮尔兹"],
    "norgren": ["norgren", "诺冠"],
    "camozzi": ["camozzi", "康茂盛"],
    "airtac": ["airtac", "亚德客"],
}

def _build_brand_lookup() -> Dict[str, str]:
    """构建品牌别名到标准名的映射"""
    lookup = {}
    for standard, aliases in BRAND_ALIASES.items():
        for alias in aliases:
            lookup[alias.lower()] = standard
    return lookup

BRAND_LOOKUP = _build_brand_lookup()


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
        tags: Optional[List[str]] = None,
        created_by: Optional[str] = None
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
                created_by=created_by,
                quote_count=1,
                last_quote_date=datetime.utcnow()
            )
            self.db.add(new_supplier)
            self.db.commit()
            self.db.refresh(new_supplier)
            return new_supplier

    def get_existing_phones(self, phones: List[str]) -> set:
        """检查哪些电话号码已存在于数据库中"""
        if not phones:
            return set()
        existing = self.db.query(Supplier.contact_phone).filter(
            Supplier.contact_phone.in_(phones)
        ).all()
        return set(row[0] for row in existing)

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
        """Delete a supplier and its associated products"""
        supplier = self.get_supplier(supplier_id)
        if supplier:
            # 先删除关联的产品记录
            self.db.query(SupplierProduct).filter(
                SupplierProduct.supplier_id == supplier_id
            ).delete()
            # 再删除供应商
            self.db.delete(supplier)
            self.db.commit()
            return True
        return False

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """Calculate similarity between two strings (0-1)"""
        if not str1 or not str2:
            return 0.0
        return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()

    def _normalize_model(self, model: str) -> str:
        """标准化型号：去除横杠、空格、斜杠，转小写"""
        if not model:
            return ""
        # 去除常见分隔符，转小写
        normalized = re.sub(r'[-_\s/\\.]', '', model.lower())
        return normalized

    def _normalize_brand(self, brand: str) -> str:
        """标准化品牌名：转换为标准名称"""
        if not brand:
            return ""
        brand_lower = brand.strip().lower()
        # 查找别名映射
        return BRAND_LOOKUP.get(brand_lower, brand_lower)

    def _match_brand(self, brand1: str, brand2: str) -> bool:
        """判断两个品牌是否匹配（考虑别名）"""
        if not brand1 or not brand2:
            return False
        return self._normalize_brand(brand1) == self._normalize_brand(brand2)

    def _calculate_model_similarity(self, model1: str, model2: str) -> float:
        """计算型号相似度（标准化后比较）"""
        if not model1 or not model2:
            return 0.0
        norm1 = self._normalize_model(model1)
        norm2 = self._normalize_model(model2)
        # 精确匹配
        if norm1 == norm2:
            return 1.0
        # 包含关系
        if norm1 in norm2 or norm2 in norm1:
            return 0.9
        # 模糊匹配
        return SequenceMatcher(None, norm1, norm2).ratio()

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

        匹配策略（优先级从高到低）：
        1. 品牌+型号双匹配（最高优先级）
        2. 型号精确/模糊匹配
        3. 品牌匹配（含别名）
        4. 产品名称模糊匹配
        """
        logger.info("[推荐] 开始推荐供应商")
        logger.info(f"[推荐] 产品名称: {product_name}, 规格: {spec}, 品牌: {brand}")

        # 获取所有供应商产品记录
        all_products = self.db.query(SupplierProduct).all()
        matched_products = []

        # 标准化输入
        norm_brand = self._normalize_brand(brand) if brand else ""
        norm_spec = self._normalize_model(spec) if spec else ""
        norm_name = self._normalize_model(product_name) if product_name else ""

        # 从 product_name 中提取可能的型号（按空格分割）
        search_terms = []
        if product_name:
            search_terms = [t.strip() for t in product_name.split() if t.strip()]

        logger.info(f"[推荐] 标准化后: norm_brand={norm_brand}, norm_spec={norm_spec}, search_terms={search_terms}")

        for p in all_products:
            score = 0.0
            match_type = "none"
            match_details = []

            # 1. 品牌匹配（含别名）
            brand_matched = False
            if norm_brand and p.brand:
                if self._match_brand(brand, p.brand):
                    brand_matched = True
                    score += 0.4
                    match_details.append("brand")

            # 2. 型号匹配（标准化后）
            model_score = 0.0
            # 优先用 spec 匹配，如果 spec 为空则用 search_terms 中的每个词尝试匹配
            if norm_spec and p.product_model:
                model_score = self._calculate_model_similarity(spec, p.product_model)
            elif search_terms and p.product_model:
                # 用 product_name 中的每个词尝试匹配型号
                for term in search_terms:
                    term_score = self._calculate_model_similarity(term, p.product_model)
                    if term_score > model_score:
                        model_score = term_score

            if model_score >= 0.6:  # 降低阈值
                score += model_score * 0.5
                match_details.append(f"model({model_score:.2f})")

            # 3. 产品名称匹配
            name_score = 0.0
            if p.product_name:
                # 用整个 product_name 匹配
                if norm_name:
                    name_score = self._calculate_model_similarity(product_name, p.product_name)
                # 也用 search_terms 中的每个词尝试匹配
                if search_terms:
                    for term in search_terms:
                        term_score = self._calculate_model_similarity(term, p.product_name)
                        if term_score > name_score:
                            name_score = term_score

            if name_score >= 0.4:  # 降低阈值
                score += name_score * 0.3
                match_details.append(f"name({name_score:.2f})")

            # 确定匹配类型
            if brand_matched and model_score >= 0.6:
                match_type = "brand+model"
                score += 0.2  # 双匹配加分
            elif model_score >= 0.8:
                match_type = "model_exact"
            elif model_score >= 0.6:
                match_type = "model_fuzzy"
            elif brand_matched:
                match_type = "brand"
            elif name_score >= 0.4:
                match_type = "name"

            # 只保留有效匹配（降低阈值以获得更多结果）
            if score >= 0.2:
                matched_products.append({
                    "product": p,
                    "match_type": match_type,
                    "match_score": score,
                    "match_details": match_details
                })

        logger.info(f"[推荐] 匹配到 {len(matched_products)} 条产品记录")

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
                    "match_types": [],
                    "brands": set()
                }
            stats = supplier_stats[sid]
            stats["products"].append({
                "name": p.product_name,
                "model": p.product_model,
                "brand": p.brand,
                "price": p.last_price,
                "quote_count": p.quote_count,
                "match_type": item["match_type"],
                "match_score": item["match_score"]
            })
            stats["total_quote_count"] += p.quote_count
            if p.last_price:
                stats["prices"].append(p.last_price)
            stats["match_scores"].append(item["match_score"])
            stats["match_types"].append(item["match_type"])
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
            max_score = max(stats["match_scores"])
            avg_price = sum(stats["prices"]) / len(stats["prices"]) if stats["prices"] else 0

            # 匹配类型加权：brand+model > model_exact > model_fuzzy > brand > name
            type_bonus = 0.0
            if "brand+model" in stats["match_types"]:
                type_bonus = 0.3
            elif "model_exact" in stats["match_types"]:
                type_bonus = 0.2
            elif "model_fuzzy" in stats["match_types"]:
                type_bonus = 0.1

            # 综合推荐分数 = 匹配分数(50%) + 类型加分(20%) + 报价次数(30%)
            recommendation_score = (
                max_score * 0.5 +
                type_bonus +
                min(stats["total_quote_count"] / 10, 1) * 0.3
            )

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
                "best_match_type": stats["match_types"][0] if stats["match_types"] else "none",
                "recommendation_score": recommendation_score,
                "created_by": supplier.created_by
            })

        # 按推荐分数排序
        recommendations.sort(key=lambda x: x["recommendation_score"], reverse=True)
        top_recommendations = recommendations[:limit]

        logger.info(f"[推荐] 返回 {len(top_recommendations)} 个供应商")
        return top_recommendations
