"""
OpsGenie 客户端单元测试
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

from app.services.opsgenie_client import OpsGenieClient, SEVERITY_TO_PRIORITY
from app.models.prometheus import PrometheusAlert, PrometheusSilence, SilenceMatcher
from app.config import OpsGenieConfig


@pytest.fixture
def opsgenie_config():
    """创建测试配置"""
    return OpsGenieConfig(
        api_url="https://api.opsgenie.com",
        api_key="test-api-key",
        default_team="Test Team",
        default_priority="P3",
        timeout=30,
        retry_count=3,
        retry_interval=1000
    )


@pytest.fixture
def opsgenie_client(opsgenie_config):
    """创建测试客户端"""
    return OpsGenieClient(config=opsgenie_config)


@pytest.fixture
def sample_alert():
    """创建测试告警"""
    return PrometheusAlert(
        labels={
            "alertname": "Test Alert",
            "alarm_id": "12345",
            "severity": "critical",
            "alarm_code": "TEST001",
            "host_name": "test-server",
            "source": "zmc"
        },
        annotations={
            "summary": "Test alert summary",
            "description": "This is a test alert description"
        },
        startsAt="2024-12-17T04:00:00Z"
    )


@pytest.fixture
def resolved_alert(sample_alert):
    """创建已恢复的告警"""
    sample_alert.endsAt = "2024-12-17T05:00:00Z"
    return sample_alert


class TestSeverityToPriority:
    """测试优先级映射"""

    def test_critical_to_p1(self):
        assert SEVERITY_TO_PRIORITY["critical"] == "P1"

    def test_error_to_p2(self):
        assert SEVERITY_TO_PRIORITY["error"] == "P2"

    def test_warning_to_p3(self):
        assert SEVERITY_TO_PRIORITY["warning"] == "P3"

    def test_info_to_p4(self):
        assert SEVERITY_TO_PRIORITY["info"] == "P4"


class TestOpsGenieClient:
    """OpsGenie 客户端测试"""

    def test_convert_to_opsgenie_alert(self, opsgenie_client, sample_alert):
        """测试告警转换"""
        result = opsgenie_client._convert_to_opsgenie_alert(sample_alert)

        assert result["message"] == "Test Alert"
        assert result["alias"] == "zmc-12345"
        assert result["priority"] == "P1"  # critical -> P1
        assert "zmc" in result["tags"]
        assert result["description"] == "This is a test alert description"
        assert result["responders"] == [{"name": "Test Team", "type": "team"}]

    def test_convert_alert_without_alarm_id(self, opsgenie_client):
        """测试没有 alarm_id 的告警转换"""
        alert = PrometheusAlert(
            labels={
                "alertname": "Test Alert",
                "severity": "warning"
            },
            annotations={}
        )

        result = opsgenie_client._convert_to_opsgenie_alert(alert)

        assert result["message"] == "Test Alert"
        assert "alias" not in result
        assert result["priority"] == "P3"  # warning -> P3

    def test_convert_alert_with_long_message(self, opsgenie_client):
        """测试长消息截断"""
        alert = PrometheusAlert(
            labels={
                "alertname": "A" * 200,  # 超过130字符
                "alarm_id": "123",
                "severity": "info"
            },
            annotations={}
        )

        result = opsgenie_client._convert_to_opsgenie_alert(alert)

        assert len(result["message"]) == 130

    def test_get_alert_alias(self, opsgenie_client, sample_alert):
        """测试获取告警 alias"""
        alias = opsgenie_client._get_alert_alias(sample_alert)
        assert alias == "zmc-12345"

    def test_get_alert_alias_with_event_id(self, opsgenie_client):
        """测试使用 event_id 获取 alias"""
        alert = PrometheusAlert(
            labels={
                "alertname": "Test",
                "event_id": "67890",
                "severity": "warning"
            },
            annotations={}
        )

        alias = opsgenie_client._get_alert_alias(alert)
        assert alias == "zmc-67890"

    def test_get_alert_alias_without_id(self, opsgenie_client):
        """测试没有 ID 时返回 None"""
        alert = PrometheusAlert(
            labels={
                "alertname": "Test",
                "severity": "warning"
            },
            annotations={}
        )

        alias = opsgenie_client._get_alert_alias(alert)
        assert alias is None


class TestOpsGenieClientAsync:
    """OpsGenie 客户端异步测试"""

    @pytest.mark.asyncio
    async def test_push_alerts_empty_list(self, opsgenie_client):
        """测试推送空列表"""
        result = await opsgenie_client.push_alerts([])

        assert result["success"] is True
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_push_alerts_success(self, opsgenie_client, sample_alert):
        """测试成功推送告警"""
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.json.return_value = {"requestId": "test-request-id"}

        with patch.object(
            opsgenie_client, '_request_with_retry',
            new_callable=AsyncMock,
            return_value=mock_response
        ):
            result = await opsgenie_client.push_alerts([sample_alert])

        assert result["success"] is True
        assert result["count"] == 1
        assert result["success_count"] == 1
        assert result["error_count"] == 0

    @pytest.mark.asyncio
    async def test_push_resolved_alert(self, opsgenie_client, resolved_alert):
        """测试推送已恢复告警"""
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.json.return_value = {}

        with patch.object(
            opsgenie_client, '_request_with_retry',
            new_callable=AsyncMock,
            return_value=mock_response
        ):
            result = await opsgenie_client.push_alerts([resolved_alert])

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_close_alert_not_found(self, opsgenie_client, resolved_alert):
        """测试关闭不存在的告警"""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Alert not found"

        with patch.object(
            opsgenie_client, '_request_with_retry',
            new_callable=AsyncMock,
            return_value=mock_response
        ):
            result = await opsgenie_client._close_alert(resolved_alert)

        # 404 应该被视为成功（告警已被关闭）
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_create_silence(self, opsgenie_client):
        """测试创建静默（acknowledge）"""
        silence = PrometheusSilence(
            matchers=[
                SilenceMatcher(name="event_id", value="12345", isRegex=False, isEqual=True)
            ],
            startsAt="2024-12-17T04:00:00Z",
            endsAt="2024-12-18T04:00:00Z",
            createdBy="test",
            comment="Test silence"
        )

        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.json.return_value = {}

        with patch.object(
            opsgenie_client, '_request_with_retry',
            new_callable=AsyncMock,
            return_value=mock_response
        ):
            result = await opsgenie_client.create_silence(silence)

        assert result["success"] is True
        assert result["silence_id"] == "zmc-12345"

    @pytest.mark.asyncio
    async def test_create_silence_without_id(self, opsgenie_client):
        """测试没有 event_id 时创建静默失败"""
        silence = PrometheusSilence(
            matchers=[
                SilenceMatcher(name="alertname", value="Test", isRegex=False, isEqual=True)
            ],
            startsAt="2024-12-17T04:00:00Z",
            endsAt="2024-12-18T04:00:00Z",
            createdBy="test",
            comment="Test silence"
        )

        result = await opsgenie_client.create_silence(silence)

        assert result["success"] is False
        assert "Missing event_id" in result["error"]

    @pytest.mark.asyncio
    async def test_delete_silence(self, opsgenie_client):
        """测试删除静默（关闭告警）"""
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.json.return_value = {}

        with patch.object(
            opsgenie_client, '_request_with_retry',
            new_callable=AsyncMock,
            return_value=mock_response
        ):
            result = await opsgenie_client.delete_silence("zmc-12345")

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_health_check_success(self, opsgenie_client):
        """测试健康检查成功"""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.get.return_value = mock_response

        with patch.object(
            opsgenie_client, '_get_client',
            new_callable=AsyncMock,
            return_value=mock_client
        ):
            result = await opsgenie_client.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, opsgenie_client):
        """测试健康检查失败"""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_client.get.return_value = mock_response

        with patch.object(
            opsgenie_client, '_get_client',
            new_callable=AsyncMock,
            return_value=mock_client
        ):
            result = await opsgenie_client.health_check()

        assert result is False

    @pytest.mark.asyncio
    async def test_get_silences_returns_empty(self, opsgenie_client):
        """测试获取静默列表返回空"""
        result = await opsgenie_client.get_silences()
        assert result == []

    @pytest.mark.asyncio
    async def test_close_client(self, opsgenie_client):
        """测试关闭客户端"""
        mock_client = AsyncMock()
        mock_client.is_closed = False

        opsgenie_client._client = mock_client

        await opsgenie_client.close()

        mock_client.aclose.assert_called_once()
        assert opsgenie_client._client is None


class TestAlertClientFactory:
    """告警客户端工厂测试"""

    def test_get_alertmanager_client(self):
        """测试获取 Alertmanager 客户端"""
        from app.services.alert_client_factory import reset_alert_client

        reset_alert_client()

        with patch('app.services.alert_client_factory.settings') as mock_settings:
            mock_settings.integration.mode = "alertmanager"

            from app.services.alert_client_factory import get_alert_client
            client = get_alert_client()

            from app.services.alertmanager_client import AlertmanagerClient
            assert isinstance(client, AlertmanagerClient)

        reset_alert_client()

    def test_get_opsgenie_client(self):
        """测试获取 OpsGenie 客户端"""
        from app.services.alert_client_factory import reset_alert_client

        reset_alert_client()

        with patch('app.services.alert_client_factory.settings') as mock_settings:
            mock_settings.integration.mode = "opsgenie"

            from app.services.alert_client_factory import get_alert_client
            client = get_alert_client()

            assert isinstance(client, OpsGenieClient)

        reset_alert_client()

    def test_is_opsgenie_mode(self):
        """测试判断是否为 OpsGenie 模式"""
        with patch('app.services.alert_client_factory.settings') as mock_settings:
            mock_settings.integration.mode = "opsgenie"

            from app.services.alert_client_factory import is_opsgenie_mode
            assert is_opsgenie_mode() is True

    def test_is_alertmanager_mode(self):
        """测试判断是否为 Alertmanager 模式"""
        with patch('app.services.alert_client_factory.settings') as mock_settings:
            mock_settings.integration.mode = "alertmanager"

            from app.services.alert_client_factory import is_alertmanager_mode
            assert is_alertmanager_mode() is True
