"""
同步管理 API

提供同步操作和状态查询端点。
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.config import settings
from app.services.sync_service import sync_service
from app.services.oracle_client import oracle_client

logger = logging.getLogger(__name__)
router = APIRouter()


# ========== 响应模型 ==========

class SyncStatus(BaseModel):
    """同步状态"""
    running: bool
    enabled: bool
    scan_interval: int
    last_sync: Optional[datetime] = None
    alarm_levels: str
    severity_filter: Optional[str] = None


class SyncResult(BaseModel):
    """同步结果"""
    batch_id: str
    new_alarms: Dict[str, Any]
    status_changes: Dict[str, Any]
    heartbeat: Dict[str, Any]
    silences_cleanup: Dict[str, Any]
    error: Optional[str] = None


class AlarmSyncStatusItem(BaseModel):
    """告警同步状态项"""
    event_inst_id: int
    alarm_inst_id: Optional[int] = None
    sync_status: str
    zmc_alarm_state: Optional[str] = None
    silence_id: Optional[str] = None
    last_push_time: Optional[datetime] = None
    error_count: int = 0


class SyncLogItem(BaseModel):
    """同步日志项"""
    log_id: int
    operation: str
    event_inst_id: Optional[int] = None
    sync_batch_id: Optional[str] = None
    old_status: Optional[str] = None
    new_status: Optional[str] = None
    response_code: Optional[int] = None
    error_message: Optional[str] = None
    create_time: datetime


class SyncStatistics(BaseModel):
    """同步统计"""
    total_synced: int
    firing: int
    resolved: int
    silenced: int
    errors: int
    last_24h_operations: int


# ========== API 端点 ==========

@router.get("/sync/status", response_model=SyncStatus)
async def get_sync_status() -> SyncStatus:
    """
    获取同步服务状态
    """
    return SyncStatus(
        running=sync_service._running,
        enabled=settings.sync.enabled,
        scan_interval=settings.sync.scan_interval,
        alarm_levels=settings.sync.alarm_levels,
        severity_filter=settings.sync.severity_filter or None
    )


@router.post("/sync/trigger", response_model=SyncResult)
async def trigger_sync() -> SyncResult:
    """
    手动触发一次同步

    立即执行完整的同步周期，不等待定时任务。
    """
    if not sync_service._running:
        raise HTTPException(
            status_code=503,
            detail="Sync service is not running"
        )

    try:
        result = await sync_service.run_sync_cycle()
        return SyncResult(**result)
    except Exception as e:
        logger.error(f"Manual sync trigger failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Sync failed: {str(e)}"
        )


@router.get("/sync/alarms", response_model=List[AlarmSyncStatusItem])
async def get_synced_alarms(
    status: Optional[str] = Query(None, description="过滤状态: FIRING, RESOLVED, SILENCED"),
    limit: int = Query(100, ge=1, le=1000, description="返回数量限制"),
    offset: int = Query(0, ge=0, description="分页偏移")
) -> List[AlarmSyncStatusItem]:
    """
    获取已同步告警列表

    返回同步状态表中的告警记录。
    """
    try:
        query = """
            SELECT
                SYNC_ID,
                EVENT_INST_ID,
                ALARM_INST_ID,
                SYNC_STATUS,
                ZMC_ALARM_STATE,
                SILENCE_ID,
                LAST_PUSH_TIME,
                ERROR_COUNT
            FROM NM_ALARM_SYNC_STATUS
        """
        params = {}

        if status:
            query += " WHERE SYNC_STATUS = :status"
            params["status"] = status.upper()

        query += " ORDER BY LAST_PUSH_TIME DESC NULLS LAST"
        query += f" OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY"

        rows = oracle_client.execute_query(query, params)

        return [
            AlarmSyncStatusItem(
                event_inst_id=row["EVENT_INST_ID"],
                alarm_inst_id=row.get("ALARM_INST_ID"),
                sync_status=row["SYNC_STATUS"],
                zmc_alarm_state=row.get("ZMC_ALARM_STATE"),
                silence_id=row.get("SILENCE_ID"),
                last_push_time=row.get("LAST_PUSH_TIME"),
                error_count=row.get("ERROR_COUNT", 0)
            )
            for row in rows
        ]

    except Exception as e:
        logger.error(f"Failed to get synced alarms: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Database query failed: {str(e)}"
        )


@router.get("/sync/logs", response_model=List[SyncLogItem])
async def get_sync_logs(
    operation: Optional[str] = Query(None, description="过滤操作类型"),
    event_id: Optional[int] = Query(None, description="过滤事件ID"),
    limit: int = Query(100, ge=1, le=1000, description="返回数量限制"),
    offset: int = Query(0, ge=0, description="分页偏移")
) -> List[SyncLogItem]:
    """
    获取同步日志

    返回同步操作的历史日志记录。
    """
    try:
        query = """
            SELECT
                LOG_ID,
                OPERATION,
                EVENT_INST_ID,
                SYNC_BATCH_ID,
                OLD_STATUS,
                NEW_STATUS,
                RESPONSE_CODE,
                ERROR_MESSAGE,
                CREATE_TIME
            FROM NM_ALARM_SYNC_LOG
            WHERE 1=1
        """
        params = {}

        if operation:
            query += " AND OPERATION = :operation"
            params["operation"] = operation.upper()

        if event_id:
            query += " AND EVENT_INST_ID = :event_id"
            params["event_id"] = event_id

        query += " ORDER BY CREATE_TIME DESC"
        query += f" OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY"

        rows = oracle_client.execute_query(query, params)

        return [
            SyncLogItem(
                log_id=row["LOG_ID"],
                operation=row["OPERATION"],
                event_inst_id=row.get("EVENT_INST_ID"),
                sync_batch_id=row.get("SYNC_BATCH_ID"),
                old_status=row.get("OLD_STATUS"),
                new_status=row.get("NEW_STATUS"),
                response_code=row.get("RESPONSE_CODE"),
                error_message=row.get("ERROR_MESSAGE"),
                create_time=row["CREATE_TIME"]
            )
            for row in rows
        ]

    except Exception as e:
        logger.error(f"Failed to get sync logs: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Database query failed: {str(e)}"
        )


@router.get("/sync/statistics", response_model=SyncStatistics)
async def get_sync_statistics() -> SyncStatistics:
    """
    获取同步统计信息
    """
    try:
        # 获取各状态计数
        count_query = """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN SYNC_STATUS = 'FIRING' THEN 1 ELSE 0 END) as firing,
                SUM(CASE WHEN SYNC_STATUS = 'RESOLVED' THEN 1 ELSE 0 END) as resolved,
                SUM(CASE WHEN SYNC_STATUS = 'SILENCED' THEN 1 ELSE 0 END) as silenced,
                SUM(CASE WHEN ERROR_COUNT > 0 THEN 1 ELSE 0 END) as errors
            FROM NM_ALARM_SYNC_STATUS
        """
        count_result = oracle_client.execute_query(count_query)
        counts = count_result[0] if count_result else {}

        # 获取最近24小时操作数
        ops_query = """
            SELECT COUNT(*) as ops_count
            FROM NM_ALARM_SYNC_LOG
            WHERE CREATE_TIME >= SYSDATE - 1
        """
        ops_result = oracle_client.execute_query(ops_query)
        ops_count = ops_result[0].get("OPS_COUNT", 0) if ops_result else 0

        return SyncStatistics(
            total_synced=counts.get("TOTAL", 0) or 0,
            firing=counts.get("FIRING", 0) or 0,
            resolved=counts.get("RESOLVED", 0) or 0,
            silenced=counts.get("SILENCED", 0) or 0,
            errors=counts.get("ERRORS", 0) or 0,
            last_24h_operations=ops_count
        )

    except Exception as e:
        logger.error(f"Failed to get sync statistics: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Database query failed: {str(e)}"
        )


@router.delete("/sync/alarm/{event_inst_id}")
async def remove_sync_status(event_inst_id: int) -> Dict[str, Any]:
    """
    删除告警同步状态

    从同步状态表中移除指定告警的记录。
    """
    try:
        delete_query = """
            DELETE FROM NM_ALARM_SYNC_STATUS
            WHERE EVENT_INST_ID = :event_id
        """
        oracle_client.execute_update(delete_query, {"event_id": event_inst_id})

        return {
            "success": True,
            "event_inst_id": event_inst_id,
            "message": "Sync status removed"
        }

    except Exception as e:
        logger.error(f"Failed to remove sync status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Delete failed: {str(e)}"
        )
