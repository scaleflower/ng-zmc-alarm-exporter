"""
告警客户端工厂

根据配置返回对应的告警客户端（Alertmanager 或 OpsGenie）。
"""

import logging
from typing import Protocol, List, Dict, Any, Optional, Union, runtime_checkable

from app.config import settings, AlertmanagerConfig, OpsGenieConfig
from app.models.prometheus import PrometheusAlert, PrometheusSilence

logger = logging.getLogger(__name__)


@runtime_checkable
class AlertClient(Protocol):
    """
    告警客户端协议

    定义告警客户端必须实现的接口，用于支持不同的后端（Alertmanager/OpsGenie）。
    """

    @property
    def config(self) -> Union[AlertmanagerConfig, OpsGenieConfig]:
        """获取客户端配置"""
        ...

    async def push_alerts(self, alerts: List[PrometheusAlert]) -> Dict[str, Any]:
        """推送告警列表"""
        ...

    async def push_single_alert(self, alert: PrometheusAlert) -> Dict[str, Any]:
        """推送单个告警"""
        ...

    async def create_silence(self, silence: PrometheusSilence) -> Dict[str, Any]:
        """创建静默规则"""
        ...

    async def delete_silence(self, silence_id: str) -> Dict[str, Any]:
        """删除静默规则"""
        ...

    async def get_silences(self) -> List[Dict[str, Any]]:
        """获取所有静默规则"""
        ...

    async def health_check(self) -> bool:
        """健康检查"""
        ...

    async def get_alerts(self) -> List[Dict[str, Any]]:
        """获取当前活跃告警"""
        ...

    async def get_status(self) -> Optional[Dict[str, Any]]:
        """获取服务状态"""
        ...

    async def close(self) -> None:
        """关闭客户端"""
        ...


# 缓存客户端实例
_alert_client: Optional[AlertClient] = None


def get_alert_client() -> AlertClient:
    """
    根据配置返回对应的告警客户端

    优先级:
    1. 如果 OPSGENIE_ENABLED=true 且 ALERTMANAGER_ENABLED=false → 使用 OpsGenie
    2. 如果 ALERTMANAGER_ENABLED=true → 使用 Alertmanager
    3. 否则根据 INTEGRATION_MODE 决定

    Returns:
        AlertClient: 告警客户端实例
    """
    global _alert_client

    if _alert_client is not None:
        return _alert_client

    # 根据 enabled 标志自动选择模式
    opsgenie_enabled = settings.opsgenie.enabled
    alertmanager_enabled = settings.alertmanager.enabled

    # 如果 OpsGenie 启用且 Alertmanager 禁用，使用 OpsGenie
    if opsgenie_enabled and not alertmanager_enabled:
        logger.info("Using OpsGenie direct integration mode (OPSGENIE_ENABLED=true, ALERTMANAGER_ENABLED=false)")
        from app.services.opsgenie_client import OpsGenieClient
        _alert_client = OpsGenieClient()
        return _alert_client

    # 如果 Alertmanager 启用，使用 Alertmanager
    if alertmanager_enabled:
        logger.info("Using Alertmanager integration mode (ALERTMANAGER_ENABLED=true)")
        from app.services.alertmanager_client import AlertmanagerClient
        _alert_client = AlertmanagerClient()
        return _alert_client

    # 回退到 INTEGRATION_MODE 配置
    mode = settings.integration.mode.lower()

    if mode == "opsgenie":
        logger.info("Using OpsGenie direct integration mode (INTEGRATION_MODE=opsgenie)")
        from app.services.opsgenie_client import OpsGenieClient
        _alert_client = OpsGenieClient()
    else:
        # 默认使用 Alertmanager
        if mode != "alertmanager":
            logger.warning(f"Unknown integration mode '{mode}', falling back to alertmanager")
        logger.info("Using Alertmanager integration mode")
        from app.services.alertmanager_client import AlertmanagerClient
        _alert_client = AlertmanagerClient()

    return _alert_client


def reset_alert_client() -> None:
    """
    重置客户端实例

    用于测试或配置变更后重新初始化。
    """
    global _alert_client
    _alert_client = None
    logger.info("Alert client has been reset")


def get_integration_mode() -> str:
    """
    获取当前集成模式

    优先级:
    1. 如果 OPSGENIE_ENABLED=true 且 ALERTMANAGER_ENABLED=false → 'opsgenie'
    2. 如果 ALERTMANAGER_ENABLED=true → 'alertmanager'
    3. 否则根据 INTEGRATION_MODE 决定

    Returns:
        str: 'alertmanager' 或 'opsgenie'
    """
    opsgenie_enabled = settings.opsgenie.enabled
    alertmanager_enabled = settings.alertmanager.enabled

    # 如果 OpsGenie 启用且 Alertmanager 禁用，使用 OpsGenie
    if opsgenie_enabled and not alertmanager_enabled:
        return "opsgenie"

    # 如果 Alertmanager 启用，使用 Alertmanager
    if alertmanager_enabled:
        return "alertmanager"

    # 回退到 INTEGRATION_MODE 配置
    return settings.integration.mode.lower()


def is_opsgenie_mode() -> bool:
    """
    检查是否为 OpsGenie 直连模式

    Returns:
        bool: True 如果是 OpsGenie 模式
    """
    return get_integration_mode() == "opsgenie"


def is_alertmanager_mode() -> bool:
    """
    检查是否为 Alertmanager 模式

    Returns:
        bool: True 如果是 Alertmanager 模式
    """
    return get_integration_mode() == "alertmanager"
