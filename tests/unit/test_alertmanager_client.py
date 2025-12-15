"""
Alertmanager 客户端单元测试

使用 pytest-httpx 模拟 HTTP 请求。
"""

import pytest
from pytest_httpx import HTTPXMock

from app.services.alertmanager_client import AlertmanagerClient
from app.models.prometheus import PrometheusAlert, PrometheusSilence, SilenceMatcher
from app.config import AlertmanagerConfig


class TestAlertmanagerClient:
    """Alertmanager 客户端测试"""

    @pytest.fixture
    def config(self):
        """测试配置"""
        return AlertmanagerConfig(
            url="http://localhost:9093",
            timeout=5,
            max_retries=1
        )

    @pytest.fixture
    def client(self, config):
        """创建客户端实例"""
        return AlertmanagerClient(config)

    @pytest.fixture
    def sample_alert(self):
        """测试用告警"""
        return PrometheusAlert(
            labels={
                "alertname": "TestAlert",
                "severity": "critical",
                "instance": "192.168.1.100",
                "event_id": "12345"
            },
            annotations={
                "summary": "Test alert summary",
                "description": "Test alert description"
            },
            startsAt="2024-01-15T10:00:00Z"
        )

    # ========== 推送告警测试 ==========

    @pytest.mark.asyncio
    async def test_push_single_alert_success(self, client, sample_alert, httpx_mock: HTTPXMock):
        """测试成功推送单个告警"""
        httpx_mock.add_response(
            url="http://localhost:9093/api/v2/alerts",
            method="POST",
            status_code=200
        )

        result = await client.push_single_alert(sample_alert)

        assert result["success"] is True
        assert result["status_code"] == 200

    @pytest.mark.asyncio
    async def test_push_single_alert_failure(self, client, sample_alert, httpx_mock: HTTPXMock):
        """测试推送告警失败"""
        httpx_mock.add_response(
            url="http://localhost:9093/api/v2/alerts",
            method="POST",
            status_code=500,
            text="Internal Server Error"
        )

        result = await client.push_single_alert(sample_alert)

        assert result["success"] is False
        assert result["status_code"] == 500

    @pytest.mark.asyncio
    async def test_push_alerts_batch(self, client, httpx_mock: HTTPXMock):
        """测试批量推送告警"""
        alerts = [
            PrometheusAlert(
                labels={"alertname": f"Alert{i}", "severity": "warning", "instance": f"192.168.1.{i}"},
                annotations={"summary": f"Alert {i}"},
                startsAt="2024-01-15T10:00:00Z"
            )
            for i in range(3)
        ]

        httpx_mock.add_response(
            url="http://localhost:9093/api/v2/alerts",
            method="POST",
            status_code=200
        )

        result = await client.push_alerts(alerts)

        assert result["success"] is True

    # ========== Silence 管理测试 ==========

    @pytest.mark.asyncio
    async def test_create_silence_success(self, client, httpx_mock: HTTPXMock):
        """测试成功创建 Silence"""
        httpx_mock.add_response(
            url="http://localhost:9093/api/v2/silences",
            method="POST",
            status_code=200,
            json={"silenceID": "abc-123-xyz"}
        )

        silence = PrometheusSilence(
            matchers=[SilenceMatcher(name="event_id", value="12345", isRegex=False, isEqual=True)],
            startsAt="2024-01-15T10:00:00Z",
            endsAt="2024-01-16T10:00:00Z",
            createdBy="test",
            comment="Test silence"
        )

        result = await client.create_silence(silence)

        assert result["success"] is True
        assert result["silence_id"] == "abc-123-xyz"

    @pytest.mark.asyncio
    async def test_delete_silence_success(self, client, httpx_mock: HTTPXMock):
        """测试成功删除 Silence"""
        silence_id = "abc-123-xyz"
        httpx_mock.add_response(
            url=f"http://localhost:9093/api/v2/silences/{silence_id}",
            method="DELETE",
            status_code=200
        )

        result = await client.delete_silence(silence_id)

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_delete_silence_not_found(self, client, httpx_mock: HTTPXMock):
        """测试删除不存在的 Silence"""
        silence_id = "non-existent"
        httpx_mock.add_response(
            url=f"http://localhost:9093/api/v2/silences/{silence_id}",
            method="DELETE",
            status_code=404,
            text="Silence not found"
        )

        result = await client.delete_silence(silence_id)

        assert result["success"] is False

    # ========== 健康检查测试 ==========

    @pytest.mark.asyncio
    async def test_health_check_success(self, client, httpx_mock: HTTPXMock):
        """测试健康检查成功"""
        httpx_mock.add_response(
            url="http://localhost:9093/api/v2/status",
            method="GET",
            status_code=200,
            json={"cluster": {"status": "ready"}}
        )

        result = await client.check_health()

        assert result["healthy"] is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, client, httpx_mock: HTTPXMock):
        """测试健康检查失败"""
        httpx_mock.add_response(
            url="http://localhost:9093/api/v2/status",
            method="GET",
            status_code=503,
            text="Service Unavailable"
        )

        result = await client.check_health()

        assert result["healthy"] is False


class TestRetryMechanism:
    """重试机制测试"""

    @pytest.fixture
    def client_with_retries(self):
        """创建带重试的客户端"""
        config = AlertmanagerConfig(
            url="http://localhost:9093",
            timeout=1,
            max_retries=3
        )
        return AlertmanagerClient(config)

    @pytest.mark.asyncio
    async def test_retry_on_failure(self, client_with_retries, httpx_mock: HTTPXMock):
        """测试失败后重试"""
        # 前两次失败，第三次成功
        httpx_mock.add_response(status_code=503)
        httpx_mock.add_response(status_code=503)
        httpx_mock.add_response(status_code=200)

        alert = PrometheusAlert(
            labels={"alertname": "Test", "severity": "warning", "instance": "test"},
            annotations={"summary": "Test"},
            startsAt="2024-01-15T10:00:00Z"
        )

        result = await client_with_retries.push_single_alert(alert)

        # 应该在第三次成功
        assert result["success"] is True
        assert len(httpx_mock.get_requests()) == 3
