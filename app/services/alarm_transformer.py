"""
告警数据转换服务

将 ZMC 告警转换为 Prometheus Alertmanager 格式。
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta

from app.models.alarm import ZMCAlarm
from app.models.prometheus import PrometheusAlert, PrometheusSilence
from app.config import settings

logger = logging.getLogger(__name__)


class AlarmTransformer:
    """告警数据转换器"""

    def __init__(self):
        """初始化转换器"""
        self.severity_mapping = settings.severity
        self.status_mapping = settings.status
        self.static_labels = settings.labels
        self.silence_config = settings.silence
        self.sync_config = settings.sync

    def should_sync_alarm(self, alarm: ZMCAlarm) -> bool:
        """
        判断告警是否应该被同步

        根据配置的告警级别和severity过滤规则判断

        Args:
            alarm: ZMC 告警对象

        Returns:
            是否应该同步
        """
        # 获取允许的ZMC告警级别
        allowed_levels = self.sync_config.get_allowed_zmc_levels()

        # 检查ZMC告警级别
        alarm_level = str(alarm.effective_severity)
        if alarm_level not in allowed_levels:
            logger.debug(
                f"Alarm {alarm.event_inst_id} filtered out: level {alarm_level} not in {allowed_levels}"
            )
            return False

        # 获取允许的Prometheus severity
        allowed_severities = self.sync_config.get_allowed_severities()

        # 如果配置了severity过滤，则检查映射后的severity
        if allowed_severities:
            mapped_severity = self.severity_mapping.get_severity(alarm_level)
            if mapped_severity.lower() not in allowed_severities:
                logger.debug(
                    f"Alarm {alarm.event_inst_id} filtered out: severity {mapped_severity} not in {allowed_severities}"
                )
                return False

        return True

    def filter_alarms(self, alarms: List[ZMCAlarm]) -> List[ZMCAlarm]:
        """
        根据配置过滤告警列表

        Args:
            alarms: 原始告警列表

        Returns:
            过滤后的告警列表
        """
        filtered = [alarm for alarm in alarms if self.should_sync_alarm(alarm)]

        if len(filtered) != len(alarms):
            logger.info(
                f"Filtered alarms: {len(alarms)} -> {len(filtered)} "
                f"(allowed levels: {self.sync_config.alarm_levels}, "
                f"severity filter: {self.sync_config.severity_filter or 'none'})"
            )

        return filtered

    def transform_to_prometheus(
        self,
        alarm: ZMCAlarm,
        resolved: bool = False,
        resolved_at: Optional[datetime] = None
    ) -> PrometheusAlert:
        """
        将 ZMC 告警转换为 Prometheus 告警格式

        Args:
            alarm: ZMC 告警对象
            resolved: 是否为已恢复状态
            resolved_at: 恢复时间

        Returns:
            Prometheus 告警对象
        """
        # 构建标签
        labels = self._build_labels(alarm)

        # 构建注解
        annotations = self._build_annotations(alarm)

        # 确定告警开始时间（使用本地时区，不转换为UTC）
        starts_at = alarm.event_time or alarm.create_date or datetime.now()

        if resolved:
            # 恢复告警：设置结束时间
            ends_at = resolved_at or alarm.get_resolved_time() or datetime.now()

            # 确保 startsAt < endsAt，Alertmanager 要求开始时间必须早于结束时间
            # 如果因为时区或数据问题导致 starts_at >= ends_at，则调整 starts_at
            if starts_at >= ends_at:
                # 将开始时间设为结束时间前1秒
                starts_at = ends_at - timedelta(seconds=1)
                logger.warning(
                    f"Adjusted startsAt for alarm {alarm.event_inst_id}: "
                    f"original event_time >= resolved_time, set startsAt to {starts_at}"
                )

            return PrometheusAlert.create_resolved(
                alertname=labels.pop("alertname"),
                instance=labels.pop("instance"),
                severity=labels.pop("severity"),
                starts_at=starts_at,
                ends_at=ends_at,
                labels=labels,
                annotations=annotations,
                generator_url=self._build_generator_url(alarm)
            )
        else:
            # 活跃告警：不设置结束时间
            return PrometheusAlert.create_firing(
                alertname=labels.pop("alertname"),
                instance=labels.pop("instance"),
                severity=labels.pop("severity"),
                starts_at=starts_at,
                labels=labels,
                annotations=annotations,
                generator_url=self._build_generator_url(alarm)
            )

    def transform_batch(
        self,
        alarms: List[ZMCAlarm],
        resolved: bool = False
    ) -> List[PrometheusAlert]:
        """
        批量转换告警

        Args:
            alarms: ZMC 告警列表
            resolved: 是否为已恢复状态

        Returns:
            Prometheus 告警列表
        """
        return [self.transform_to_prometheus(alarm, resolved) for alarm in alarms]

    def create_silence(
        self,
        alarm: ZMCAlarm,
        duration_hours: Optional[int] = None,
        comment: Optional[str] = None
    ) -> PrometheusSilence:
        """
        为告警创建静默规则

        Args:
            alarm: ZMC 告警对象
            duration_hours: 静默时长（小时）
            comment: 静默注释

        Returns:
            静默规则对象
        """
        duration = duration_hours or self.silence_config.default_duration_hours

        starts_at = datetime.now(timezone.utc)
        ends_at = starts_at + timedelta(hours=duration)

        # 使用模板生成注释
        if comment is None:
            comment = self.silence_config.comment_template.format(
                time=starts_at.strftime("%Y-%m-%d %H:%M:%S"),
                operator="zmc-alarm-exporter",
                alarm_code=alarm.alarm_code,
                event_id=alarm.event_inst_id
            )

        return PrometheusSilence.create_for_alarm(
            event_id=alarm.event_inst_id,
            alarm_code=alarm.alarm_code,
            instance=alarm.effective_host,
            starts_at=starts_at,
            ends_at=ends_at,
            created_by="zmc-alarm-exporter",
            comment=comment
        )

    def get_sync_status(self, zmc_state: str) -> str:
        """
        获取同步状态

        Args:
            zmc_state: ZMC 告警状态

        Returns:
            同步状态
        """
        return self.status_mapping.get_sync_status(zmc_state)

    def _build_labels(self, alarm: ZMCAlarm) -> Dict[str, str]:
        """
        构建 Prometheus 标签

        Args:
            alarm: ZMC 告警对象

        Returns:
            标签字典
        """
        labels = {
            # 核心标签
            "alertname": self._sanitize_label_value(alarm.effective_alert_name),
            "instance": self._sanitize_label_value(alarm.effective_host),
            "severity": self.severity_mapping.get_severity(alarm.effective_severity),

            # ZMC 标识
            "alarm_id": str(alarm.alarm_inst_id) if alarm.alarm_inst_id else str(alarm.event_inst_id),
            "event_id": str(alarm.event_inst_id),
            "alarm_code": str(alarm.alarm_code),

            # 资源信息
            "resource_type": self._sanitize_label_value(alarm.res_inst_type or "UNKNOWN"),
        }

        # 添加主机名（如果与 instance 不同）
        if alarm.host_name and alarm.host_name != alarm.host_ip:
            labels["host"] = self._sanitize_label_value(alarm.host_name)

        # 添加应用信息
        if alarm.app_name:
            labels["application"] = self._sanitize_label_value(alarm.app_name)

        # 添加业务域信息
        if alarm.business_domain:
            labels["domain"] = self._sanitize_label_value(alarm.business_domain)

        # 添加环境信息
        if alarm.environment:
            labels["env"] = self._sanitize_label_value(alarm.environment.lower())

        # 添加任务类型
        if alarm.task_type:
            labels["task_type"] = self._sanitize_label_value(alarm.task_type)

        # 添加静态标签
        static = self.static_labels.to_dict()
        labels.update(static)

        return labels

    def _get_severity_display(self, alarm: ZMCAlarm) -> tuple:
        """
        获取告警级别的显示信息

        Args:
            alarm: ZMC 告警对象

        Returns:
            (英文级别, ZMC级别代码) 元组
        """
        level = str(alarm.effective_severity)
        severity_en = self.severity_mapping.get_severity(level)

        # ZMC alarm level description (English only to avoid encoding issues)
        severity_desc_map = {
            "1": "Critical",
            "2": "Major",
            "3": "Minor",
            "4": "Warning",
            "0": "Undefined"
        }
        severity_desc = severity_desc_map.get(level, "Unknown")

        return severity_en, severity_desc

    def _build_annotations(self, alarm: ZMCAlarm) -> Dict[str, str]:
        """
        构建 Prometheus 注解

        Args:
            alarm: ZMC 告警对象

        Returns:
            注解字典
        """
        annotations = {}

        # Get severity display info
        severity_en, severity_desc = self._get_severity_display(alarm)

        # Summary
        summary = alarm.alarm_name or f"ZMC Alert {alarm.alarm_code}"
        annotations["summary"] = summary

        # Severity level annotation (English only)
        annotations["severity_level"] = f"{severity_en.upper()} ({severity_desc})"

        # Description - bullet list format for better readability
        # Use "  \n" (two spaces + newline) for Markdown line breaks in DingTalk
        description_lines = []

        # 0. Severity level (first item)
        description_lines.append(f"• Severity: {severity_en.upper()} ({severity_desc})")

        # 1. Detail info
        if alarm.detail_info:
            detail = alarm.detail_info.replace("\n", " ").replace("\r", "").strip()
            if len(detail) > 200:
                detail = detail[:197] + "..."
            description_lines.append(f"• Detail: {detail}")

        # 2. Location info (each on separate line)
        if alarm.host_name:
            description_lines.append(f"• Host: {alarm.host_name}")
        if alarm.host_ip:
            description_lines.append(f"• IP: {alarm.host_ip}")
        if alarm.app_name:
            description_lines.append(f"• App: {alarm.app_name}")
        if alarm.business_domain:
            description_lines.append(f"• Domain: {alarm.business_domain}")

        # 3. Fault reason
        if alarm.fault_reason:
            description_lines.append(f"• Reason: {alarm.fault_reason}")

        # 4. Suggestion
        if alarm.deal_suggest:
            suggest = alarm.deal_suggest
            if len(suggest) > 150:
                suggest = suggest[:147] + "..."
            description_lines.append(f"• Suggestion: {suggest}")

        # Join with "  \n" - two trailing spaces force Markdown line break
        # Add leading newline so "Description:" and first bullet are on separate lines
        annotations["description"] = "  \n" + "  \n".join(description_lines) if description_lines else summary

        # 故障原因 (保留单独字段，供其他用途)
        if alarm.fault_reason:
            annotations["fault_reason"] = alarm.fault_reason

        # 处理建议 (runbook)
        if alarm.deal_suggest:
            annotations["runbook"] = alarm.deal_suggest

        # 告警类型
        if alarm.alarm_type_name:
            annotations["alarm_type"] = alarm.alarm_type_name

        # 扩展字段（如果有值）
        for i in range(1, 11):
            data_field = getattr(alarm, f"data_{i}", None)
            if data_field:
                annotations[f"data_{i}"] = data_field

        return annotations

    def _build_generator_url(self, alarm: ZMCAlarm) -> Optional[str]:
        """
        构建告警来源 URL

        Args:
            alarm: ZMC 告警对象

        Returns:
            URL 字符串
        """
        # TODO: 可以配置 ZMC Portal URL 来生成详情链接
        return None

    @staticmethod
    def _sanitize_label_value(value: str) -> str:
        """
        清理标签值，确保符合 Prometheus 规范

        Args:
            value: 原始值

        Returns:
            清理后的值
        """
        if not value:
            return "unknown"

        # Prometheus 标签值可以是任意 Unicode 字符
        # 但建议避免换行符和引号
        sanitized = value.replace("\n", " ").replace("\r", " ").replace('"', "'")

        # 限制长度
        if len(sanitized) > 256:
            sanitized = sanitized[:253] + "..."

        return sanitized


# 全局转换器实例
alarm_transformer = AlarmTransformer()
