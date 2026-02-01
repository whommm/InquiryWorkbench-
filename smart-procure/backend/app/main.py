import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .api import routes
from .auth import auth_router
from .models.columns import HEADERS
from .models.database import init_db
from .core.config import setup_logging

# 初始化日志配置
setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="SmartProcure Backend")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理"""
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误，请稍后重试"}
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes.router, prefix="/api")
app.include_router(auth_router)


@app.on_event("startup")
async def startup_event():
    """应用启动时初始化数据库"""
    logger.info("正在初始化数据库...")
    init_db()
    logger.info("数据库初始化完成")


@app.get("/api/init")
async def init_sheet():
    """返回空表格，只有表头"""
    return {"data": [HEADERS]}

@app.get("/")
async def root():
    return {"message": "SmartProcure API Running"}
