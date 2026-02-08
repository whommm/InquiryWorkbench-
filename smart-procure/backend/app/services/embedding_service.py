"""
Embedding Service - 向量嵌入生成服务
通过 OpenRouter 调用 Gemini Embedding 模型
"""
import logging
import requests
from typing import List, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """向量嵌入服务（OpenRouter 渠道）"""

    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.base_url = "https://openrouter.ai/api/v1/embeddings"
        self.model = settings.EMBEDDING_MODEL
        self.dimensions = settings.EMBEDDING_DIMENSIONS

    def get_embedding(self, text: str) -> Optional[List[float]]:
        """获取单个文本的 embedding"""
        if not text or not text.strip():
            return None

        if not self.api_key:
            logger.error("OPENROUTER_API_KEY 未配置")
            return None

        try:
            response = requests.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "input": text.strip()
                },
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]
        except Exception as e:
            logger.error(f"生成 embedding 失败: {e}")
            return None

    def get_embeddings_batch(
        self,
        texts: List[str],
        batch_size: int = 50
    ) -> List[Optional[List[float]]]:
        """批量获取 embeddings"""
        if not self.api_key:
            logger.error("OPENROUTER_API_KEY 未配置")
            return [None] * len(texts)

        results = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            valid_texts = [t.strip() if t else "" for t in batch]

            try:
                response = requests.post(
                    self.base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "input": valid_texts
                    },
                    timeout=60
                )
                response.raise_for_status()
                data = response.json()
                for item in data["data"]:
                    results.append(item["embedding"])
            except Exception as e:
                logger.error(f"批量生成 embedding 失败: {e}")
                results.extend([None] * len(batch))

        return results


class EmbeddingTextBuilder:
    """构建用于 embedding 的文本"""

    @staticmethod
    def build_product_text(
        brand: str = "",
        product_name: str = "",
        product_model: str = ""
    ) -> str:
        """
        构建产品 embedding 文本
        策略：品牌 + 产品名称 + 型号
        示例："SMC 气缸 CDQ2B20-10D"
        """
        parts = []
        if brand and brand.strip():
            parts.append(brand.strip())
        if product_name and product_name.strip():
            parts.append(product_name.strip())
        if product_model and product_model.strip():
            parts.append(product_model.strip())
        return " ".join(parts)

    @staticmethod
    def build_query_text(
        product_name: str = "",
        spec: str = "",
        brand: str = ""
    ) -> str:
        """
        构建查询 embedding 文本
        策略：与产品文本保持一致的结构
        """
        parts = []
        if brand and brand.strip():
            parts.append(brand.strip())
        if product_name and product_name.strip():
            parts.append(product_name.strip())
        if spec and spec.strip():
            parts.append(spec.strip())
        return " ".join(parts)
