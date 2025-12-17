"""
告警同步服务

核心同步逻辑，负责协调告警抽取、转换和推送。
"""

import logging
import asyncio
import uuid
from typing import Optional
from datetime import datetime, timezone

from app.config import settings
from app.models.alarm import ZMCAlarm
from app.services.oracle_client import OracleClient, oracle_client
from app.services.alarm_extractor import AlarmExtractor, alarm_extractor
from app.services.alarm_transformer import AlarmTransformer, alarm_transformer
from app.services.alert_client_factory import AlertClient, get_alert_client

logger = logging.getLogger(__name__)


class SyncService:
    """告警同步服务"""

    def __init__(
        self,
        db_client: Optional[OracleClient] = None,
        extractor: Optional[AlarmExtractor] = None,
        transformer: Optional[AlarmTransformer] = None,
        am_client: Optional[AlertClient] = None
    ):
        """
        初始化同步服务

        Args:
            db_client: Oracle 客户端
            extractor: 告警抽取器
            transformer: 告警转换器
            am_client: 告警客户端 (Alertmanager 或 OpsGenie)
        """
        self.db = db_client or oracle_client
        self.extractor = extractor or alarm_extractor
        self.transformer = transformer or alarm_transformer
        self.am_client = am_client or get_alert_client()

        self._running = False
        self._sync_task: Optional[asyncio.Task] = None

    def generate_batch_id(self) -> str:
        """生成同步批次ID"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        short_uuid = str(uuid.uuid4())[:8]
        return f"{timestamp}_{short_uuid}"

    # ========== 核心同步流程 ==========

    async def sync_new_alarms(self, batch_id: Optional[str] = None) -> dict:
        """
        同步新产生的告警

        Returns:
            同步结果统计
        """
        batch_id = batch_id or self.generate_batch_id()
        stats = {
            "batch_id": batch_id,
            "extracted": 0,
            "filtered": 0,
            "pushed": 0,
            "errors": 0
        }

        logger.info(f"Starting sync_new_alarms, batch_id: {batch_id}")

        try:
            # 1. 抽取新告警
            alarms = self.extractor.extract_new_alarms()
            stats["extracted"] = len(alarms)

            if not alarms:
                logger.info("No new alarms to sync")
                return stats

            # 2. 根据级别过滤告警
            filtered_alarms = self.transformer.filter_alarms(alarms)
            stats["filtered"] = len(alarms) - len(filtered_alarms)

            if not filtered_alarms:
                logger.info("All alarms filtered out by level configuration")
                return stats

            # 3. 转换为 Prometheus 格式
            prometheus_alerts = []
            for alarm in filtered_alarms:
                try:
                    alert = self.transformer.transform_to_prometheus(alarm, resolved=False)
                    prometheus_alerts.append((alarm, alert))
                except Exception as e:
                    logger.error(f"Failed to transform alarm {alarm.event_inst_id}: {e}")
                    stats["errors"] += 1

            # 4. 批量推送到 Alertmanager
            if prometheus_alerts:
                alerts_to_push = [alert for _, alert in prometheus_alerts]
                result = await self.am_client.push_alerts(alerts_to_push)

                if result["success"]:
                    # 5. 更新同步状态（以 ALARM_INST_ID 为核心）
                    for alarm, alert in prometheus_alerts:
                        try:
                            self.extractor.create_sync_status(
                                alarm_inst_id=alarm.alarm_inst_id,
                                event_inst_id=alarm.event_inst_id,
                                sync_status="FIRING",
                                zmc_alarm_state=alarm.alarm_state or "U"
                            )
                            stats["pushed"] += 1
                        except Exception as e:
                            logger.error(f"Failed to create sync status for alarm {alarm.alarm_inst_id}: {e}")
                            stats["errors"] += 1

                    # 记录日志
                    self.extractor.log_sync_operation(
                        operation="PUSH_FIRING",
                        sync_batch_id=batch_id,
                        new_status="FIRING",
                        request_url=self.am_client.config.alerts_url,
                        request_method="POST",
                        response_code=result.get("status_code"),
                        duration_ms=result.get("duration_ms")
                    )
                else:
                    stats["errors"] += len(prometheus_alerts)
                    self.extractor.log_sync_operation(
                        operation="ERROR",
                        sync_batch_id=batch_id,
                        error_message=result.get("error"),
                        request_url=self.am_client.config.alerts_url,
                        request_method="POST",
                        response_code=result.get("status_code"),
                        duration_ms=result.get("duration_ms")
                    )

        except Exception as e:
            logger.error(f"sync_new_alarms failed: {e}")
            stats["errors"] += 1
            self.extractor.log_sync_operation(
                operation="ERROR",
                sync_batch_id=batch_id,
                error_message=str(e)
            )

        logger.info(f"sync_new_alarms completed: {stats}")
        return stats

    async def sync_refired_alarms(self, batch_id: Optional[str] = None) -> dict:
        """
        同步重新触发的告警（曾经恢复但又重新变为活跃的告警）

        这解决了历史告警重复出现时漏报的问题。

        Returns:
            同步结果统计
        """
        batch_id = batch_id or self.generate_batch_id()
        stats = {
            "batch_id": batch_id,
            "detected": 0,
            "pushed": 0,
            "errors": 0
        }

        logger.info(f"Starting sync_refired_alarms, batch_id: {batch_id}")

        try:
            # 1. 抽取重新触发的告警
            refired_alarms = self.extractor.extract_refired_alarms()
            stats["detected"] = len(refired_alarms)

            if not refired_alarms:
                logger.debug("No refired alarms detected")
                return stats

            # 2. 转换为 Prometheus 格式并推送
            for alarm_data in refired_alarms:
                try:
                    sync_id = alarm_data["sync_id"]
                    alarm_inst_id = alarm_data["alarm_inst_id"]
                    old_state = alarm_data.get("old_zmc_state")
                    new_state = alarm_data.get("new_zmc_state", "U")
                    total_alarm = alarm_data.get("total_alarm", 1)

                    logger.info(
                        f"Processing refired alarm: alarm_inst_id={alarm_inst_id}, "
                        f"state={old_state}->{new_state}, total_alarm={total_alarm}"
                    )

                    # 构建告警对象
                    alarm = self._build_alarm_from_data(alarm_data)

                    # 转换为 Prometheus 格式
                    alert = self.transformer.transform_to_prometheus(alarm, resolved=False)

                    # 推送到 Alertmanager
                    result = await self.am_client.push_single_alert(alert)

                    if result["success"]:
                        # 更新同步状态：从 RESOLVED 变回 FIRING
                        self.extractor.update_sync_status(
                            sync_id=sync_id,
                            sync_status="FIRING",
                            zmc_alarm_state=new_state
                        )
                        stats["pushed"] += 1

                        self.extractor.log_sync_operation(
                            operation="PUSH_REFIRED",
                            event_inst_id=alarm_data.get("event_inst_id"),
                            sync_batch_id=batch_id,
                            old_status="RESOLVED",
                            new_status="FIRING",
                            request_url=self.am_client.config.alerts_url,
                            request_method="POST",
                            response_code=result.get("status_code"),
                            duration_ms=result.get("duration_ms")
                        )

                        logger.info(f"Refired alarm {alarm_inst_id} pushed successfully")
                    else:
                        self.extractor.record_sync_error(sync_id, result.get("error", "Unknown error"))
                        stats["errors"] += 1

                except Exception as e:
                    logger.error(f"Failed to process refired alarm: {e}")
                    stats["errors"] += 1

        except Exception as e:
            logger.error(f"sync_refired_alarms failed: {e}")
            stats["errors"] += 1

        logger.info(f"sync_refired_alarms completed: {stats}")
        return stats

    def _build_alarm_from_data(self, alarm_data: dict) -> ZMCAlarm:
        """从数据库行数据构建告警对象"""
        return ZMCAlarm(
            event_inst_id=alarm_data.get("event_inst_id") or 0,
            alarm_inst_id=alarm_data.get("alarm_inst_id"),
            alarm_code=alarm_data["alarm_code"],
            alarm_level=alarm_data.get("alarm_level"),
            alarm_state=alarm_data.get("new_zmc_state") or alarm_data.get("alarm_state", "U"),
            reset_flag="1",
            event_time=alarm_data.get("event_time"),
            create_date=alarm_data.get("event_create_date") or alarm_data.get("cdr_create_date"),
            detail_info=alarm_data.get("detail_info"),
            data_1=alarm_data.get("data_1"),
            data_2=alarm_data.get("data_2"),
            data_3=alarm_data.get("data_3"),
            data_4=alarm_data.get("data_4"),
            data_5=alarm_data.get("data_5"),
            data_6=alarm_data.get("data_6"),
            data_7=alarm_data.get("data_7"),
            data_8=alarm_data.get("data_8"),
            data_9=alarm_data.get("data_9"),
            data_10=alarm_data.get("data_10"),
            total_alarm=alarm_data.get("total_alarm"),
            alarm_name=alarm_data.get("alarm_name"),
            fault_reason=alarm_data.get("fault_reason"),
            deal_suggest=alarm_data.get("deal_suggest"),
            default_warn_level=alarm_data.get("default_warn_level"),
            host_name=alarm_data.get("host_name"),
            host_ip=alarm_data.get("host_ip"),
            device_model=alarm_data.get("device_model"),
            app_name=alarm_data.get("app_name"),
            app_user=alarm_data.get("app_user"),
            business_domain=alarm_data.get("business_domain"),
            environment=alarm_data.get("environment"),
            res_inst_id=alarm_data.get("res_inst_id"),
            app_env_id=alarm_data.get("app_env_id"),
        )

    async def sync_status_changes(self, batch_id: Optional[str] = None) -> dict:
        """
        同步状态变更的告警

        Returns:
            同步结果统计
        """
        batch_id = batch_id or self.generate_batch_id()
        stats = {
            "batch_id": batch_id,
            "detected": 0,
            "resolved": 0,
            "silenced": 0,
            "errors": 0
        }

        logger.info(f"Starting sync_status_changes, batch_id: {batch_id}")

        try:
            # 获取状态变更的告警
            changed_alarms = self.extractor.extract_status_changed_alarms()
            stats["detected"] = len(changed_alarms)

            if not changed_alarms:
                logger.debug("No status changes detected")
                return stats

            for alarm_data in changed_alarms:
                try:
                    old_state = alarm_data.get("old_zmc_state")
                    new_state = alarm_data.get("new_zmc_state")
                    sync_id = alarm_data["sync_id"]
                    event_inst_id = alarm_data["event_inst_id"]
                    push_count = alarm_data.get("push_count", 0) or 0

                    logger.info(f"Processing status change: event={event_inst_id}, {old_state} -> {new_state}, push_count={push_count}")

                    # 如果告警从未被推送过（push_count=0），则跳过推送，直接更新状态
                    # 这些是历史告警，在同步服务启动前就已经恢复了
                    if push_count == 0:
                        logger.info(f"Skipping alarm {event_inst_id}: never pushed before, directly mark as RESOLVED")
                        self.extractor.update_sync_status(
                            sync_id=sync_id,
                            sync_status="RESOLVED",
                            zmc_alarm_state=new_state
                        )
                        stats["resolved"] += 1
                        continue

                    # 根据新状态决定操作
                    if new_state in ("A", "C"):
                        # 自动恢复或已确认 -> 推送 resolved
                        await self._handle_alarm_resolved(alarm_data, batch_id)
                        stats["resolved"] += 1

                    elif new_state == "M":
                        # 手工清除 -> 创建静默
                        if settings.silence.use_silence_api:
                            await self._handle_alarm_silenced(alarm_data, batch_id)
                            stats["silenced"] += 1
                        else:
                            # 不使用静默API，直接标记为resolved
                            await self._handle_alarm_resolved(alarm_data, batch_id)
                            stats["resolved"] += 1

                except Exception as e:
                    logger.error(f"Failed to process status change: {e}")
                    stats["errors"] += 1

        except Exception as e:
            logger.error(f"sync_status_changes failed: {e}")
            stats["errors"] += 1

        logger.info(f"sync_status_changes completed: {stats}")
        return stats

    async def sync_heartbeat(self, batch_id: Optional[str] = None) -> dict:
        """
        心跳保活：重新推送活跃告警

        Returns:
            同步结果统计
        """
        batch_id = batch_id or self.generate_batch_id()
        stats = {
            "batch_id": batch_id,
            "heartbeat_count": 0,
            "errors": 0
        }

        logger.debug(f"Starting sync_heartbeat, batch_id: {batch_id}")

        try:
            # 获取需要心跳的告警
            heartbeat_alarms = self.extractor.extract_heartbeat_alarms()

            if not heartbeat_alarms:
                logger.debug("No alarms need heartbeat")
                return stats

            # 转换并推送
            alerts_to_push = []
            alarm_sync_ids = []

            for alarm_data in heartbeat_alarms:
                try:
                    # 创建简化的告警对象（支持新架构）
                    alarm = ZMCAlarm(
                        event_inst_id=alarm_data.get("event_inst_id") or 0,
                        alarm_inst_id=alarm_data.get("alarm_inst_id"),
                        alarm_code=alarm_data["alarm_code"],
                        alarm_level=alarm_data.get("alarm_level"),
                        alarm_state=alarm_data.get("alarm_state", "U"),
                        reset_flag="1",
                        event_time=alarm_data.get("event_time"),
                        detail_info=alarm_data.get("detail_info"),
                        alarm_name=alarm_data.get("alarm_name"),
                        host_name=alarm_data.get("host_name"),
                        host_ip=alarm_data.get("host_ip"),
                        app_name=alarm_data.get("app_name"),
                        business_domain=alarm_data.get("business_domain"),
                        environment=alarm_data.get("environment"),
                    )

                    alert = self.transformer.transform_to_prometheus(alarm, resolved=False)
                    alerts_to_push.append(alert)
                    alarm_sync_ids.append(alarm_data["sync_id"])

                except Exception as e:
                    logger.error(f"Failed to prepare heartbeat for alarm {alarm_data.get('alarm_inst_id')}: {e}")
                    stats["errors"] += 1

            # 批量推送
            if alerts_to_push:
                result = await self.am_client.push_alerts(alerts_to_push)

                if result["success"]:
                    # 更新推送时间
                    for sync_id in alarm_sync_ids:
                        try:
                            self.extractor.update_sync_status(
                                sync_id=sync_id,
                                sync_status="FIRING",
                                zmc_alarm_state="U"
                            )
                            stats["heartbeat_count"] += 1
                        except Exception as e:
                            logger.error(f"Failed to update heartbeat status: {e}")

                    self.extractor.log_sync_operation(
                        operation="HEARTBEAT",
                        sync_batch_id=batch_id,
                        request_url=self.am_client.config.alerts_url,
                        request_method="POST",
                        response_code=result.get("status_code"),
                        duration_ms=result.get("duration_ms")
                    )
                else:
                    stats["errors"] += len(alerts_to_push)

        except Exception as e:
            logger.error(f"sync_heartbeat failed: {e}")
            stats["errors"] += 1

        logger.debug(f"sync_heartbeat completed: {stats}")
        return stats

    async def cleanup_silences(self, batch_id: Optional[str] = None) -> dict:
        """
        清理已恢复告警的静默规则

        Returns:
            清理结果统计
        """
        batch_id = batch_id or self.generate_batch_id()
        stats = {
            "batch_id": batch_id,
            "removed": 0,
            "errors": 0
        }

        if not settings.silence.auto_remove_on_clear:
            return stats

        logger.info(f"Starting cleanup_silences, batch_id: {batch_id}")

        try:
            silences_to_remove = self.extractor.extract_silences_to_remove()

            for silence_data in silences_to_remove:
                try:
                    silence_id = silence_data["silence_id"]
                    sync_id = silence_data["sync_id"]

                    result = await self.am_client.delete_silence(silence_id)

                    if result["success"]:
                        # 更新状态为 RESOLVED
                        self.extractor.update_sync_status(
                            sync_id=sync_id,
                            sync_status="RESOLVED",
                            zmc_alarm_state=silence_data.get("current_zmc_state"),
                            silence_id=None
                        )
                        stats["removed"] += 1

                        self.extractor.log_sync_operation(
                            operation="DELETE_SILENCE",
                            event_inst_id=silence_data["event_inst_id"],
                            sync_batch_id=batch_id,
                            old_status="SILENCED",
                            new_status="RESOLVED",
                            request_url=f"{self.am_client.config.silences_url}/{silence_id}",
                            request_method="DELETE",
                            response_code=result.get("status_code"),
                            duration_ms=result.get("duration_ms")
                        )
                    else:
                        stats["errors"] += 1

                except Exception as e:
                    logger.error(f"Failed to cleanup silence: {e}")
                    stats["errors"] += 1

        except Exception as e:
            logger.error(f"cleanup_silences failed: {e}")
            stats["errors"] += 1

        logger.info(f"cleanup_silences completed: {stats}")
        return stats

    # ========== 内部处理方法 ==========

    async def _handle_alarm_resolved(self, alarm_data: dict, batch_id: str):
        """处理告警恢复"""
        event_inst_id = alarm_data["event_inst_id"]
        sync_id = alarm_data["sync_id"]

        # 构建恢复告警 - 使用完整的告警数据以保证 RESOLVED 消息包含所有详细信息
        resolved_time = (
            alarm_data.get("reset_date") or
            alarm_data.get("clear_date") or
            alarm_data.get("confirm_date") or
            datetime.now(timezone.utc)
        )

        # 使用 _build_alarm_from_data 构建完整的告警对象
        alarm = self._build_alarm_from_data(alarm_data)
        alarm.reset_flag = "0"  # 标记为已恢复

        alert = self.transformer.transform_to_prometheus(
            alarm,
            resolved=True,
            resolved_at=resolved_time
        )

        # 推送恢复告警
        result = await self.am_client.push_single_alert(alert)

        if result["success"]:
            # 如果有静默规则，先删除
            silence_id = alarm_data.get("silence_id")
            if silence_id:
                await self.am_client.delete_silence(silence_id)

            # 更新状态
            self.extractor.update_sync_status(
                sync_id=sync_id,
                sync_status="RESOLVED",
                zmc_alarm_state=alarm_data.get("new_zmc_state"),
                silence_id=None
            )

            self.extractor.log_sync_operation(
                operation="PUSH_RESOLVED",
                event_inst_id=event_inst_id,
                sync_batch_id=batch_id,
                old_status="FIRING",
                new_status="RESOLVED",
                request_url=self.am_client.config.alerts_url,
                request_method="POST",
                response_code=result.get("status_code"),
                duration_ms=result.get("duration_ms")
            )
        else:
            self.extractor.record_sync_error(sync_id, result.get("error", "Unknown error"))
            raise Exception(f"Failed to push resolved alert: {result.get('error')}")

    async def _handle_alarm_silenced(self, alarm_data: dict, batch_id: str):
        """
        处理告警静默（手工清除）

        处理流程：
        1. 先推送 resolved 告警 → 关闭 OpsGenie 中的告警
        2. 再创建 Silence 规则 → 防止告警重新触发时发送通知

        这样确保：
        - OpsGenie 中已存在的告警被关闭
        - 如果告警再次产生（未真正恢复），会被 Silence 拦截
        """
        event_inst_id = alarm_data["event_inst_id"]
        sync_id = alarm_data["sync_id"]

        # 使用 _build_alarm_from_data 构建完整的告警对象
        alarm = self._build_alarm_from_data(alarm_data)
        alarm.reset_flag = "0"  # 标记为已恢复

        # 步骤1: 推送 resolved 告警到 Alertmanager → 关闭 OpsGenie 告警
        clear_time = alarm_data.get("clear_date") or datetime.now(timezone.utc)
        resolved_alert = self.transformer.transform_to_prometheus(
            alarm,
            resolved=True,
            resolved_at=clear_time
        )

        resolve_result = await self.am_client.push_single_alert(resolved_alert)

        if not resolve_result["success"]:
            self.extractor.record_sync_error(sync_id, resolve_result.get("error", "Unknown error"))
            raise Exception(f"Failed to push resolved alert for silenced alarm: {resolve_result.get('error')}")

        logger.info(f"Pushed resolved alert for silenced alarm {event_inst_id}")

        self.extractor.log_sync_operation(
            operation="PUSH_RESOLVED_FOR_SILENCE",
            event_inst_id=event_inst_id,
            sync_batch_id=batch_id,
            old_status="FIRING",
            new_status="RESOLVED",
            request_url=self.am_client.config.alerts_url,
            request_method="POST",
            response_code=resolve_result.get("status_code"),
            duration_ms=resolve_result.get("duration_ms")
        )

        # 步骤2: 创建 Silence 规则 → 防止告警重新触发
        silence = self.transformer.create_silence(
            alarm,
            comment=f"Shielded in ZMC at {clear_time.strftime('%Y-%m-%d %H:%M:%S')}. "
                    f"Reason: {alarm_data.get('clear_reason', 'Manual clear')}"
        )

        silence_result = await self.am_client.create_silence(silence)

        if silence_result["success"]:
            self.extractor.update_sync_status(
                sync_id=sync_id,
                sync_status="SILENCED",
                zmc_alarm_state="M",
                silence_id=silence_result.get("silence_id")
            )

            self.extractor.log_sync_operation(
                operation="CREATE_SILENCE",
                event_inst_id=event_inst_id,
                sync_batch_id=batch_id,
                old_status="RESOLVED",
                new_status="SILENCED",
                request_url=self.am_client.config.silences_url,
                request_method="POST",
                response_code=silence_result.get("status_code"),
                duration_ms=silence_result.get("duration_ms")
            )

            logger.info(f"Created silence {silence_result.get('silence_id')} for alarm {event_inst_id}")
        else:
            # Silence 创建失败，但 resolved 已推送成功，记录警告但不抛异常
            logger.warning(
                f"Failed to create silence for alarm {event_inst_id}, "
                f"but resolved alert was pushed successfully: {silence_result.get('error')}"
            )
            # 更新状态为 RESOLVED（因为 resolved 已成功）
            self.extractor.update_sync_status(
                sync_id=sync_id,
                sync_status="RESOLVED",
                zmc_alarm_state="M",
                silence_id=None
            )

    # ========== 定时任务控制 ==========

    async def run_sync_cycle(self) -> dict:
        """
        执行一次完整的同步周期

        Returns:
            同步结果汇总
        """
        batch_id = self.generate_batch_id()
        logger.info(f"=== Starting sync cycle, batch_id: {batch_id} ===")

        results = {
            "batch_id": batch_id,
            "new_alarms": {},
            "refired_alarms": {},
            "status_changes": {},
            "heartbeat": {},
            "silences_cleanup": {}
        }

        try:
            # 1. 同步新告警
            results["new_alarms"] = await self.sync_new_alarms(batch_id)

            # 2. 同步重新触发的告警（曾经恢复但又重新变为活跃的告警）
            results["refired_alarms"] = await self.sync_refired_alarms(batch_id)

            # 3. 同步状态变更
            results["status_changes"] = await self.sync_status_changes(batch_id)

            # 4. 心跳保活（仅在启用时执行）
            if settings.sync.heartbeat_enabled:
                results["heartbeat"] = await self.sync_heartbeat(batch_id)
            else:
                results["heartbeat"] = {"skipped": True, "reason": "heartbeat_enabled=False"}

            # 5. 清理静默
            results["silences_cleanup"] = await self.cleanup_silences(batch_id)

        except Exception as e:
            logger.error(f"Sync cycle failed: {e}")
            results["error"] = str(e)

        logger.info(f"=== Sync cycle completed, batch_id: {batch_id} ===")
        return results

    async def start_background_sync(self):
        """启动后台同步任务"""
        if self._running:
            logger.warning("Background sync is already running")
            return

        self._running = True
        logger.info("Starting background sync service")

        # 初始化数据库连接
        self.db.init_pool()

        # 启动时同步历史告警
        if settings.sync.sync_on_startup:
            logger.info("Syncing historical alarms on startup...")
            await self.sync_new_alarms()

        # 启动定时同步
        self._sync_task = asyncio.create_task(self._sync_loop())

    async def stop_background_sync(self):
        """停止后台同步任务"""
        if not self._running:
            return

        logger.info("Stopping background sync service")
        self._running = False

        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass

        # 关闭连接
        await self.am_client.close()
        self.db.close_pool()

    async def _sync_loop(self):
        """同步主循环"""
        scan_interval = settings.sync.scan_interval

        while self._running:
            try:
                await self.run_sync_cycle()
            except Exception as e:
                logger.error(f"Sync loop error: {e}")

            # 等待下一个周期
            await asyncio.sleep(scan_interval)


# 全局同步服务实例
sync_service = SyncService()
