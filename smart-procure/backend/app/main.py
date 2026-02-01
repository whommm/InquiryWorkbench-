import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .api import routes
from .models.columns import HEADERS
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

@app.get("/api/init")
async def init_sheet():
    # Return headers and some empty rows
    # Row 1: Headers
    # Row 2, 3: Dummy items
    
    row1 = HEADERS
    
    # Dummy Item 1
    row2 = ["1", "西门子电机", "1KW", "10", "台", "西门子"] + [None] * (len(HEADERS) - 6)
    
    # Dummy Item 2
    row3 = ["2", "诺德减速机", "Ratio 10", "5", "台", "诺德"] + [None] * (len(HEADERS) - 6)
    
    return {"data": [row1, row2, row3]}

@app.get("/")
async def root():
    return {"message": "SmartProcure API Running"}
