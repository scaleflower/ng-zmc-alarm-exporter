"""
健康检查 API

提供服务健康状态检查端点。
"""

import logging
from enum import Enum
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app.config import settings
from app.services.oracle_client import oracle_client
from app.services.alertmanager_client import alertmanager_client
from app.services.sync_service import sync_service

logger = logging.getLogger(__name__)
router = APIRouter()


class HealthStatus(str, Enum):
    """健康状态枚举"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ComponentHealth(BaseModel):
    """组件健康状态"""
    status: HealthStatus
    message: Optional[str] = None
    latency_ms: Optional[int] = None


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: HealthStatus
    timestamp: datetime
    version: str
    components: Dict[str, ComponentHealth]


@router.get("/health", response_model=HealthResponse)
async def health_check(response: Response) -> HealthResponse:
    """
    完整健康检查

    检查所有依赖组件的状态：
    - Oracle 数据库连接
    - Alertmanager 连接
    - 同步服务状态
    """
    components: Dict[str, ComponentHealth] = {}
    overall_status = HealthStatus.HEALTHY

    # 1. 检查 Oracle 数据库
    try:
        db_healthy = oracle_client.health_check()
        if db_healthy:
            components["oracle"] = ComponentHealth(
                status=HealthStatus.HEALTHY,
                message="Connected"
            )
        else:
            components["oracle"] = ComponentHealth(
                status=HealthStatus.UNHEALTHY,
                message="Connection failed"
            )
            overall_status = HealthStatus.UNHEALTHY
    except Exception as e:
        components["oracle"] = ComponentHealth(
            status=HealthStatus.UNHEALTHY,
            message=str(e)
        )
        overall_status = HealthStatus.UNHEALTHY

    # 2. 检查 Alertmanager
    try:
        am_healthy = await alertmanager_client.health_check()
        if am_healthy:
            components["alertmanager"] = ComponentHealth(
                status=HealthStatus.HEALTHY,
                message="Connected"
            )
        else:
            components["alertmanager"] = ComponentHealth(
                status=HealthStatus.DEGRADED,
                message="Alertmanager unreachable"
            )
            if overall_status == HealthStatus.HEALTHY:
                overall_status = HealthStatus.DEGRADED
    except Exception as e:
        components["alertmanager"] = ComponentHealth(
            status=HealthStatus.DEGRADED,
            message=str(e)
        )
        if overall_status == HealthStatus.HEALTHY:
            overall_status = HealthStatus.DEGRADED

    # 3. 检查同步服务
    if sync_service._running:
        components["sync_service"] = ComponentHealth(
            status=HealthStatus.HEALTHY,
            message="Running"
        )
    else:
        if settings.sync.enabled:
            components["sync_service"] = ComponentHealth(
                status=HealthStatus.UNHEALTHY,
                message="Not running"
            )
            overall_status = HealthStatus.UNHEALTHY
        else:
            components["sync_service"] = ComponentHealth(
                status=HealthStatus.DEGRADED,
                message="Disabled"
            )

    # 设置响应状态码
    if overall_status == HealthStatus.UNHEALTHY:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif overall_status == HealthStatus.DEGRADED:
        response.status_code = status.HTTP_200_OK

    return HealthResponse(
        status=overall_status,
        timestamp=datetime.now(timezone.utc),
        version=settings.app_version,
        components=components
    )


@router.get("/health/live")
async def liveness_probe() -> Dict[str, Any]:
    """
    存活探针 (Kubernetes liveness probe)

    仅检查应用是否运行，不检查依赖。
    """
    return {
        "status": "alive",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.get("/health/ready")
async def readiness_probe(response: Response) -> Dict[str, Any]:
    """
    就绪探针 (Kubernetes readiness probe)

    检查应用是否准备好接收流量。
    """
    ready = True
    checks = {}

    # 检查数据库连接
    try:
        db_ready = oracle_client.health_check()
        checks["oracle"] = "ok" if db_ready else "not ready"
        if not db_ready:
            ready = False
    except Exception as e:
        checks["oracle"] = str(e)
        ready = False

    # 检查同步服务
    if settings.sync.enabled:
        if sync_service._running:
            checks["sync_service"] = "ok"
        else:
            checks["sync_service"] = "not running"
            ready = False
    else:
        checks["sync_service"] = "disabled"

    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "ready": ready,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks
    }
