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
            retry_count=1
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

    @pytest.mark.asyncio
    async def test_push_empty_alerts(self, client, httpx_mock: HTTPXMock):
        """测试推送空告警列表"""
        result = await client.push_alerts([])

        assert result["success"] is True
        assert result["count"] == 0
        assert result["message"] == "No alerts to push"

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

    @pytest.mark.asyncio
    async def test_get_silences_success(self, client, httpx_mock: HTTPXMock):
        """测试获取静默规则列表"""
        httpx_mock.add_response(
            url="http://localhost:9093/api/v2/silences",
            method="GET",
            status_code=200,
            json=[
                {"id": "silence-1", "status": {"state": "active"}},
                {"id": "silence-2", "status": {"state": "active"}}
            ]
        )

        result = await client.get_silences()

        assert len(result) == 2
        assert result[0]["id"] == "silence-1"

    # ========== 健康检查测试 ==========

    @pytest.mark.asyncio
    async def test_health_check_success(self, client, httpx_mock: HTTPXMock):
        """测试健康检查成功"""
        httpx_mock.add_response(
            url="http://localhost:9093/-/healthy",
            method="GET",
            status_code=200
        )

        result = await client.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, client, httpx_mock: HTTPXMock):
        """测试健康检查失败"""
        httpx_mock.add_response(
            url="http://localhost:9093/-/healthy",
            method="GET",
            status_code=503,
            text="Service Unavailable"
        )

        result = await client.health_check()

        assert result is False

    # ========== 状态获取测试 ==========

    @pytest.mark.asyncio
    async def test_get_status_success(self, client, httpx_mock: HTTPXMock):
        """测试获取状态成功"""
        httpx_mock.add_response(
            url="http://localhost:9093/api/v2/status",
            method="GET",
            status_code=200,
            json={"cluster": {"status": "ready"}, "uptime": "10h30m"}
        )

        result = await client.get_status()

        assert result is not None
        assert result["cluster"]["status"] == "ready"

    @pytest.mark.asyncio
    async def test_get_status_failure(self, client, httpx_mock: HTTPXMock):
        """测试获取状态失败"""
        httpx_mock.add_response(
            url="http://localhost:9093/api/v2/status",
            method="GET",
            status_code=500,
            text="Internal Server Error"
        )

        result = await client.get_status()

        assert result is None

    # ========== 获取告警测试 ==========

    @pytest.mark.asyncio
    async def test_get_alerts_success(self, client, httpx_mock: HTTPXMock):
        """测试获取告警列表成功"""
        httpx_mock.add_response(
            url="http://localhost:9093/api/v2/alerts",
            method="GET",
            status_code=200,
            json=[
                {"labels": {"alertname": "Alert1"}, "status": {"state": "active"}},
                {"labels": {"alertname": "Alert2"}, "status": {"state": "suppressed"}}
            ]
        )

        result = await client.get_alerts()

        assert len(result) == 2
        assert result[0]["labels"]["alertname"] == "Alert1"

    @pytest.mark.asyncio
    async def test_get_alerts_empty(self, client, httpx_mock: HTTPXMock):
        """测试获取空告警列表"""
        httpx_mock.add_response(
            url="http://localhost:9093/api/v2/alerts",
            method="GET",
            status_code=200,
            json=[]
        )

        result = await client.get_alerts()

        assert result == []


class TestRetryMechanism:
    """重试机制测试"""

    @pytest.fixture
    def client_with_retries(self):
        """创建带重试的客户端"""
        config = AlertmanagerConfig(
            url="http://localhost:9093",
            timeout=1,
            retry_count=3,
            retry_interval=100  # 100ms for faster tests
        )
        return AlertmanagerClient(config)

    @pytest.mark.asyncio
    async def test_retry_on_timeout(self, client_with_retries, httpx_mock: HTTPXMock):
        """测试超时后重试"""
        import httpx

        # 前两次超时，第三次成功
        httpx_mock.add_exception(httpx.TimeoutException("timeout"))
        httpx_mock.add_exception(httpx.TimeoutException("timeout"))
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

    @pytest.mark.asyncio
    async def test_retry_on_connection_error(self, client_with_retries, httpx_mock: HTTPXMock):
        """测试连接错误后重试"""
        import httpx

        # 前两次连接失败，第三次成功
        httpx_mock.add_exception(httpx.ConnectError("connection refused"))
        httpx_mock.add_exception(httpx.ConnectError("connection refused"))
        httpx_mock.add_response(status_code=200)

        alert = PrometheusAlert(
            labels={"alertname": "Test", "severity": "warning", "instance": "test"},
            annotations={"summary": "Test"},
            startsAt="2024-01-15T10:00:00Z"
        )

        result = await client_with_retries.push_single_alert(alert)

        assert result["success"] is True
        assert len(httpx_mock.get_requests()) == 3

    @pytest.mark.asyncio
    async def test_all_retries_fail(self, client_with_retries, httpx_mock: HTTPXMock):
        """测试所有重试都失败"""
        import httpx

        # 所有重试都超时
        httpx_mock.add_exception(httpx.TimeoutException("timeout"))
        httpx_mock.add_exception(httpx.TimeoutException("timeout"))
        httpx_mock.add_exception(httpx.TimeoutException("timeout"))

        alert = PrometheusAlert(
            labels={"alertname": "Test", "severity": "warning", "instance": "test"},
            annotations={"summary": "Test"},
            startsAt="2024-01-15T10:00:00Z"
        )

        result = await client_with_retries.push_single_alert(alert)

        # 所有重试失败后应返回失败
        assert result["success"] is False
        assert "error" in result
        assert len(httpx_mock.get_requests()) == 3


class TestUnicodeHandling:
    """Unicode 字符处理测试"""

    @pytest.fixture
    def client(self):
        """创建客户端实例"""
        config = AlertmanagerConfig(url="http://localhost:9093", timeout=5, retry_count=1)
        return AlertmanagerClient(config)

    @pytest.mark.asyncio
    async def test_push_alert_with_chinese(self, client, httpx_mock: HTTPXMock):
        """测试推送包含中文的告警"""
        httpx_mock.add_response(
            url="http://localhost:9093/api/v2/alerts",
            method="POST",
            status_code=200
        )

        alert = PrometheusAlert(
            labels={
                "alertname": "CPU使用率过高 ( 1001 )",
                "severity": "critical",
                "instance": "server-01@192.168.1.100"
            },
            annotations={
                "summary": "服务器 CPU 使用率超过 90%",
                "description": "• Severity: CRITICAL (Critical)\n• Detail: 测试告警详情"
            },
            startsAt="2024-01-15T10:00:00Z"
        )

        result = await client.push_single_alert(alert)

        assert result["success"] is True

        # 验证请求内容包含正确的 UTF-8 编码
        request = httpx_mock.get_requests()[0]
        content = request.content.decode("utf-8")
        assert "CPU使用率过高" in content
        assert "服务器" in content
