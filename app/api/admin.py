"""
管理 API

提供配置管理和运维操作端点。
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel

from app.config import settings
from app.services.sync_service import sync_service
from app.services.alertmanager_client import alertmanager_client
from app.services.oracle_client import oracle_client

logger = logging.getLogger(__name__)
router = APIRouter()


# ========== 响应模型 ==========

class ConfigItem(BaseModel):
    """配置项"""
    config_key: str
    config_value: str
    config_group: str
    description: Optional[str] = None


class AlertmanagerInfo(BaseModel):
    """Alertmanager 信息"""
    url: str
    healthy: bool
    version: Optional[str] = None
    cluster_status: Optional[str] = None
    active_alerts: int = 0
    active_silences: int = 0


class ServiceControl(BaseModel):
    """服务控制"""
    action: str  # start, stop, restart


# ========== API 端点 ==========

@router.get("/config", response_model=List[ConfigItem])
async def get_config(
    group: Optional[str] = None
) -> List[ConfigItem]:
    """
    获取配置列表

    从数据库配置表读取配置项。
    """
    try:
        query = """
            SELECT CONFIG_KEY, CONFIG_VALUE, CONFIG_GROUP, DESCRIPTION
            FROM NM_ALARM_SYNC_CONFIG
            WHERE IS_ACTIVE = 1
        """
        params = {}

        if group:
            query += " AND CONFIG_GROUP = :group"
            params["group"] = group.upper()

        query += " ORDER BY CONFIG_GROUP, CONFIG_KEY"

        rows = oracle_client.execute_query(query, params)

        return [
            ConfigItem(
                config_key=row["CONFIG_KEY"],
                config_value=row["CONFIG_VALUE"],
                config_group=row["CONFIG_GROUP"],
                description=row.get("DESCRIPTION")
            )
            for row in rows
        ]

    except Exception as e:
        logger.error(f"Failed to get config: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Database query failed: {str(e)}"
        )


@router.put("/config/{config_key}")
async def update_config(
    config_key: str,
    config_value: str = Body(..., embed=True)
) -> Dict[str, Any]:
    """
    更新配置项

    修改数据库配置表中的配置值。
    """
    try:
        # 检查配置项是否存在
        check_query = """
            SELECT CONFIG_ID FROM NM_ALARM_SYNC_CONFIG
            WHERE CONFIG_KEY = :key AND IS_ACTIVE = 1
        """
        result = oracle_client.execute_query(check_query, {"key": config_key})

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Config key not found: {config_key}"
            )

        # 更新配置
        update_query = """
            UPDATE NM_ALARM_SYNC_CONFIG
            SET CONFIG_VALUE = :value, UPDATE_TIME = SYSDATE
            WHERE CONFIG_KEY = :key AND IS_ACTIVE = 1
        """
        oracle_client.execute_update(
            update_query,
            {"key": config_key, "value": config_value}
        )

        logger.info(f"Config updated: {config_key} = {config_value}")

        return {
            "success": True,
            "config_key": config_key,
            "config_value": config_value,
            "message": "Configuration updated. Restart may be required for some settings."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update config: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Update failed: {str(e)}"
        )


@router.get("/alertmanager/status", response_model=AlertmanagerInfo)
async def get_alertmanager_status() -> AlertmanagerInfo:
    """
    获取 Alertmanager 状态信息
    """
    try:
        healthy = await alertmanager_client.health_check()

        info = AlertmanagerInfo(
            url=settings.alertmanager.url,
            healthy=healthy
        )

        if healthy:
            # 获取详细状态
            status = await alertmanager_client.get_status()
            if status:
                info.version = status.get("versionInfo", {}).get("version")
                info.cluster_status = status.get("cluster", {}).get("status")

            # 获取活跃告警数
            alerts = await alertmanager_client.get_alerts()
            info.active_alerts = len(alerts)

            # 获取活跃静默数
            silences = await alertmanager_client.get_silences()
            active_silences = [s for s in silences if s.get("status", {}).get("state") == "active"]
            info.active_silences = len(active_silences)

        return info

    except Exception as e:
        logger.error(f"Failed to get Alertmanager status: {e}")
        return AlertmanagerInfo(
            url=settings.alertmanager.url,
            healthy=False
        )


@router.get("/alertmanager/alerts")
async def get_alertmanager_alerts() -> List[Dict[str, Any]]:
    """
    获取 Alertmanager 中的活跃告警
    """
    try:
        alerts = await alertmanager_client.get_alerts()
        return alerts
    except Exception as e:
        logger.error(f"Failed to get Alertmanager alerts: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get alerts: {str(e)}"
        )


@router.get("/alertmanager/silences")
async def get_alertmanager_silences() -> List[Dict[str, Any]]:
    """
    获取 Alertmanager 中的静默规则
    """
    try:
        silences = await alertmanager_client.get_silences()
        return silences
    except Exception as e:
        logger.error(f"Failed to get Alertmanager silences: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get silences: {str(e)}"
        )


@router.delete("/alertmanager/silences/{silence_id}")
async def delete_alertmanager_silence(silence_id: str) -> Dict[str, Any]:
    """
    删除 Alertmanager 静默规则
    """
    try:
        result = await alertmanager_client.delete_silence(silence_id)

        if result["success"]:
            return {
                "success": True,
                "silence_id": silence_id,
                "message": "Silence deleted"
            }
        else:
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "Delete failed")
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete silence: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Delete failed: {str(e)}"
        )


@router.post("/service/control")
async def control_service(control: ServiceControl) -> Dict[str, Any]:
    """
    控制同步服务

    支持的操作：start, stop, restart
    """
    action = control.action.lower()

    if action == "start":
        if sync_service._running:
            return {
                "success": False,
                "message": "Service is already running"
            }
        await sync_service.start_background_sync()
        return {
            "success": True,
            "action": "start",
            "message": "Sync service started"
        }

    elif action == "stop":
        if not sync_service._running:
            return {
                "success": False,
                "message": "Service is not running"
            }
        await sync_service.stop_background_sync()
        return {
            "success": True,
            "action": "stop",
            "message": "Sync service stopped"
        }

    elif action == "restart":
        if sync_service._running:
            await sync_service.stop_background_sync()
        await sync_service.start_background_sync()
        return {
            "success": True,
            "action": "restart",
            "message": "Sync service restarted"
        }

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown action: {action}. Supported: start, stop, restart"
        )


@router.post("/cleanup/old-logs")
async def cleanup_old_logs(
    days: int = 30
) -> Dict[str, Any]:
    """
    清理旧日志

    删除指定天数之前的同步日志记录。
    """
    if days < 1:
        raise HTTPException(
            status_code=400,
            detail="Days must be at least 1"
        )

    try:
        delete_query = """
            DELETE FROM NM_ALARM_SYNC_LOG
            WHERE CREATE_TIME < SYSDATE - :days
        """
        oracle_client.execute_update(delete_query, {"days": days})

        logger.info(f"Cleaned up sync logs older than {days} days")

        return {
            "success": True,
            "days": days,
            "message": f"Logs older than {days} days have been deleted"
        }

    except Exception as e:
        logger.error(f"Failed to cleanup logs: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Cleanup failed: {str(e)}"
        )


@router.post("/cleanup/resolved-alarms")
async def cleanup_resolved_alarms(
    days: int = 7
) -> Dict[str, Any]:
    """
    清理已解决告警

    删除指定天数之前的已解决告警同步状态。
    """
    if days < 1:
        raise HTTPException(
            status_code=400,
            detail="Days must be at least 1"
        )

    try:
        delete_query = """
            DELETE FROM NM_ALARM_SYNC_STATUS
            WHERE SYNC_STATUS = 'RESOLVED'
            AND LAST_PUSH_TIME < SYSDATE - :days
        """
        oracle_client.execute_update(delete_query, {"days": days})

        logger.info(f"Cleaned up resolved alarms older than {days} days")

        return {
            "success": True,
            "days": days,
            "message": f"Resolved alarms older than {days} days have been deleted"
        }

    except Exception as e:
        logger.error(f"Failed to cleanup resolved alarms: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Cleanup failed: {str(e)}"
        )


@router.get("/database/status")
async def get_database_status() -> Dict[str, Any]:
    """
    获取数据库连接状态
    """
    try:
        healthy = oracle_client.health_check()

        # 获取连接池信息（如果有）
        pool_info = {}
        if oracle_client._pool:
            pool_info = {
                "min": oracle_client._pool.min,
                "max": oracle_client._pool.max,
                "busy": oracle_client._pool.busy,
                "opened": oracle_client._pool.opened,
            }

        return {
            "healthy": healthy,
            "dsn": settings.oracle.dsn,
            "pool": pool_info
        }

    except Exception as e:
        logger.error(f"Failed to get database status: {e}")
        return {
            "healthy": False,
            "dsn": settings.oracle.dsn,
            "error": str(e)
        }


@router.get("/statistics/alarms")
async def get_alarm_statistics() -> Dict[str, Any]:
    """
    获取 ZMC 告警统计信息

    统计未关闭告警的数量，按级别分组显示。
    """
    try:
        # 告警级别名称映射
        level_names = {
            "1": {"en": "Critical", "cn": "严重", "prometheus": "critical"},
            "2": {"en": "Error", "cn": "重要", "prometheus": "error"},
            "3": {"en": "Warning", "cn": "次要", "prometheus": "warning"},
            "4": {"en": "Info", "cn": "警告", "prometheus": "info"},
            "0": {"en": "Undefined", "cn": "未定义", "prometheus": "warning"},
        }

        # 查询未关闭告警统计 (ALARM_STATE = 'U')
        alarm_query = """
            SELECT
                TO_CHAR(ALARM_LEVEL) as ALARM_LEVEL,
                COUNT(*) as CNT
            FROM NM_ALARM_CDR
            WHERE ALARM_STATE = 'U'
            GROUP BY ALARM_LEVEL
            ORDER BY ALARM_LEVEL
        """
        alarm_rows = oracle_client.execute_query(alarm_query)

        # 构建告警统计
        by_level = []
        total_active = 0
        for row in alarm_rows:
            level = str(row["ALARM_LEVEL"])
            count = row["CNT"]
            total_active += count

            level_info = level_names.get(level, {"en": "Unknown", "cn": "未知", "prometheus": "unknown"})
            by_level.append({
                "level": level,
                "level_name": f"{level_info['en']} ({level_info['cn']})",
                "prometheus_severity": level_info["prometheus"],
                "count": count
            })

        # 查询同步状态统计
        sync_query = """
            SELECT
                SYNC_STATUS,
                COUNT(*) as CNT
            FROM NM_ALARM_SYNC_STATUS
            GROUP BY SYNC_STATUS
        """
        sync_rows = oracle_client.execute_query(sync_query)

        sync_status = {}
        for row in sync_rows:
            sync_status[row["SYNC_STATUS"]] = row["CNT"]

        # 查询最近同步时间
        last_sync_query = """
            SELECT MAX(LAST_PUSH_TIME) as LAST_PUSH
            FROM NM_ALARM_SYNC_STATUS
        """
        last_sync_rows = oracle_client.execute_query(last_sync_query)
        last_push_time = None
        if last_sync_rows and last_sync_rows[0]["LAST_PUSH"]:
            last_push_time = str(last_sync_rows[0]["LAST_PUSH"])

        return {
            "active_alarms": {
                "total": total_active,
                "by_level": by_level
            },
            "sync_status": {
                "firing": sync_status.get("FIRING", 0),
                "resolved": sync_status.get("RESOLVED", 0),
                "silenced": sync_status.get("SILENCED", 0),
                "total": sum(sync_status.values())
            },
            "last_push_time": last_push_time,
            "config": {
                "sync_alarm_levels": settings.sync.alarm_levels,
                "severity_filter": settings.sync.severity_filter or "(all)",
                "scan_interval": settings.sync.scan_interval
            }
        }

    except Exception as e:
        logger.error(f"Failed to get alarm statistics: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get statistics: {str(e)}"
        )
