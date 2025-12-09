"""
Prometheus/Alertmanager 数据模型

定义符合 Prometheus Alertmanager API 规范的数据结构。
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class PrometheusAlert(BaseModel):
    """
    Prometheus Alertmanager 告警模型

    符合 Alertmanager API v2 规范:
    https://prometheus.io/docs/alerting/latest/clients/
    """

    labels: Dict[str, str] = Field(
        ...,
        description="告警标签，用于匹配和分组"
    )
    annotations: Dict[str, str] = Field(
        default_factory=dict,
        description="告警注解，用于展示详细信息"
    )
    startsAt: Optional[str] = Field(
        None,
        description="告警开始时间 (RFC3339格式)"
    )
    endsAt: Optional[str] = Field(
        None,
        description="告警结束时间 (RFC3339格式)，设置后表示告警已恢复"
    )
    generatorURL: Optional[str] = Field(
        None,
        description="告警来源URL"
    )

    class Config:
        populate_by_name = True

    @classmethod
    def create_firing(
        cls,
        alertname: str,
        instance: str,
        severity: str,
        starts_at: datetime,
        labels: Optional[Dict[str, str]] = None,
        annotations: Optional[Dict[str, str]] = None,
        generator_url: Optional[str] = None
    ) -> "PrometheusAlert":
        """
        创建一个活跃状态的告警

        Args:
            alertname: 告警名称
            instance: 实例标识(通常是IP或主机名)
            severity: 告警级别
            starts_at: 告警开始时间
            labels: 额外标签
            annotations: 告警注解
            generator_url: 来源URL
        """
        alert_labels = {
            "alertname": alertname,
            "instance": instance,
            "severity": severity,
        }
        if labels:
            alert_labels.update(labels)

        return cls(
            labels=alert_labels,
            annotations=annotations or {},
            startsAt=cls._format_time(starts_at),
            endsAt=None,  # 活跃告警不设置结束时间
            generatorURL=generator_url
        )

    @classmethod
    def create_resolved(
        cls,
        alertname: str,
        instance: str,
        severity: str,
        starts_at: datetime,
        ends_at: datetime,
        labels: Optional[Dict[str, str]] = None,
        annotations: Optional[Dict[str, str]] = None,
        generator_url: Optional[str] = None
    ) -> "PrometheusAlert":
        """
        创建一个已恢复的告警

        Args:
            alertname: 告警名称
            instance: 实例标识
            severity: 告警级别
            starts_at: 告警开始时间
            ends_at: 告警结束时间
            labels: 额外标签
            annotations: 告警注解
            generator_url: 来源URL
        """
        alert_labels = {
            "alertname": alertname,
            "instance": instance,
            "severity": severity,
        }
        if labels:
            alert_labels.update(labels)

        return cls(
            labels=alert_labels,
            annotations=annotations or {},
            startsAt=cls._format_time(starts_at),
            endsAt=cls._format_time(ends_at),  # 设置结束时间表示已恢复
            generatorURL=generator_url
        )

    @staticmethod
    def _format_time(dt: datetime) -> str:
        """格式化时间为RFC3339格式"""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()

    def to_dict(self) -> dict:
        """转换为API请求格式的字典"""
        result = {
            "labels": self.labels,
            "annotations": self.annotations,
        }
        if self.startsAt:
            result["startsAt"] = self.startsAt
        if self.endsAt:
            result["endsAt"] = self.endsAt
        if self.generatorURL:
            result["generatorURL"] = self.generatorURL
        return result


class SilenceMatcher(BaseModel):
    """静默规则匹配器"""

    name: str = Field(..., description="标签名")
    value: str = Field(..., description="标签值")
    isRegex: bool = Field(default=False, description="是否正则匹配")
    isEqual: bool = Field(default=True, description="是否等值匹配")


class PrometheusSilence(BaseModel):
    """
    Prometheus Alertmanager 静默规则模型

    符合 Alertmanager API v2 silences 规范
    """

    matchers: List[SilenceMatcher] = Field(
        ...,
        description="匹配器列表，用于匹配要静默的告警"
    )
    startsAt: str = Field(
        ...,
        description="静默开始时间 (RFC3339格式)"
    )
    endsAt: str = Field(
        ...,
        description="静默结束时间 (RFC3339格式)"
    )
    createdBy: str = Field(
        ...,
        description="创建者标识"
    )
    comment: str = Field(
        ...,
        description="静默注释/原因"
    )
    id: Optional[str] = Field(
        None,
        description="静默规则ID (由Alertmanager生成)"
    )

    @classmethod
    def create_for_alarm(
        cls,
        event_id: int,
        alarm_code: int,
        instance: str,
        starts_at: datetime,
        ends_at: datetime,
        created_by: str = "zmc-alarm-exporter",
        comment: str = "Silenced by ZMC"
    ) -> "PrometheusSilence":
        """
        为指定告警创建静默规则

        Args:
            event_id: 告警事件ID
            alarm_code: 告警码
            instance: 实例标识
            starts_at: 静默开始时间
            ends_at: 静默结束时间
            created_by: 创建者
            comment: 注释
        """
        # 使用 event_id 作为精确匹配条件
        matchers = [
            SilenceMatcher(name="event_id", value=str(event_id), isRegex=False, isEqual=True),
        ]

        return cls(
            matchers=matchers,
            startsAt=cls._format_time(starts_at),
            endsAt=cls._format_time(ends_at),
            createdBy=created_by,
            comment=comment
        )

    @classmethod
    def create_by_labels(
        cls,
        labels: Dict[str, str],
        starts_at: datetime,
        ends_at: datetime,
        created_by: str = "zmc-alarm-exporter",
        comment: str = "Silenced by ZMC"
    ) -> "PrometheusSilence":
        """
        根据标签创建静默规则

        Args:
            labels: 要匹配的标签
            starts_at: 静默开始时间
            ends_at: 静默结束时间
            created_by: 创建者
            comment: 注释
        """
        matchers = [
            SilenceMatcher(name=k, value=v, isRegex=False, isEqual=True)
            for k, v in labels.items()
        ]

        return cls(
            matchers=matchers,
            startsAt=cls._format_time(starts_at),
            endsAt=cls._format_time(ends_at),
            createdBy=created_by,
            comment=comment
        )

    @staticmethod
    def _format_time(dt: datetime) -> str:
        """格式化时间为RFC3339格式"""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()

    def to_dict(self) -> dict:
        """转换为API请求格式的字典"""
        return {
            "matchers": [m.model_dump() for m in self.matchers],
            "startsAt": self.startsAt,
            "endsAt": self.endsAt,
            "createdBy": self.createdBy,
            "comment": self.comment,
        }


class AlertmanagerStatus(BaseModel):
    """Alertmanager 状态响应模型"""

    cluster: Optional[dict] = Field(None, description="集群信息")
    versionInfo: Optional[dict] = Field(None, description="版本信息")
    config: Optional[dict] = Field(None, description="配置信息")
    uptime: Optional[str] = Field(None, description="运行时间")


class AlertGroup(BaseModel):
    """告警分组模型"""

    labels: Dict[str, str] = Field(default_factory=dict, description="分组标签")
    receiver: Optional[str] = Field(None, description="接收器名称")
    alerts: List[PrometheusAlert] = Field(default_factory=list, description="告警列表")
