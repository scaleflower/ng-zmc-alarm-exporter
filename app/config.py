"""
配置管理模块

支持从环境变量、配置文件和数据库加载配置。
"""

import os
from pathlib import Path
from typing import Optional
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_version() -> str:
    """
    从 VERSION 文件读取版本号

    查找顺序:
    1. 项目根目录 (开发环境)
    2. /app 目录 (Docker 容器)
    3. 当前工作目录
    """
    search_paths = [
        Path(__file__).parent.parent / "VERSION",  # 项目根目录
        Path("/app/VERSION"),                       # Docker 容器
        Path("VERSION"),                            # 当前目录
    ]

    for version_file in search_paths:
        if version_file.exists():
            return version_file.read_text().strip()

    return "0.0.0"  # 默认版本号


# 应用版本号 (从 VERSION 文件读取)
APP_VERSION = get_version()


class OracleConfig(BaseSettings):
    """ZMC Oracle 数据库连接配置"""

    model_config = SettingsConfigDict(
        env_prefix="ZMC_ORACLE_",
        env_file=".env",
        extra="ignore"
    )

    host: str = Field(default="localhost", description="Oracle数据库主机地址")
    port: int = Field(default=1521, description="Oracle数据库端口")
    service_name: str = Field(default="ORCL", description="Oracle服务名")
    username: str = Field(default="zmc", description="数据库用户名")
    password: str = Field(default="", description="数据库密码")
    pool_min: int = Field(default=2, description="连接池最小连接数")
    pool_max: int = Field(default=10, description="连接池最大连接数")
    timeout: int = Field(default=30, description="连接超时(秒)")
    # Oracle Instant Client 库路径，用于启用 thick 模式
    # 如果数据库使用旧版密码加密(DPY-3015错误)，需要设置此路径
    client_lib_dir: Optional[str] = Field(default=None, description="Oracle Instant Client库路径")

    @property
    def dsn(self) -> str:
        """生成Oracle DSN连接字符串"""
        return f"{self.host}:{self.port}/{self.service_name}"

    @property
    def connection_string(self) -> str:
        """生成完整连接字符串"""
        return f"{self.username}/{self.password}@{self.dsn}"


class AlertmanagerConfig(BaseSettings):
    """Alertmanager 连接配置"""

    model_config = SettingsConfigDict(
        env_prefix="ALERTMANAGER_",
        env_file=".env",
        extra="ignore"
    )

    enabled: bool = Field(default=True, description="是否启用Alertmanager集成")
    url: str = Field(default="http://localhost:9093", description="Alertmanager API地址")
    api_version: str = Field(default="v2", description="API版本")
    auth_enabled: bool = Field(default=False, description="是否启用认证")
    username: Optional[str] = Field(default=None, description="Basic Auth用户名")
    password: Optional[str] = Field(default=None, description="Basic Auth密码")
    timeout: int = Field(default=30, description="请求超时(秒)")
    retry_count: int = Field(default=3, description="重试次数")
    retry_interval: int = Field(default=1000, description="重试间隔(毫秒)")

    @property
    def alerts_url(self) -> str:
        """告警API端点"""
        return f"{self.url}/api/{self.api_version}/alerts"

    @property
    def silences_url(self) -> str:
        """静默API端点"""
        return f"{self.url}/api/{self.api_version}/silences"

    @property
    def status_url(self) -> str:
        """状态API端点"""
        return f"{self.url}/api/{self.api_version}/status"


class OpsGenieConfig(BaseSettings):
    """OpsGenie 直连配置"""

    model_config = SettingsConfigDict(
        env_prefix="OPSGENIE_",
        env_file=".env",
        extra="ignore"
    )

    enabled: bool = Field(default=False, description="是否启用OpsGenie直连")
    api_url: str = Field(default="https://api.opsgenie.com", description="API地址")
    api_key: str = Field(default="", description="API Key")
    default_team: Optional[str] = Field(default=None, description="默认团队")
    default_priority: str = Field(default="P3", description="默认优先级 (P1-P5)")
    timeout: int = Field(default=30, description="请求超时(秒)")
    retry_count: int = Field(default=3, description="重试次数")
    retry_interval: int = Field(default=1000, description="重试间隔(毫秒)")

    @property
    def alerts_url(self) -> str:
        """告警API端点"""
        return f"{self.api_url}/v2/alerts"

    @property
    def heartbeat_url(self) -> str:
        """心跳API端点"""
        return f"{self.api_url}/v2/heartbeats"


class IntegrationConfig(BaseSettings):
    """集成模式配置"""

    model_config = SettingsConfigDict(
        env_prefix="INTEGRATION_",
        env_file=".env",
        extra="ignore"
    )

    mode: str = Field(
        default="alertmanager",
        description="集成模式: alertmanager (通过Alertmanager转发) 或 opsgenie (直连OpsGenie)"
    )


class SyncServiceConfig(BaseSettings):
    """同步服务配置"""

    model_config = SettingsConfigDict(
        env_prefix="SYNC_",
        env_file=".env",
        extra="ignore"
    )

    enabled: bool = Field(default=True, description="是否启用同步服务")
    scan_interval: int = Field(default=60, description="扫描间隔(秒)")
    heartbeat_enabled: bool = Field(
        default=False,
        description="是否启用心跳保活机制。关闭后告警只推送一次，状态变更时才再次推送"
    )
    heartbeat_interval: int = Field(default=120, description="心跳间隔(秒)，仅在heartbeat_enabled=True时生效")
    batch_size: int = Field(default=100, description="批处理大小")
    sync_on_startup: bool = Field(default=True, description="启动时同步历史告警")
    history_hours: int = Field(default=24, description="历史回溯时长(小时)")
    worker_threads: int = Field(default=4, description="工作线程数")

    # 告警级别过滤配置
    # ZMC告警级别: 1-严重, 2-重要, 3-次要, 4-警告
    # 示例: "1,2" 表示只同步严重和重要级别的告警
    # 示例: "1,2,3,4" 或留空表示同步所有级别
    alarm_levels: str = Field(
        default="1,2,3,4",
        description="要同步的ZMC告警级别，逗号分隔，如: 1,2 表示只同步严重和重要告警"
    )

    # Prometheus severity 过滤配置
    # 示例: "critical,error" 表示只同步映射后为 critical 或 error 的告警
    # 留空表示同步所有级别
    severity_filter: str = Field(
        default="",
        description="要同步的Prometheus severity，逗号分隔，如: critical,error"
    )

    def get_allowed_zmc_levels(self) -> set:
        """获取允许同步的ZMC告警级别集合"""
        if not self.alarm_levels or self.alarm_levels.strip() == "":
            return {"0", "1", "2", "3", "4"}  # 所有级别
        return set(level.strip() for level in self.alarm_levels.split(",") if level.strip())

    def get_allowed_severities(self) -> set:
        """获取允许同步的Prometheus severity集合"""
        if not self.severity_filter or self.severity_filter.strip() == "":
            return set()  # 空集表示不过滤
        return set(s.strip().lower() for s in self.severity_filter.split(",") if s.strip())


class SilenceConfig(BaseSettings):
    """静默策略配置"""

    model_config = SettingsConfigDict(
        env_prefix="SILENCE_",
        env_file=".env",
        extra="ignore"
    )

    use_silence_api: bool = Field(default=True, description="使用Silence API处理屏蔽")
    default_duration_hours: int = Field(default=24, description="默认静默时长(小时)")
    auto_remove_on_clear: bool = Field(default=True, description="告警清除时自动移除静默")
    comment_template: str = Field(
        default="Silenced by ZMC at {time}. Operator: {operator}",
        description="静默注释模板"
    )


class SeverityMapping(BaseSettings):
    """告警级别映射配置"""

    model_config = SettingsConfigDict(
        env_prefix="SEVERITY_",
        env_file=".env",
        extra="ignore"
    )

    level_0: str = Field(default="warning", description="级别0(未定义)映射")
    level_1: str = Field(default="critical", description="级别1(严重)映射")
    level_2: str = Field(default="error", description="级别2(重要)映射")
    level_3: str = Field(default="warning", description="级别3(次要)映射")
    level_4: str = Field(default="info", description="级别4(警告)映射")

    def get_severity(self, zmc_level: str) -> str:
        """将ZMC告警级别转换为Prometheus severity"""
        mapping = {
            "0": self.level_0,
            "1": self.level_1,
            "2": self.level_2,
            "3": self.level_3,
            "4": self.level_4,
        }
        return mapping.get(str(zmc_level), self.level_3)


class StatusMapping(BaseSettings):
    """状态映射配置"""

    model_config = SettingsConfigDict(
        env_prefix="STATUS_",
        env_file=".env",
        extra="ignore"
    )

    state_u: str = Field(default="FIRING", description="未确认→状态")
    state_a: str = Field(default="RESOLVED", description="自动恢复→状态")
    state_m: str = Field(default="SILENCED", description="手工清除→状态")
    state_c: str = Field(default="RESOLVED", description="已确认→状态")

    def get_sync_status(self, zmc_state: str) -> str:
        """将ZMC告警状态转换为同步状态"""
        mapping = {
            "U": self.state_u,
            "A": self.state_a,
            "M": self.state_m,
            "C": self.state_c,
        }
        return mapping.get(zmc_state, self.state_u)


class StaticLabels(BaseSettings):
    """Prometheus静态标签配置"""

    model_config = SettingsConfigDict(
        env_prefix="LABEL_",
        env_file=".env",
        extra="ignore"
    )

    source: str = Field(default="BSS_OSS_L1", description="告警来源标识，可通过 LABEL_SOURCE 环境变量配置")
    cluster: Optional[str] = Field(default=None, description="集群名称")
    datacenter: Optional[str] = Field(default=None, description="数据中心")

    def to_dict(self) -> dict:
        """转换为标签字典，排除None值"""
        labels = {"source": self.source}
        if self.cluster:
            labels["cluster"] = self.cluster
        if self.datacenter:
            labels["datacenter"] = self.datacenter
        return labels


class LoggingConfig(BaseSettings):
    """日志配置"""

    model_config = SettingsConfigDict(
        env_prefix="LOG_",
        env_file=".env",
        extra="ignore"
    )

    level: str = Field(default="INFO", description="日志级别")
    retention_days: int = Field(default=30, description="日志保留天数")
    log_request_body: bool = Field(default=True, description="记录请求体")
    log_response_body: bool = Field(default=True, description="记录响应体")
    format: str = Field(default="json", description="日志格式: json/text")


class ServerConfig(BaseSettings):
    """HTTP服务器配置"""

    model_config = SettingsConfigDict(
        env_prefix="SERVER_",
        env_file=".env",
        extra="ignore"
    )

    host: str = Field(default="0.0.0.0", description="监听地址")
    port: int = Field(default=8080, description="监听端口")
    workers: int = Field(default=1, description="工作进程数")
    reload: bool = Field(default=False, description="开发模式热重载")


class Settings(BaseSettings):
    """应用总配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )

    # 应用信息
    app_name: str = Field(default="ZMC Alarm Exporter", description="应用名称")
    app_version: str = Field(default_factory=lambda: APP_VERSION, description="应用版本")
    debug: bool = Field(default=False, description="调试模式")

    # 子配置
    oracle: OracleConfig = Field(default_factory=OracleConfig)
    alertmanager: AlertmanagerConfig = Field(default_factory=AlertmanagerConfig)
    opsgenie: OpsGenieConfig = Field(default_factory=OpsGenieConfig)
    integration: IntegrationConfig = Field(default_factory=IntegrationConfig)
    sync: SyncServiceConfig = Field(default_factory=SyncServiceConfig)
    silence: SilenceConfig = Field(default_factory=SilenceConfig)
    severity: SeverityMapping = Field(default_factory=SeverityMapping)
    status: StatusMapping = Field(default_factory=StatusMapping)
    labels: StaticLabels = Field(default_factory=StaticLabels)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)


@lru_cache()
def get_settings() -> Settings:
    """获取应用配置(带缓存)"""
    return Settings()


# 配置单例
settings = get_settings()
