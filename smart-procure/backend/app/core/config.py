import os
import logging
from dotenv import load_dotenv

load_dotenv()


def setup_logging():
    """配置统一的日志格式"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    # 降低第三方库的日志级别
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


class Settings:
    API_KEY = os.getenv("API_KEY")
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"

    # Qdrant 向量数据库配置
    QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
    QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
    QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "supplier_products")

    # OpenRouter API 配置（用于 Embedding）
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "google/gemini-embedding-001")
    EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "3072"))


settings = Settings()
