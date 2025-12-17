"""
OpsGenie API 客户端

直接与 OpsGenie API 交互，推送告警和管理告警状态。
"""

import json
import logging
import time
from typing import List, Optional, Dict, Any

import httpx

from app.models.prometheus import PrometheusAlert, PrometheusSilence
from app.config import OpsGenieConfig, settings

logger = logging.getLogger(__name__)


# Prometheus severity 到 OpsGenie priority 的映射
SEVERITY_TO_PRIORITY = {
    "critical": "P1",
    "error": "P2",
    "warning": "P3",
    "info": "P4",
}


class OpsGenieClient:
    """OpsGenie API 客户端"""

    def __init__(self, config: Optional[OpsGenieConfig] = None):
        """
        初始化客户端

        Args:
            config: OpsGenie 配置
        """
        self.config = config or settings.opsgenie
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """获取 HTTP 客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.timeout),
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Authorization": f"GenieKey {self.config.api_key}",
                    "User-Agent": "zmc-alarm-exporter/1.0"
                },
                # 禁用代理，直接连接 OpsGenie
                trust_env=False
            )
        return self._client

    async def close(self):
        """关闭客户端"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        json_data: Optional[Any] = None
    ) -> httpx.Response:
        """
        带重试的 HTTP 请求

        Args:
            method: HTTP 方法
            url: 请求 URL
            json_data: JSON 数据

        Returns:
            HTTP 响应
        """
        client = await self._get_client()
        last_error = None

        # 手动序列化 JSON，确保中文字符不被转义
        content = None
        if json_data is not None:
            content = json.dumps(json_data, ensure_ascii=False).encode("utf-8")

        for attempt in range(self.config.retry_count):
            try:
                response = await client.request(method, url, content=content)
                return response

            except httpx.TimeoutException as e:
                last_error = e
                logger.warning(f"Request timeout (attempt {attempt + 1}/{self.config.retry_count}): {url}")

            except httpx.ConnectError as e:
                last_error = e
                logger.warning(f"Connection error (attempt {attempt + 1}/{self.config.retry_count}): {url}")

            except Exception as e:
                last_error = e
                logger.error(f"Request error (attempt {attempt + 1}/{self.config.retry_count}): {e}")

            # 等待后重试
            if attempt < self.config.retry_count - 1:
                await self._sleep(self.config.retry_interval / 1000)

        raise last_error or Exception("Request failed after all retries")

    @staticmethod
    async def _sleep(seconds: float):
        """异步睡眠"""
        import asyncio
        await asyncio.sleep(seconds)

    def _convert_to_opsgenie_alert(self, alert: PrometheusAlert) -> Dict[str, Any]:
        """
        将 Prometheus 格式告警转换为 OpsGenie 格式

        Args:
            alert: Prometheus 格式告警

        Returns:
            OpsGenie 格式告警
        """
        labels = alert.labels
        annotations = alert.annotations

        # 构建 alias，用于去重和后续操作（关闭/确认）
        # 优先使用 alarm_id，其次使用 event_id
        alarm_id = labels.get("alarm_id") or labels.get("event_id") or ""
        alias = f"zmc-{alarm_id}" if alarm_id else None

        # 获取优先级
        severity = labels.get("severity", "warning").lower()
        priority = SEVERITY_TO_PRIORITY.get(severity, self.config.default_priority)

        # 构建 message（限制130字符）
        alertname = labels.get("alertname", "Unknown Alert")
        message = alertname[:130] if len(alertname) > 130 else alertname

        # 构建 tags
        tags = ["zmc"]
        if labels.get("alarm_code"):
            tags.append(f"alarm_code:{labels['alarm_code']}")
        if labels.get("source"):
            tags.append(labels["source"])
        if severity:
            tags.append(severity)

        # 构建 details（合并 labels 和 annotations）
        details = {}
        for key, value in labels.items():
            if key not in ("alertname",):  # 排除已在 message 中使用的字段
                details[f"label_{key}"] = str(value)
        for key, value in annotations.items():
            details[f"annotation_{key}"] = str(value)

        # 构建 OpsGenie 告警
        opsgenie_alert = {
            "message": message,
            "priority": priority,
            "tags": tags[:20],  # OpsGenie 限制最多20个标签
            "details": details,
            "source": "zmc-alarm-exporter",
        }

        # 添加可选字段
        if alias:
            opsgenie_alert["alias"] = alias

        if annotations.get("description"):
            # OpsGenie description 限制15000字符
            desc = annotations["description"]
            opsgenie_alert["description"] = desc[:15000] if len(desc) > 15000 else desc

        # 添加 responders（团队）
        if self.config.default_team:
            opsgenie_alert["responders"] = [
                {"name": self.config.default_team, "type": "team"}
            ]

        return opsgenie_alert

    def _get_alert_alias(self, alert: PrometheusAlert) -> Optional[str]:
        """获取告警的 alias"""
        labels = alert.labels
        alarm_id = labels.get("alarm_id") or labels.get("event_id") or ""
        return f"zmc-{alarm_id}" if alarm_id else None

    # ========== 告警管理 ==========

    async def push_alerts(self, alerts: List[PrometheusAlert]) -> Dict[str, Any]:
        """
        推送告警到 OpsGenie

        注意：OpsGenie 不支持批量推送，需要逐个推送

        Args:
            alerts: 告警列表

        Returns:
            推送结果
        """
        if not alerts:
            return {"success": True, "count": 0, "message": "No alerts to push"}

        url = self.config.alerts_url
        success_count = 0
        error_count = 0
        errors = []

        logger.info(f"Pushing {len(alerts)} alerts to OpsGenie")

        start_time = time.time()

        for alert in alerts:
            try:
                # 检查是否是 resolved 告警
                is_resolved = alert.endsAt is not None

                if is_resolved:
                    # 关闭告警
                    result = await self._close_alert(alert)
                else:
                    # 创建告警
                    result = await self._create_alert(alert)

                if result["success"]:
                    success_count += 1
                else:
                    error_count += 1
                    errors.append(result.get("error"))

            except Exception as e:
                error_count += 1
                errors.append(str(e))
                logger.error(f"Failed to push alert: {e}")

        duration_ms = int((time.time() - start_time) * 1000)

        result = {
            "success": error_count == 0,
            "count": len(alerts),
            "success_count": success_count,
            "error_count": error_count,
            "duration_ms": duration_ms,
        }

        if errors:
            result["errors"] = errors[:10]  # 只保留前10个错误

        if error_count == 0:
            logger.info(f"Successfully pushed {success_count} alerts to OpsGenie (duration: {duration_ms}ms)")
        else:
            logger.warning(f"Pushed alerts with errors: {success_count} success, {error_count} failed")

        return result

    async def _create_alert(self, alert: PrometheusAlert) -> Dict[str, Any]:
        """创建单个告警"""
        url = self.config.alerts_url
        payload = self._convert_to_opsgenie_alert(alert)

        logger.debug(f"Creating OpsGenie alert: {payload.get('alias')}")

        try:
            response = await self._request_with_retry("POST", url, json_data=payload)

            # OpsGenie 返回 202 表示请求已接受
            if response.status_code in (200, 201, 202):
                return {
                    "success": True,
                    "status_code": response.status_code,
                    "request_id": response.json().get("requestId")
                }
            else:
                error_msg = f"Create alert failed with status {response.status_code}: {response.text}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "error": error_msg
                }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _close_alert(self, alert: PrometheusAlert) -> Dict[str, Any]:
        """关闭告警"""
        alias = self._get_alert_alias(alert)

        if not alias:
            logger.warning("Cannot close alert without alias")
            return {"success": False, "error": "Missing alias"}

        url = f"{self.config.alerts_url}/{alias}/close?identifierType=alias"

        logger.debug(f"Closing OpsGenie alert: {alias}")

        try:
            payload = {
                "source": "zmc-alarm-exporter",
                "note": "Alert resolved by ZMC"
            }

            response = await self._request_with_retry("POST", url, json_data=payload)

            if response.status_code in (200, 202):
                return {
                    "success": True,
                    "status_code": response.status_code
                }
            elif response.status_code == 404:
                # 告警不存在，视为成功（可能已被手动关闭）
                logger.info(f"Alert {alias} not found in OpsGenie, treating as already closed")
                return {
                    "success": True,
                    "status_code": response.status_code,
                    "note": "Alert not found, already closed"
                }
            else:
                error_msg = f"Close alert failed with status {response.status_code}: {response.text}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "error": error_msg
                }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def push_single_alert(self, alert: PrometheusAlert) -> Dict[str, Any]:
        """
        推送单个告警

        Args:
            alert: 告警对象

        Returns:
            推送结果
        """
        return await self.push_alerts([alert])

    # ========== 静默管理 ==========
    # OpsGenie 没有 Alertmanager 风格的 Silence API
    # 使用 acknowledge 来模拟静默效果

    async def create_silence(self, silence: PrometheusSilence) -> Dict[str, Any]:
        """
        创建静默规则（使用 acknowledge 实现）

        在 OpsGenie 中，acknowledge 一个告警会暂停该告警的通知，
        直到告警状态变更或超时。

        Args:
            silence: 静默规则对象

        Returns:
            创建结果
        """
        # 从 matchers 中提取 event_id 或 alarm_id
        event_id = None
        for matcher in silence.matchers:
            if matcher.name in ("event_id", "alarm_id"):
                event_id = matcher.value
                break

        if not event_id:
            logger.warning("Cannot create silence without event_id or alarm_id")
            return {"success": False, "error": "Missing event_id or alarm_id in matchers"}

        alias = f"zmc-{event_id}"
        url = f"{self.config.alerts_url}/{alias}/acknowledge?identifierType=alias"

        logger.info(f"Acknowledging OpsGenie alert (as silence): {alias}")

        try:
            payload = {
                "source": "zmc-alarm-exporter",
                "note": silence.comment or "Silenced by ZMC"
            }

            response = await self._request_with_retry("POST", url, json_data=payload)

            if response.status_code in (200, 202):
                # 使用 alias 作为 silence_id 返回
                return {
                    "success": True,
                    "silence_id": alias,
                    "status_code": response.status_code
                }
            elif response.status_code == 404:
                logger.info(f"Alert {alias} not found, cannot acknowledge")
                return {
                    "success": True,
                    "silence_id": alias,
                    "note": "Alert not found"
                }
            else:
                error_msg = f"Acknowledge failed with status {response.status_code}: {response.text}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "error": error_msg
                }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def delete_silence(self, silence_id: str) -> Dict[str, Any]:
        """
        删除静默规则

        在 OpsGenie 中，没有直接的取消 acknowledge 操作。
        我们通过关闭告警来达到类似效果。

        Args:
            silence_id: 静默规则 ID（实际是 alias）

        Returns:
            删除结果
        """
        # silence_id 实际是 alias
        url = f"{self.config.alerts_url}/{silence_id}/close?identifierType=alias"

        logger.info(f"Closing OpsGenie alert (delete silence): {silence_id}")

        try:
            payload = {
                "source": "zmc-alarm-exporter",
                "note": "Silence removed by ZMC"
            }

            response = await self._request_with_retry("POST", url, json_data=payload)

            if response.status_code in (200, 202, 404):
                return {
                    "success": True,
                    "silence_id": silence_id,
                    "status_code": response.status_code
                }
            else:
                error_msg = f"Delete silence failed with status {response.status_code}: {response.text}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "silence_id": silence_id,
                    "status_code": response.status_code,
                    "error": error_msg
                }

        except Exception as e:
            return {"success": False, "silence_id": silence_id, "error": str(e)}

    async def get_silences(self) -> List[Dict[str, Any]]:
        """
        获取所有静默规则

        OpsGenie 没有单独的 silence 概念，这里返回空列表。

        Returns:
            静默规则列表（空）
        """
        logger.debug("OpsGenie does not support listing silences")
        return []

    # ========== 状态检查 ==========

    async def get_status(self) -> Optional[Dict[str, Any]]:
        """
        获取 OpsGenie 状态

        Returns:
            状态信息
        """
        # 使用 heartbeats API 来检查连接状态
        url = f"{self.config.api_url}/v2/heartbeats"

        try:
            response = await self._request_with_retry("GET", url)

            if response.status_code == 200:
                return {
                    "connected": True,
                    "api_url": self.config.api_url
                }
            else:
                return {
                    "connected": False,
                    "status_code": response.status_code
                }

        except Exception as e:
            logger.error(f"Get OpsGenie status failed: {e}")
            return {
                "connected": False,
                "error": str(e)
            }

    async def health_check(self) -> bool:
        """
        健康检查

        Returns:
            是否健康
        """
        try:
            # 通过获取 account info 来验证 API key 和连接
            url = f"{self.config.api_url}/v2/account"
            client = await self._get_client()
            response = await client.get(url)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"OpsGenie health check failed: {e}")
            return False

    async def get_alerts(self) -> List[Dict[str, Any]]:
        """
        获取当前活跃告警

        Returns:
            告警列表
        """
        url = f"{self.config.alerts_url}?query=status:open"

        try:
            response = await self._request_with_retry("GET", url)

            if response.status_code == 200:
                data = response.json()
                return data.get("data", [])
            else:
                logger.error(f"Get OpsGenie alerts failed: {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"Get OpsGenie alerts failed: {e}")
            return []


# 全局客户端实例
opsgenie_client = OpsGenieClient()
