"""
Supplier service for CRUD operations
"""
import logging
import re
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional, Dict, Any
from app.models.database import Supplier, InquirySheet, SupplierProduct
from difflib import SequenceMatcher
from app.core.datetime_utils import utc_now, ensure_utc

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


def normalize_phone(phone: str) -> str:
    """标准化电话号码：去除所有非数字字符"""
    if not phone:
        return ""
    return re.sub(r'\D', '', phone)


def normalize_company_name(name: str) -> str:
    """标准化公司名称：去除常见后缀和空格"""
    if not name:
        return ""
    # 去除常见后缀
    suffixes = ['有限公司', '有限责任公司', '股份有限公司', '集团', '公司', '（', '）', '(', ')']
    result = name.strip()
    for suffix in suffixes:
        result = result.replace(suffix, '')
    # 去除"市"前面的省份名
    result = re.sub(r'^(广东|江苏|浙江|上海|北京|山东|福建|湖北|湖南|四川|河南|河北|安徽|陕西|辽宁|天津|重庆)', '', result)
    return result.strip()


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
        # 标准化电话号码
        normalized_phone = normalize_phone(contact_phone)

        # 先精确匹配
        existing = self.db.query(Supplier).filter(
            Supplier.company_name == company_name
        ).first()

        # 如果精确匹配失败，尝试模糊匹配
        if not existing and normalized_phone:
            existing = self.db.query(Supplier).filter(
                Supplier.contact_phone == normalized_phone
            ).first()

        # 如果还没找到，尝试公司名称模糊匹配
        if not existing:
            norm_name = normalize_company_name(company_name)
            if len(norm_name) >= 4:
                candidates = self.db.query(Supplier).all()
                for c in candidates:
                    if normalize_company_name(c.company_name) == norm_name:
                        existing = c
                        break

        if existing:
            # Update existing supplier
            existing.contact_phone = normalized_phone
            existing.owner = owner
            if contact_name:
                existing.contact_name = contact_name
            if tags:
                # Merge tags (avoid duplicates)
                existing_tags = existing.tags or []
                merged_tags = list(set(existing_tags + tags))
                existing.tags = merged_tags
            existing.quote_count += 1
            existing.last_quote_date = utc_now()
            existing.updated_at = utc_now()
            self.db.commit()
            self.db.refresh(existing)
            return existing
        else:
            # Create new supplier
            new_supplier = Supplier(
                company_name=company_name,
                contact_phone=normalized_phone,
                owner=owner,
                contact_name=contact_name,
                tags=tags or [],
                created_by=created_by,
                quote_count=1,
                last_quote_date=utc_now()
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
        """保存供应商-产品关联信息，并同步更新 Qdrant 索引"""
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
        target_record = None

        if existing:
            # 更新现有记录
            if brand:
                existing.brand = brand
            if price is not None:
                existing.last_price = price
            existing.quote_count += 1
            existing.updated_at = utc_now()
            self.db.commit()
            self.db.refresh(existing)
            target_record = existing
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
            target_record = new_record
        
        # 同步更新 Qdrant 索引
        if target_record:
            try:
                # 局部导入避免循环依赖
                from app.services.embedding_index_service import EmbeddingIndexService
                embedding_service = EmbeddingIndexService(self.db)
                embedding_service.index_product(target_record)
                logger.info(f"已同步更新产品索引: {target_record.id}")
            except Exception as e:
                # 索引失败不应阻塞主流程
                logger.error(f"同步更新索引失败: {e}")

        return target_record

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

        # 标准化输入
        norm_brand = self._normalize_brand(brand) if brand else ""
        norm_spec = self._normalize_model(spec) if spec else ""
        norm_name = self._normalize_model(product_name) if product_name else ""

        # 从 product_name 中提取可能的型号（按空格分割）
        search_terms = []
        if product_name:
            search_terms = [t.strip() for t in product_name.split() if t.strip()]

        logger.info(f"[推荐] 标准化后: norm_brand={norm_brand}, norm_spec={norm_spec}, search_terms={search_terms}")

        # SQL 预过滤：构建 LIKE 条件减少加载量
        query = self.db.query(SupplierProduct)
        filters = []
        if brand:
            filters.append(SupplierProduct.brand.ilike(f"%{brand}%"))
        if spec:
            filters.append(SupplierProduct.product_model.ilike(f"%{spec}%"))
        for term in search_terms[:3]:  # 限制搜索词数量
            if len(term) >= 2:
                filters.append(SupplierProduct.product_name.ilike(f"%{term}%"))
                filters.append(SupplierProduct.product_model.ilike(f"%{term}%"))

        if filters:
            query = query.filter(or_(*filters))

        all_products = query.limit(1000).all()  # 限制最大返回量
        matched_products = []

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

            # 综合推荐分数 = 匹配分数(60%) + 类型加分(25%) + 报价次数(15%)
            recommendation_score = (
                max_score * 0.6 +
                type_bonus * 1.25 +
                min(stats["total_quote_count"] / 10, 1) * 0.15
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

    def recommend_suppliers_v2(
        self,
        product_name: str,
        spec: str = "",
        brand: str = "",
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """基于向量检索的供应商推荐（V2）

        使用 Qdrant 向量数据库进行语义匹配，支持：
        - 语义级匹配（"气缸" vs "气动执行器"）
        - 自动品牌关联
        - 毫秒级检索
        """
        from app.services.embedding_service import EmbeddingService, EmbeddingTextBuilder
        from app.services.qdrant_service import QdrantService

        logger.info("[推荐V2] 开始向量检索推荐")
        logger.info(f"[推荐V2] 产品名称: {product_name}, 规格: {spec}, 品牌: {brand}")

        embedding_service = EmbeddingService()
        qdrant_service = QdrantService()

        # 构建查询文本
        query_text = EmbeddingTextBuilder.build_query_text(
            product_name=product_name,
            spec=spec,
            brand=brand
        )

        if not query_text.strip():
            logger.warning("[推荐V2] 查询文本为空")
            return []

        # 生成查询向量
        query_embedding = embedding_service.get_embedding(query_text)
        if not query_embedding:
            logger.warning("[推荐V2] 无法生成查询向量，回退到V1算法")
            return self.recommend_suppliers(product_name, spec, brand, limit)

        # 向量检索
        search_results = qdrant_service.search_with_brand_filter(
            query_vector=query_embedding,
            brand=brand if brand else None,
            limit=50,
            score_threshold=0.3
        )

        if not search_results:
            logger.info("[推荐V2] 向量检索无结果，回退到V1算法")
            return self.recommend_suppliers(product_name, spec, brand, limit)

        logger.info(f"[推荐V2] 向量检索到 {len(search_results)} 条记录")

        # 获取 V2 结果
        v2_results = self._rerank_and_aggregate_v2(search_results, limit * 2)

        # 获取 V1 结果并融合
        v1_results = self.recommend_suppliers(product_name, spec, brand, limit * 2)

        # 融合结果：按 supplier_id 去重，V2 优先
        seen_ids = set()
        merged = []
        for r in v2_results:
            if r["supplier_id"] not in seen_ids:
                seen_ids.add(r["supplier_id"])
                merged.append(r)
        for r in v1_results:
            if r["supplier_id"] not in seen_ids:
                seen_ids.add(r["supplier_id"])
                # 转换 V1 格式以匹配 V2
                r["avg_similarity"] = r.get("avg_match_score", 0)
                r["max_similarity"] = r.get("recommendation_score", 0)
                merged.append(r)

        # 按推荐分数排序
        merged.sort(key=lambda x: x.get("recommendation_score", 0), reverse=True)
        return merged[:limit]

    def _rerank_and_aggregate_v2(
        self,
        vector_results: List[Dict],
        limit: int
    ) -> List[Dict[str, Any]]:
        """重排序并按供应商聚合（V2）"""
        # 按供应商聚合
        supplier_groups: Dict[int, Dict] = {}

        for result in vector_results:
            payload = result["payload"]
            sid = payload["supplier_id"]
            similarity = result["score"]

            if sid not in supplier_groups:
                supplier_groups[sid] = {
                    "supplier_id": sid,
                    "products": [],
                    "similarities": [],
                    "total_quotes": 0,
                    "brands": set()
                }

            group = supplier_groups[sid]
            group["products"].append({
                "name": payload.get("product_name", ""),
                "model": payload.get("product_model", ""),
                "brand": payload.get("brand", ""),
                "similarity": similarity
            })
            group["similarities"].append(similarity)
            group["total_quotes"] += payload.get("quote_count", 0)
            if payload.get("brand"):
                group["brands"].add(payload["brand"])

        # 获取供应商信息
        supplier_ids = list(supplier_groups.keys())
        suppliers = self.db.query(Supplier).filter(
            Supplier.id.in_(supplier_ids)
        ).all()
        supplier_map = {s.id: s for s in suppliers}

        # 构建结果
        results = []
        for sid, group in supplier_groups.items():
            supplier = supplier_map.get(sid)
            if not supplier:
                continue

            avg_similarity = sum(group["similarities"]) / len(group["similarities"])
            max_similarity = max(group["similarities"])

            # 综合分数：相似度(60%) + 报价次数(30%) + 时效性(10%)
            quote_factor = min(group["total_quotes"] / 10, 1.0)
            recency = self._calc_recency(supplier.last_quote_date)
            score = max_similarity * 0.6 + quote_factor * 0.3 + recency * 0.1

            results.append({
                "supplier_id": sid,
                "supplier_name": supplier.company_name,
                "company_name": supplier.company_name,
                "contact_name": supplier.contact_name,
                "contact_phone": supplier.contact_phone,
                "quote_count": group["total_quotes"],
                "brands": list(group["brands"]),
                "products": group["products"][:3],
                "avg_similarity": avg_similarity,
                "max_similarity": max_similarity,
                "recommendation_score": score,
                "last_quote_date": supplier.last_quote_date,
                "created_by": supplier.created_by
            })

        results.sort(key=lambda x: x["recommendation_score"], reverse=True)
        return results[:limit]

    def _calc_recency(self, last_date) -> float:
        """计算时效性分数（0-1）"""
        if not last_date:
            return 0.0
        normalized_last_date = ensure_utc(last_date)
        if normalized_last_date is None:
            return 0.0
        days_ago = (utc_now() - normalized_last_date).days
        if days_ago <= 7:
            return 1.0
        elif days_ago <= 30:
            return 0.8
        elif days_ago <= 90:
            return 0.5
        elif days_ago <= 180:
            return 0.3
        return 0.1
