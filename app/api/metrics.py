"""
Prometheus 指标 API

导出服务运行指标供 Prometheus 抓取。
"""

import logging
import time
from typing import Dict, Any

from fastapi import APIRouter, Response
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    Info,
    REGISTRY,
    generate_latest,
    CONTENT_TYPE_LATEST
)

from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# ========== 指标定义 ==========

# 应用信息
APP_INFO = Info(
    "zmc_alarm_exporter",
    "ZMC Alarm Exporter information"
)

# 同步计数器
SYNC_TOTAL = Counter(
    "zmc_sync_total",
    "Total number of sync operations",
    ["operation", "status"]
)

# 告警计数器
ALARMS_PROCESSED = Counter(
    "zmc_alarms_processed_total",
    "Total number of alarms processed",
    ["action"]  # new, resolved, silenced, heartbeat
)

# 当前活跃告警数
ACTIVE_ALARMS = Gauge(
    "zmc_active_alarms",
    "Number of currently active alarms in sync"
)

# 同步延迟直方图
SYNC_DURATION = Histogram(
    "zmc_sync_duration_seconds",
    "Time spent in sync operations",
    ["operation"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0]
)

# 数据库查询延迟
DB_QUERY_DURATION = Histogram(
    "zmc_db_query_duration_seconds",
    "Time spent in database queries",
    ["query_type"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

# Alertmanager 请求延迟
AM_REQUEST_DURATION = Histogram(
    "zmc_alertmanager_request_duration_seconds",
    "Time spent in Alertmanager API requests",
    ["method", "endpoint"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# 错误计数器
ERRORS_TOTAL = Counter(
    "zmc_errors_total",
    "Total number of errors",
    ["component", "error_type"]
)

# 上次同步时间
LAST_SYNC_TIMESTAMP = Gauge(
    "zmc_last_sync_timestamp_seconds",
    "Unix timestamp of the last successful sync"
)

# 同步服务状态
SYNC_SERVICE_UP = Gauge(
    "zmc_sync_service_up",
    "Whether the sync service is running (1 = running, 0 = stopped)"
)

# 数据库连接池状态
DB_POOL_CONNECTIONS = Gauge(
    "zmc_db_pool_connections",
    "Number of database pool connections",
    ["state"]  # active, idle
)


def init_metrics():
    """初始化指标"""
    APP_INFO.info({
        "version": settings.app_version,
        "alertmanager_url": settings.alertmanager.url,
        "sync_interval": str(settings.sync.scan_interval),
        "alarm_levels": settings.sync.alarm_levels
    })


# 初始化
init_metrics()


# ========== 指标端点 ==========

@router.get("/metrics")
async def prometheus_metrics():
    """
    Prometheus 指标端点

    返回所有指标供 Prometheus 抓取。
    """
    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST
    )


@router.get("/metrics/json")
async def metrics_json() -> Dict[str, Any]:
    """
    JSON 格式指标

    返回关键指标的 JSON 表示，便于调试。
    """
    from app.services.sync_service import sync_service

    return {
        "app": {
            "name": settings.app_name,
            "version": settings.app_version
        },
        "sync_service": {
            "running": sync_service._running,
            "interval_seconds": settings.sync.scan_interval
        },
        "config": {
            "alertmanager_url": settings.alertmanager.url,
            "alarm_levels": settings.sync.alarm_levels,
            "severity_filter": settings.sync.severity_filter or "none",
            "batch_size": settings.sync.batch_size
        }
    }


# ========== 指标辅助函数 ==========

class MetricsHelper:
    """指标辅助类，供其他模块使用"""

    @staticmethod
    def record_sync_operation(operation: str, success: bool, duration_seconds: float):
        """记录同步操作"""
        status = "success" if success else "failure"
        SYNC_TOTAL.labels(operation=operation, status=status).inc()
        SYNC_DURATION.labels(operation=operation).observe(duration_seconds)
        if success:
            LAST_SYNC_TIMESTAMP.set(time.time())

    @staticmethod
    def record_alarm_processed(action: str, count: int = 1):
        """记录告警处理"""
        ALARMS_PROCESSED.labels(action=action).inc(count)

    @staticmethod
    def set_active_alarms(count: int):
        """设置活跃告警数"""
        ACTIVE_ALARMS.set(count)

    @staticmethod
    def record_db_query(query_type: str, duration_seconds: float):
        """记录数据库查询"""
        DB_QUERY_DURATION.labels(query_type=query_type).observe(duration_seconds)

    @staticmethod
    def record_am_request(method: str, endpoint: str, duration_seconds: float):
        """记录 Alertmanager 请求"""
        AM_REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration_seconds)

    @staticmethod
    def record_error(component: str, error_type: str):
        """记录错误"""
        ERRORS_TOTAL.labels(component=component, error_type=error_type).inc()

    @staticmethod
    def set_sync_service_status(running: bool):
        """设置同步服务状态"""
        SYNC_SERVICE_UP.set(1 if running else 0)

    @staticmethod
    def set_db_pool_status(active: int, idle: int):
        """设置数据库连接池状态"""
        DB_POOL_CONNECTIONS.labels(state="active").set(active)
        DB_POOL_CONNECTIONS.labels(state="idle").set(idle)


# 全局辅助实例
metrics_helper = MetricsHelper()
