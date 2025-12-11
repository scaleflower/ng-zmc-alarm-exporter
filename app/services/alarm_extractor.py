"""
告警数据抽取服务

从 ZMC Oracle 数据库抽取告警数据。
"""

import logging
from typing import List, Optional
from datetime import datetime

from app.models.alarm import ZMCAlarm, AlarmSyncStatus, AlarmStatistics
from app.services.oracle_client import OracleClient, oracle_client
from app.config import settings

logger = logging.getLogger(__name__)


class AlarmExtractor:
    """告警数据抽取器"""

    def __init__(self, db_client: Optional[OracleClient] = None):
        """
        初始化抽取器

        Args:
            db_client: Oracle 数据库客户端
        """
        self.db = db_client or oracle_client

    def extract_new_alarms(
        self,
        history_hours: Optional[int] = None,
        batch_size: Optional[int] = None
    ) -> List[ZMCAlarm]:
        """
        抽取新产生的告警（尚未同步）

        Args:
            history_hours: 历史回溯时长（小时）
            batch_size: 批处理大小

        Returns:
            告警列表
        """
        history_hours = history_hours or settings.sync.history_hours
        batch_size = batch_size or settings.sync.batch_size

        logger.info(f"Extracting new alarms (history: {history_hours}h, batch: {batch_size})")

        rows = self.db.get_new_alarms(history_hours, batch_size)
        alarms = [self._row_to_alarm(row) for row in rows]

        logger.info(f"Extracted {len(alarms)} new alarms")
        return alarms

    def extract_status_changed_alarms(self) -> List[dict]:
        """
        抽取状态变更的告警

        Returns:
            告警状态变更信息列表
        """
        logger.info("Extracting status changed alarms")

        rows = self.db.get_status_changed_alarms()

        logger.info(f"Found {len(rows)} alarms with status changes")
        return rows

    def extract_heartbeat_alarms(
        self,
        heartbeat_interval: Optional[int] = None
    ) -> List[dict]:
        """
        抽取需要心跳保活的活跃告警

        Args:
            heartbeat_interval: 心跳间隔（秒）

        Returns:
            需要心跳的告警列表
        """
        heartbeat_interval = heartbeat_interval or settings.sync.heartbeat_interval

        logger.debug(f"Extracting heartbeat alarms (interval: {heartbeat_interval}s)")

        rows = self.db.get_heartbeat_alarms(heartbeat_interval)

        logger.debug(f"Found {len(rows)} alarms needing heartbeat")
        return rows

    def extract_silences_to_remove(self) -> List[dict]:
        """
        抽取需要删除静默的告警

        Returns:
            需要删除静默的告警列表
        """
        logger.info("Extracting silences to remove")

        rows = self.db.get_silences_to_remove()

        logger.info(f"Found {len(rows)} silences to remove")
        return rows

    def get_sync_statistics(self) -> List[AlarmStatistics]:
        """
        获取同步统计信息

        Returns:
            统计信息列表
        """
        rows = self.db.get_sync_statistics()
        return [
            AlarmStatistics(
                sync_status=row["sync_status"],
                alarm_count=row["alarm_count"],
                earliest_alarm=row.get("earliest_alarm"),
                latest_update=row.get("latest_update"),
                total_pushes=row.get("total_pushes", 0) or 0,
                total_errors=row.get("total_errors", 0) or 0,
                alarms_with_errors=row.get("alarms_with_errors", 0) or 0
            )
            for row in rows
        ]

    def create_sync_status(
        self,
        alarm_inst_id: int,
        event_inst_id: Optional[int],
        sync_status: str,
        zmc_alarm_state: Optional[str]
    ) -> bool:
        """
        创建同步状态记录（以 ALARM_INST_ID 为核心）

        Args:
            alarm_inst_id: 告警汇总ID（必填，作为唯一标识）
            event_inst_id: 告警事件ID（可选）
            sync_status: 同步状态
            zmc_alarm_state: ZMC告警状态

        Returns:
            是否成功
        """
        try:
            self.db.insert_sync_status(
                alarm_inst_id=alarm_inst_id,
                event_inst_id=event_inst_id,
                sync_status=sync_status,
                zmc_alarm_state=zmc_alarm_state
            )
            return True
        except Exception as e:
            logger.error(f"Failed to create sync status for alarm {alarm_inst_id}: {e}")
            return False

    def update_sync_status(
        self,
        sync_id: int,
        sync_status: str,
        zmc_alarm_state: Optional[str] = None,
        am_fingerprint: Optional[str] = None,
        silence_id: Optional[str] = None
    ) -> bool:
        """
        更新同步状态（成功）

        Args:
            sync_id: 同步记录ID
            sync_status: 新状态
            zmc_alarm_state: ZMC状态
            am_fingerprint: Alertmanager指纹
            silence_id: 静默规则ID

        Returns:
            是否成功
        """
        try:
            self.db.update_sync_status_success(
                sync_id=sync_id,
                sync_status=sync_status,
                zmc_alarm_state=zmc_alarm_state,
                am_fingerprint=am_fingerprint,
                silence_id=silence_id
            )
            return True
        except Exception as e:
            logger.error(f"Failed to update sync status {sync_id}: {e}")
            return False

    def record_sync_error(self, sync_id: int, error_message: str) -> bool:
        """
        记录同步错误

        Args:
            sync_id: 同步记录ID
            error_message: 错误信息

        Returns:
            是否成功
        """
        try:
            self.db.update_sync_status_error(sync_id, error_message)
            return True
        except Exception as e:
            logger.error(f"Failed to record sync error for {sync_id}: {e}")
            return False

    def log_sync_operation(
        self,
        operation: str,
        event_inst_id: Optional[int] = None,
        sync_batch_id: Optional[str] = None,
        old_status: Optional[str] = None,
        new_status: Optional[str] = None,
        request_url: Optional[str] = None,
        request_method: Optional[str] = None,
        request_payload: Optional[str] = None,
        response_code: Optional[int] = None,
        response_body: Optional[str] = None,
        error_message: Optional[str] = None,
        duration_ms: Optional[int] = None
    ) -> bool:
        """
        记录同步操作日志

        Args:
            operation: 操作类型
            event_inst_id: 告警事件ID
            sync_batch_id: 批次ID
            old_status: 旧状态
            new_status: 新状态
            request_url: 请求URL
            request_method: HTTP方法
            request_payload: 请求体
            response_code: 响应码
            response_body: 响应体
            error_message: 错误信息
            duration_ms: 耗时(ms)

        Returns:
            是否成功
        """
        try:
            self.db.insert_sync_log({
                "sync_batch_id": sync_batch_id,
                "event_inst_id": event_inst_id,
                "operation": operation,
                "old_status": old_status,
                "new_status": new_status,
                "request_url": request_url,
                "request_method": request_method,
                "request_payload": request_payload[:4000] if request_payload else None,
                "response_code": response_code,
                "response_body": response_body[:4000] if response_body else None,
                "error_message": error_message[:2000] if error_message else None,
                "duration_ms": duration_ms
            })
            return True
        except Exception as e:
            logger.error(f"Failed to log sync operation: {e}")
            return False

    def _row_to_alarm(self, row: dict) -> ZMCAlarm:
        """
        将数据库行转换为告警对象

        支持新架构（以 NM_ALARM_CDR 为核心）和旧架构的字段映射

        Args:
            row: 数据库查询结果行

        Returns:
            告警对象
        """
        # 处理日期字段兼容性（新架构使用 cdr_create_date / event_create_date）
        create_date = (
            row.get("create_date") or
            row.get("event_create_date") or
            row.get("cdr_create_date")
        )

        return ZMCAlarm(
            event_inst_id=row.get("event_inst_id") or 0,  # 新架构中可能为空
            event_time=row.get("event_time"),
            create_date=create_date,
            alarm_code=row["alarm_code"],
            alarm_level=row.get("alarm_level"),
            reset_flag=row.get("reset_flag", "1"),
            task_type=row.get("task_type"),
            task_id=row.get("task_id"),
            res_inst_type=row.get("res_inst_type"),
            res_inst_id=row.get("res_inst_id"),
            app_env_id=row.get("app_env_id"),
            detail_info=row.get("detail_info"),
            data_1=row.get("data_1"),
            data_2=row.get("data_2"),
            data_3=row.get("data_3"),
            data_4=row.get("data_4"),
            data_5=row.get("data_5"),
            data_6=row.get("data_6"),
            data_7=row.get("data_7"),
            data_8=row.get("data_8"),
            data_9=row.get("data_9"),
            data_10=row.get("data_10"),
            alarm_inst_id=row.get("alarm_inst_id"),
            alarm_state=row.get("alarm_state"),
            reset_date=row.get("reset_date"),
            clear_date=row.get("clear_date"),
            confirm_date=row.get("confirm_date"),
            total_alarm=row.get("total_alarm"),
            clear_reason=row.get("clear_reason"),
            alarm_name=row.get("alarm_name"),
            alarm_type_code=row.get("alarm_type_code"),
            alarm_type_name=row.get("alarm_type_name"),
            default_warn_level=row.get("default_warn_level"),
            fault_reason=row.get("fault_reason"),
            deal_suggest=row.get("deal_suggest"),
            device_id=row.get("device_id"),
            host_name=row.get("host_name"),
            host_ip=row.get("host_ip"),
            device_model=row.get("device_model"),
            app_name=row.get("app_name"),
            app_user=row.get("app_user"),
            domain_id=row.get("domain_id"),
            business_domain=row.get("business_domain"),
            domain_type=row.get("domain_type"),
            environment=row.get("environment"),
            app_service_name=row.get("app_service_name"),
            service_ip=row.get("service_ip"),
            process_name=row.get("process_name"),
        )


# 全局抽取器实例
alarm_extractor = AlarmExtractor()
