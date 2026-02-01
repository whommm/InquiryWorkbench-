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


settings = Settings()
