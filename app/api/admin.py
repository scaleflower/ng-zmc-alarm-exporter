"""
管理 API

提供配置管理和运维操作端点。
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.config import settings
from app.services.sync_service import sync_service
from app.services.alertmanager_client import alertmanager_client
from app.services.oracle_client import oracle_client

logger = logging.getLogger(__name__)
router = APIRouter()


# ========== Admin 首页 ==========

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def admin_index() -> str:
    """
    Admin API 首页

    展示所有可用的管理接口和链接（HTML 页面）。
    """
    base_url = "/api/v1/admin"

    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>ZMC Alarm Exporter - Admin</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                min-height: 100vh;
                color: #e0e0e0;
                padding: 20px;
            }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            h1 {{
                text-align: center;
                color: #00d4ff;
                margin-bottom: 10px;
                font-size: 2em;
            }}
            .subtitle {{
                text-align: center;
                color: #888;
                margin-bottom: 30px;
            }}
            .section {{
                background: rgba(255,255,255,0.05);
                border-radius: 12px;
                padding: 20px;
                margin-bottom: 20px;
                border: 1px solid rgba(255,255,255,0.1);
            }}
            .section h2 {{
                color: #00d4ff;
                margin-bottom: 15px;
                font-size: 1.2em;
                border-bottom: 1px solid rgba(255,255,255,0.1);
                padding-bottom: 10px;
            }}
            .api-list {{ list-style: none; }}
            .api-item {{
                display: flex;
                align-items: center;
                padding: 12px 15px;
                margin: 8px 0;
                background: rgba(255,255,255,0.03);
                border-radius: 8px;
                transition: all 0.2s;
            }}
            .api-item:hover {{
                background: rgba(0,212,255,0.1);
                transform: translateX(5px);
            }}
            .method {{
                display: inline-block;
                padding: 4px 10px;
                border-radius: 4px;
                font-size: 0.75em;
                font-weight: bold;
                margin-right: 15px;
                min-width: 60px;
                text-align: center;
            }}
            .method-get {{ background: #28a745; color: white; }}
            .method-post {{ background: #ffc107; color: #333; }}
            .method-put {{ background: #17a2b8; color: white; }}
            .method-delete {{ background: #dc3545; color: white; }}
            .api-info {{ flex: 1; }}
            .api-name {{
                font-weight: 600;
                color: #fff;
                margin-bottom: 4px;
            }}
            .api-desc {{ font-size: 0.85em; color: #888; }}
            .api-link {{
                color: #00d4ff;
                text-decoration: none;
                font-size: 0.85em;
                padding: 6px 12px;
                border: 1px solid #00d4ff;
                border-radius: 4px;
                transition: all 0.2s;
            }}
            .api-link:hover {{
                background: #00d4ff;
                color: #1a1a2e;
            }}
            .api-link.disabled {{
                color: #666;
                border-color: #666;
                cursor: not-allowed;
            }}
            .quick-links {{
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                justify-content: center;
                margin-bottom: 30px;
            }}
            .quick-link {{
                background: linear-gradient(135deg, #00d4ff 0%, #0099cc 100%);
                color: #1a1a2e;
                padding: 10px 20px;
                border-radius: 25px;
                text-decoration: none;
                font-weight: 600;
                transition: all 0.2s;
            }}
            .quick-link:hover {{
                transform: scale(1.05);
                box-shadow: 0 4px 15px rgba(0,212,255,0.4);
            }}
            .footer {{
                text-align: center;
                margin-top: 30px;
                color: #666;
                font-size: 0.85em;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔧 ZMC Alarm Exporter</h1>
            <p class="subtitle">Admin API Dashboard</p>

            <div class="quick-links">
                <a href="{base_url}/statistics/alarms" class="quick-link">📊 告警统计</a>
                <a href="{base_url}/database/status" class="quick-link">🗄️ 数据库状态</a>
                <a href="{base_url}/alertmanager/status" class="quick-link">🔔 Alertmanager</a>
                <a href="{base_url}/alertmanager/alerts" class="quick-link">⚠️ 活跃告警</a>
                <a href="/health" class="quick-link">💚 健康检查</a>
            </div>

            <div class="section">
                <h2>📊 统计信息</h2>
                <ul class="api-list">
                    <li class="api-item">
                        <span class="method method-get">GET</span>
                        <div class="api-info">
                            <div class="api-name">告警统计</div>
                            <div class="api-desc">查看 ZMC 未关闭告警数量（按级别分组）和同步状态</div>
                        </div>
                        <a href="{base_url}/statistics/alarms" class="api-link">调用</a>
                    </li>
                </ul>
            </div>

            <div class="section">
                <h2>📡 状态监控</h2>
                <ul class="api-list">
                    <li class="api-item">
                        <span class="method method-get">GET</span>
                        <div class="api-info">
                            <div class="api-name">数据库状态</div>
                            <div class="api-desc">查看 Oracle 数据库连接状态和连接池信息</div>
                        </div>
                        <a href="{base_url}/database/status" class="api-link">调用</a>
                    </li>
                    <li class="api-item">
                        <span class="method method-get">GET</span>
                        <div class="api-info">
                            <div class="api-name">Alertmanager 状态</div>
                            <div class="api-desc">查看 Alertmanager 健康状态、版本和集群信息</div>
                        </div>
                        <a href="{base_url}/alertmanager/status" class="api-link">调用</a>
                    </li>
                    <li class="api-item">
                        <span class="method method-get">GET</span>
                        <div class="api-info">
                            <div class="api-name">Alertmanager 活跃告警</div>
                            <div class="api-desc">查看 Alertmanager 中的所有活跃告警</div>
                        </div>
                        <a href="{base_url}/alertmanager/alerts" class="api-link">调用</a>
                    </li>
                    <li class="api-item">
                        <span class="method method-get">GET</span>
                        <div class="api-info">
                            <div class="api-name">Alertmanager 静默规则</div>
                            <div class="api-desc">查看 Alertmanager 中的所有静默规则</div>
                        </div>
                        <a href="{base_url}/alertmanager/silences" class="api-link">调用</a>
                    </li>
                </ul>
            </div>

            <div class="section">
                <h2>⚙️ 配置管理</h2>
                <ul class="api-list">
                    <li class="api-item">
                        <span class="method method-get">GET</span>
                        <div class="api-info">
                            <div class="api-name">获取配置列表</div>
                            <div class="api-desc">从数据库读取配置项（可选 ?group=xxx 过滤）</div>
                        </div>
                        <a href="{base_url}/config" class="api-link">调用</a>
                    </li>
                    <li class="api-item">
                        <span class="method method-put">PUT</span>
                        <div class="api-info">
                            <div class="api-name">更新配置项</div>
                            <div class="api-desc">PUT {base_url}/config/{{config_key}} - Body: {{"config_value": "新值"}}</div>
                        </div>
                        <span class="api-link disabled">需用工具调用</span>
                    </li>
                </ul>
            </div>

            <div class="section">
                <h2>🎮 服务控制</h2>
                <ul class="api-list">
                    <li class="api-item">
                        <span class="method method-post">POST</span>
                        <div class="api-info">
                            <div class="api-name">控制同步服务</div>
                            <div class="api-desc">POST {base_url}/service/control - Body: {{"action": "start|stop|restart"}}</div>
                        </div>
                        <span class="api-link disabled">需用工具调用</span>
                    </li>
                </ul>
            </div>

            <div class="section">
                <h2>🧹 数据清理</h2>
                <ul class="api-list">
                    <li class="api-item">
                        <span class="method method-post">POST</span>
                        <div class="api-info">
                            <div class="api-name">清理旧日志</div>
                            <div class="api-desc">POST {base_url}/cleanup/old-logs?days=30</div>
                        </div>
                        <span class="api-link disabled">需用工具调用</span>
                    </li>
                    <li class="api-item">
                        <span class="method method-post">POST</span>
                        <div class="api-info">
                            <div class="api-name">清理已解决告警</div>
                            <div class="api-desc">POST {base_url}/cleanup/resolved-alarms?days=7</div>
                        </div>
                        <span class="api-link disabled">需用工具调用</span>
                    </li>
                    <li class="api-item">
                        <span class="method method-delete">DELETE</span>
                        <div class="api-info">
                            <div class="api-name">删除静默规则</div>
                            <div class="api-desc">DELETE {base_url}/alertmanager/silences/{{silence_id}}</div>
                        </div>
                        <span class="api-link disabled">需用工具调用</span>
                    </li>
                </ul>
            </div>

            <div class="footer">
                ZMC Alarm Exporter v{settings.app_version} |
                <a href="/health" style="color: #00d4ff;">Health</a> |
                <a href="/metrics" style="color: #00d4ff;">Metrics</a>
            </div>
        </div>
    </body>
    </html>
    """

    return html_content


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
                config_key=row["config_key"],
                config_value=row["config_value"],
                config_group=row["config_group"],
                description=row.get("description")
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
            level = str(row["alarm_level"])
            count = row["cnt"]
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
            sync_status[row["sync_status"]] = row["cnt"]

        # 查询最近同步时间
        last_sync_query = """
            SELECT MAX(LAST_PUSH_TIME) as LAST_PUSH
            FROM NM_ALARM_SYNC_STATUS
        """
        last_sync_rows = oracle_client.execute_query(last_sync_query)
        last_push_time = None
        if last_sync_rows and last_sync_rows[0]["last_push"]:
            last_push_time = str(last_sync_rows[0]["last_push"])

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
