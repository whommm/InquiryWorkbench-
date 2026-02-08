"""
Qdrant Service - 向量数据库服务
提供向量存储、检索、集合管理等功能
"""
import logging
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Distance, VectorParams, PointStruct
from app.core.config import settings

logger = logging.getLogger(__name__)


class QdrantService:
    """Qdrant 向量数据库服务"""

    def __init__(self):
        self.client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT
        )
        self.collection_name = settings.QDRANT_COLLECTION
        self.vector_size = settings.EMBEDDING_DIMENSIONS

    def ensure_collection(self) -> bool:
        """确保集合存在，不存在则创建"""
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)

            if not exists:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.vector_size,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"创建集合: {self.collection_name}")
            return True
        except Exception as e:
            logger.error(f"确保集合存在失败: {e}")
            return False

    def upsert_point(
        self,
        point_id: int,
        vector: List[float],
        payload: Dict[str, Any]
    ) -> bool:
        """插入或更新单个向量点"""
        try:
            self.client.upsert(
                collection_name=self.collection_name,
                points=[
                    PointStruct(
                        id=point_id,
                        vector=vector,
                        payload=payload
                    )
                ]
            )
            return True
        except Exception as e:
            logger.error(f"upsert 向量点失败: {e}")
            return False

    def upsert_points_batch(
        self,
        points: List[Dict[str, Any]]
    ) -> bool:
        """批量插入或更新向量点"""
        try:
            point_structs = [
                PointStruct(
                    id=p["id"],
                    vector=p["vector"],
                    payload=p["payload"]
                )
                for p in points
            ]
            self.client.upsert(
                collection_name=self.collection_name,
                points=point_structs
            )
            return True
        except Exception as e:
            logger.error(f"批量 upsert 失败: {e}")
            return False

    def search(
        self,
        query_vector: List[float],
        limit: int = 50,
        score_threshold: float = 0.3,
        filter_conditions: Optional[models.Filter] = None
    ) -> List[Dict[str, Any]]:
        """向量相似度搜索"""
        try:
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=limit,
                score_threshold=score_threshold,
                query_filter=filter_conditions
            )
            return [
                {
                    "id": hit.id,
                    "score": hit.score,
                    "payload": hit.payload
                }
                for hit in results
            ]
        except Exception as e:
            logger.error(f"向量搜索失败: {e}")
            return []

    def search_with_brand_filter(
        self,
        query_vector: List[float],
        brand: Optional[str] = None,
        limit: int = 50,
        score_threshold: float = 0.3
    ) -> List[Dict[str, Any]]:
        """带品牌过滤的向量搜索"""
        filter_conditions = None
        if brand:
            filter_conditions = models.Filter(
                must=[
                    models.FieldCondition(
                        key="brand",
                        match=models.MatchValue(value=brand.lower())
                    )
                ]
            )
        return self.search(
            query_vector=query_vector,
            limit=limit,
            score_threshold=score_threshold,
            filter_conditions=filter_conditions
        )

    def delete_point(self, point_id: int) -> bool:
        """删除单个向量点"""
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.PointIdsList(points=[point_id])
            )
            return True
        except Exception as e:
            logger.error(f"删除向量点失败: {e}")
            return False

    def get_collection_info(self) -> Optional[Dict[str, Any]]:
        """获取集合信息"""
        try:
            info = self.client.get_collection(self.collection_name)
            return {
                "name": self.collection_name,
                "vectors_count": info.vectors_count,
                "points_count": info.points_count,
                "status": info.status.value
            }
        except Exception as e:
            logger.error(f"获取集合信息失败: {e}")
            return None

    def delete_collection(self) -> bool:
        """删除集合（谨慎使用）"""
        try:
            self.client.delete_collection(self.collection_name)
            logger.info(f"删除集合: {self.collection_name}")
            return True
        except Exception as e:
            logger.error(f"删除集合失败: {e}")
            return False
