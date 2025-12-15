"""
Alertmanager 集成测试

需要运行真实的 Alertmanager 服务进行测试。
在 CI 中通过 Docker service 启动。
"""

import pytest
import os

from app.services.alertmanager_client import AlertmanagerClient
from app.models.prometheus import PrometheusAlert, PrometheusSilence, SilenceMatcher
from app.config import AlertmanagerConfig


# 检查是否在集成测试环境中
ALERTMANAGER_URL = os.getenv("ALERTMANAGER_URL", "http://localhost:9093")
SKIP_INTEGRATION = os.getenv("SKIP_INTEGRATION_TESTS", "true").lower() == "true"


@pytest.mark.skipif(SKIP_INTEGRATION, reason="Integration tests disabled")
class TestAlertmanagerIntegration:
    """Alertmanager 集成测试"""

    @pytest.fixture
    def client(self):
        """创建真实的客户端"""
        config = AlertmanagerConfig(url=ALERTMANAGER_URL)
        return AlertmanagerClient(config)

    @pytest.mark.asyncio
    async def test_real_health_check(self, client):
        """测试真实的健康检查"""
        result = await client.check_health()
        assert result["healthy"] is True

    @pytest.mark.asyncio
    async def test_real_push_and_query_alert(self, client):
        """测试真实推送和查询告警"""
        # 创建测试告警
        alert = PrometheusAlert(
            labels={
                "alertname": "IntegrationTestAlert",
                "severity": "warning",
                "instance": "test-instance",
                "event_id": "integration-test-001",
                "source": "pytest"
            },
            annotations={
                "summary": "Integration test alert",
                "description": "This is a test alert from pytest integration tests"
            },
            startsAt="2024-01-15T10:00:00Z"
        )

        # 推送告警
        push_result = await client.push_single_alert(alert)
        assert push_result["success"] is True

        # 等待 Alertmanager 处理
        import asyncio
        await asyncio.sleep(1)

        # 查询告警
        query_result = await client.get_alerts()
        assert query_result["success"] is True

        # 验证告警存在
        alerts = query_result.get("alerts", [])
        test_alert = next(
            (a for a in alerts if a.get("labels", {}).get("event_id") == "integration-test-001"),
            None
        )
        assert test_alert is not None

    @pytest.mark.asyncio
    async def test_real_silence_lifecycle(self, client):
        """测试真实的 Silence 生命周期：创建 -> 查询 -> 删除"""
        # 创建 Silence
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)

        silence = PrometheusSilence(
            matchers=[
                SilenceMatcher(
                    name="event_id",
                    value="integration-test-silence",
                    isRegex=False,
                    isEqual=True
                )
            ],
            startsAt=now.isoformat(),
            endsAt=(now + timedelta(hours=1)).isoformat(),
            createdBy="pytest-integration",
            comment="Integration test silence"
        )

        # 创建
        create_result = await client.create_silence(silence)
        assert create_result["success"] is True
        silence_id = create_result["silence_id"]
        assert silence_id is not None

        # 等待处理
        import asyncio
        await asyncio.sleep(1)

        # 删除
        delete_result = await client.delete_silence(silence_id)
        assert delete_result["success"] is True


@pytest.mark.skipif(SKIP_INTEGRATION, reason="Integration tests disabled")
class TestFullSyncFlow:
    """完整同步流程集成测试"""

    @pytest.mark.asyncio
    async def test_alarm_sync_scenario(self):
        """
        测试完整的告警同步场景:
        1. 创建新告警 -> 推送 FIRING
        2. 状态变更 -> 推送 RESOLVED
        3. 手工清除 -> 创建 Silence
        """
        from app.services.alarm_transformer import AlarmTransformer
        from app.models.alarm import ZMCAlarm

        config = AlertmanagerConfig(url=ALERTMANAGER_URL)
        client = AlertmanagerClient(config)
        transformer = AlarmTransformer()

        # 场景 1: 新告警
        alarm = ZMCAlarm(
            event_inst_id=99999,
            alarm_inst_id=9999,
            alarm_code=9001,
            alarm_level=1,
            alarm_state="U",
            host_ip="192.168.99.99",
            alarm_name="Integration Test Alarm"
        )

        alert = transformer.transform_to_prometheus(alarm)
        result = await client.push_single_alert(alert)
        assert result["success"] is True, "Failed to push FIRING alert"

        # 场景 2: 告警恢复
        alarm.alarm_state = "A"
        resolved_alert = transformer.transform_to_prometheus(alarm, resolved=True)
        result = await client.push_single_alert(resolved_alert)
        assert result["success"] is True, "Failed to push RESOLVED alert"

        # 场景 3: 手工清除 + Silence
        alarm.alarm_state = "M"
        silence = transformer.create_silence(alarm, duration_hours=1)
        result = await client.create_silence(silence)
        assert result["success"] is True, "Failed to create silence"

        # 清理
        if result.get("silence_id"):
            await client.delete_silence(result["silence_id"])
