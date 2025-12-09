"""
ZMC Alarm Exporter - FastAPI 应用

将 ZMC 告警同步到 Prometheus Alertmanager。
"""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api import health, metrics, sync, admin
from app.services.sync_service import sync_service


def setup_logging():
    """配置日志"""
    log_format = (
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        if settings.logging.format == "text"
        else '{"time": "%(asctime)s", "name": "%(name)s", "level": "%(levelname)s", "message": "%(message)s"}'
    )

    logging.basicConfig(
        level=getattr(logging, settings.logging.level.upper()),
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

    # 降低第三方库日志级别
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理

    - 启动时初始化同步服务
    - 关闭时清理资源
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")

    # 启动后台同步服务
    if settings.sync.enabled:
        await sync_service.start_background_sync()
        logger.info("Background sync service started")
    else:
        logger.warning("Sync service is disabled")

    yield

    # 停止后台同步服务
    logger.info("Shutting down...")
    await sync_service.stop_background_sync()
    logger.info("Shutdown complete")


# 初始化日志
setup_logging()

# 创建 FastAPI 应用
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="ZMC Alarm Exporter - 将 ZMC 告警同步到 Prometheus Alertmanager",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan
)

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(health.router, tags=["Health"])
app.include_router(metrics.router, tags=["Metrics"])
app.include_router(sync.router, prefix="/api/v1", tags=["Sync"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin"])


@app.get("/")
async def root():
    """根路径 - 返回基本信息"""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running"
    }
