"""
Alertmanager API 客户端

与 Prometheus Alertmanager 进行交互，推送告警和管理静默规则。
"""

import json
import logging
import time
from typing import List, Optional, Dict, Any

import httpx

from app.models.prometheus import PrometheusAlert, PrometheusSilence
from app.config import AlertmanagerConfig, settings

logger = logging.getLogger(__name__)


class AlertmanagerClient:
    """Alertmanager API 客户端"""

    def __init__(self, config: Optional[AlertmanagerConfig] = None):
        """
        初始化客户端

        Args:
            config: Alertmanager 配置
        """
        self.config = config or settings.alertmanager
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """获取 HTTP 客户端"""
        if self._client is None or self._client.is_closed:
            # 构建认证信息
            auth = None
            if self.config.auth_enabled and self.config.username and self.config.password:
                auth = (self.config.username, self.config.password)

            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.timeout),
                auth=auth,
                headers={
                    # 明确指定 charset=utf-8 以确保中文字符正确传输
                    "Content-Type": "application/json; charset=utf-8",
                    "User-Agent": "zmc-alarm-exporter/1.0"
                },
                # 禁用代理，直接连接 Alertmanager（不从环境变量读取代理）
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
        # 使用 ensure_ascii=False 保留原始 Unicode 字符
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

    # ========== 告警管理 ==========

    async def push_alerts(self, alerts: List[PrometheusAlert]) -> Dict[str, Any]:
        """
        推送告警到 Alertmanager

        Args:
            alerts: 告警列表

        Returns:
            推送结果
        """
        if not alerts:
            return {"success": True, "count": 0, "message": "No alerts to push"}

        url = self.config.alerts_url
        payload = [alert.to_dict() for alert in alerts]

        logger.info(f"Pushing {len(alerts)} alerts to Alertmanager: {url}")
        logger.debug(f"Alert payload: {payload}")

        start_time = time.time()

        try:
            response = await self._request_with_retry("POST", url, json_data=payload)
            duration_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                logger.info(f"Successfully pushed {len(alerts)} alerts (duration: {duration_ms}ms)")
                return {
                    "success": True,
                    "count": len(alerts),
                    "status_code": response.status_code,
                    "duration_ms": duration_ms
                }
            else:
                error_msg = f"Push failed with status {response.status_code}: {response.text}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "count": len(alerts),
                    "status_code": response.status_code,
                    "error": error_msg,
                    "duration_ms": duration_ms
                }

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = f"Push failed with exception: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "count": len(alerts),
                "error": error_msg,
                "duration_ms": duration_ms
            }

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

    async def create_silence(self, silence: PrometheusSilence) -> Dict[str, Any]:
        """
        创建静默规则

        Args:
            silence: 静默规则对象

        Returns:
            创建结果，包含 silence_id
        """
        url = self.config.silences_url
        payload = silence.to_dict()

        logger.info(f"Creating silence: {url}")
        logger.debug(f"Silence payload: {payload}")

        start_time = time.time()

        try:
            response = await self._request_with_retry("POST", url, json_data=payload)
            duration_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                result = response.json()
                silence_id = result.get("silenceID")
                logger.info(f"Successfully created silence: {silence_id} (duration: {duration_ms}ms)")
                return {
                    "success": True,
                    "silence_id": silence_id,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms
                }
            else:
                error_msg = f"Create silence failed with status {response.status_code}: {response.text}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "error": error_msg,
                    "duration_ms": duration_ms
                }

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = f"Create silence failed with exception: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "duration_ms": duration_ms
            }

    async def delete_silence(self, silence_id: str) -> Dict[str, Any]:
        """
        删除静默规则

        Args:
            silence_id: 静默规则 ID

        Returns:
            删除结果
        """
        url = f"{self.config.silences_url}/{silence_id}"

        logger.info(f"Deleting silence: {silence_id}")

        start_time = time.time()

        try:
            response = await self._request_with_retry("DELETE", url)
            duration_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                logger.info(f"Successfully deleted silence: {silence_id} (duration: {duration_ms}ms)")
                return {
                    "success": True,
                    "silence_id": silence_id,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms
                }
            else:
                error_msg = f"Delete silence failed with status {response.status_code}: {response.text}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "silence_id": silence_id,
                    "status_code": response.status_code,
                    "error": error_msg,
                    "duration_ms": duration_ms
                }

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = f"Delete silence failed with exception: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "silence_id": silence_id,
                "error": error_msg,
                "duration_ms": duration_ms
            }

    async def get_silences(self) -> List[Dict[str, Any]]:
        """
        获取所有静默规则

        Returns:
            静默规则列表
        """
        url = self.config.silences_url

        try:
            response = await self._request_with_retry("GET", url)

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Get silences failed: {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"Get silences failed: {e}")
            return []

    # ========== 状态检查 ==========

    async def get_status(self) -> Optional[Dict[str, Any]]:
        """
        获取 Alertmanager 状态

        Returns:
            状态信息
        """
        url = self.config.status_url

        try:
            response = await self._request_with_retry("GET", url)

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Get status failed: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Get status failed: {e}")
            return None

    async def health_check(self) -> bool:
        """
        健康检查

        Returns:
            是否健康
        """
        try:
            # 使用 /-/healthy 端点检查健康状态
            url = f"{self.config.url}/-/healthy"
            client = await self._get_client()
            response = await client.get(url)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Alertmanager health check failed: {e}")
            return False

    async def get_alerts(self) -> List[Dict[str, Any]]:
        """
        获取当前活跃告警

        Returns:
            告警列表
        """
        url = self.config.alerts_url

        try:
            response = await self._request_with_retry("GET", url)

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Get alerts failed: {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"Get alerts failed: {e}")
            return []


# 全局客户端实例
alertmanager_client = AlertmanagerClient()
