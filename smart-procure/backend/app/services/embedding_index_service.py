"""
Embedding Index Service - 向量索引管理服务
提供产品索引、批量索引、增量同步等功能
"""
import logging
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from app.models.database import SupplierProduct
from app.services.embedding_service import EmbeddingService, EmbeddingTextBuilder
from app.services.qdrant_service import QdrantService

logger = logging.getLogger(__name__)


class EmbeddingIndexService:
    """向量索引管理服务"""

    def __init__(self, db: Session):
        self.db = db
        self.embedding_service = EmbeddingService()
        self.qdrant_service = QdrantService()

    def index_product(self, product: SupplierProduct) -> bool:
        """为单个产品创建向量索引"""
        # 构建 embedding 文本
        text = EmbeddingTextBuilder.build_product_text(
            brand=product.brand or "",
            product_name=product.product_name or "",
            product_model=product.product_model or ""
        )

        if not text.strip():
            logger.warning(f"产品 {product.id} 文本为空，跳过索引")
            return False

        # 生成 embedding
        embedding = self.embedding_service.get_embedding(text)
        if not embedding:
            logger.error(f"产品 {product.id} embedding 生成失败")
            return False

        # 存入 Qdrant
        payload = {
            "supplier_product_id": product.id,
            "supplier_id": product.supplier_id,
            "product_name": product.product_name or "",
            "product_model": product.product_model or "",
            "brand": (product.brand or "").lower(),
            "embedding_text": text,
            "quote_count": product.quote_count or 0
        }

        return self.qdrant_service.upsert_point(
            point_id=product.id,
            vector=embedding,
            payload=payload
        )

    def index_products_batch(
        self,
        products: List[SupplierProduct],
        batch_size: int = 50
    ) -> Dict[str, int]:
        """批量索引产品"""
        stats = {"total": len(products), "success": 0, "failed": 0}

        # 构建文本列表
        texts = []
        for product in products:
            text = EmbeddingTextBuilder.build_product_text(
                brand=product.brand or "",
                product_name=product.product_name or "",
                product_model=product.product_model or ""
            )
            texts.append(text)

        # 批量生成 embeddings
        embeddings = self.embedding_service.get_embeddings_batch(texts, batch_size)

        # 构建点列表并批量插入
        points = []
        for i, (product, embedding) in enumerate(zip(products, embeddings)):
            if embedding is None:
                stats["failed"] += 1
                continue

            points.append({
                "id": product.id,
                "vector": embedding,
                "payload": {
                    "supplier_product_id": product.id,
                    "supplier_id": product.supplier_id,
                    "product_name": product.product_name or "",
                    "product_model": product.product_model or "",
                    "brand": (product.brand or "").lower(),
                    "embedding_text": texts[i],
                    "quote_count": product.quote_count or 0
                }
            })

            # 分批插入
            if len(points) >= batch_size:
                if self.qdrant_service.upsert_points_batch(points):
                    stats["success"] += len(points)
                else:
                    stats["failed"] += len(points)
                points = []

        # 处理剩余的点
        if points:
            if self.qdrant_service.upsert_points_batch(points):
                stats["success"] += len(points)
            else:
                stats["failed"] += len(points)

        return stats

    def rebuild_all_indexes(self, batch_size: int = 50) -> Dict[str, int]:
        """全量重建索引"""
        # 确保集合存在
        self.qdrant_service.ensure_collection()

        stats = {"total": 0, "success": 0, "failed": 0}
        offset = 0

        while True:
            products = self.db.query(SupplierProduct).offset(offset).limit(batch_size).all()
            if not products:
                break

            batch_stats = self.index_products_batch(products, batch_size)
            stats["total"] += batch_stats["total"]
            stats["success"] += batch_stats["success"]
            stats["failed"] += batch_stats["failed"]

            offset += batch_size
            logger.info(f"已处理 {offset} 条记录")

        return stats

    def get_index_stats(self) -> Optional[Dict[str, Any]]:
        """获取索引统计信息"""
        # 数据库中的产品数量
        db_count = self.db.query(SupplierProduct).count()

        # Qdrant 中的向量数量
        qdrant_info = self.qdrant_service.get_collection_info()

        return {
            "db_product_count": db_count,
            "qdrant_info": qdrant_info
        }
