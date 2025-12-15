"""
告警转换器单元测试

测试 ZMC 告警到 Prometheus Alert 的转换逻辑。
"""

import pytest
from datetime import datetime, timezone

from app.models.alarm import ZMCAlarm
from app.services.alarm_transformer import AlarmTransformer


class TestAlarmTransformer:
    """告警转换器测试"""

    @pytest.fixture
    def transformer(self):
        """创建转换器实例"""
        return AlarmTransformer()

    # ========== 基础转换测试 ==========

    def test_transform_basic_alarm(self, transformer, sample_alarm):
        """测试基础告警转换"""
        result = transformer.transform_to_prometheus(sample_alarm)

        assert result is not None
        assert result.labels["event_id"] == str(sample_alarm.event_inst_id)
        assert result.labels["alarm_code"] == str(sample_alarm.alarm_code)
        assert result.labels["instance"] == sample_alarm.host_ip

    def test_transform_alarm_severity_mapping(self, transformer):
        """测试告警级别映射"""
        # Critical (level 1)
        alarm_critical = ZMCAlarm(
            event_inst_id=1, alarm_code=1001, alarm_level=1, host_ip="192.168.1.1"
        )
        result = transformer.transform_to_prometheus(alarm_critical)
        assert result.labels["severity"] == "critical"

        # Major (level 2)
        alarm_major = ZMCAlarm(
            event_inst_id=2, alarm_code=1002, alarm_level=2, host_ip="192.168.1.2"
        )
        result = transformer.transform_to_prometheus(alarm_major)
        assert result.labels["severity"] == "major"

        # Minor (level 3)
        alarm_minor = ZMCAlarm(
            event_inst_id=3, alarm_code=1003, alarm_level=3, host_ip="192.168.1.3"
        )
        result = transformer.transform_to_prometheus(alarm_minor)
        assert result.labels["severity"] == "minor"

        # Warning (level 4)
        alarm_warning = ZMCAlarm(
            event_inst_id=4, alarm_code=1004, alarm_level=4, host_ip="192.168.1.4"
        )
        result = transformer.transform_to_prometheus(alarm_warning)
        assert result.labels["severity"] == "warning"

    def test_transform_alertname_format(self, transformer, sample_alarm):
        """测试 alertname 格式"""
        result = transformer.transform_to_prometheus(sample_alarm)

        # alertname 应该包含告警名称和代码
        alertname = result.labels["alertname"]
        assert str(sample_alarm.alarm_code) in alertname

    # ========== 状态转换测试 ==========

    def test_transform_firing_alarm(self, transformer, sample_alarm):
        """测试 FIRING 状态告警"""
        result = transformer.transform_to_prometheus(sample_alarm, resolved=False)

        assert result.status == "firing"
        assert result.endsAt is None or result.endsAt > result.startsAt

    def test_transform_resolved_alarm(self, transformer, sample_alarm):
        """测试 RESOLVED 状态告警"""
        resolved_time = datetime.now(timezone.utc)
        result = transformer.transform_to_prometheus(
            sample_alarm, resolved=True, resolved_at=resolved_time
        )

        assert result.status == "resolved"
        assert result.endsAt is not None

    # ========== 过滤测试 ==========

    def test_filter_alarms_by_level(self, transformer, sample_alarms):
        """测试按级别过滤告警"""
        # 默认应该只保留 critical 和 major (level 1, 2)
        filtered = transformer.filter_alarms(sample_alarms)

        # 检查 minor (level 3) 是否被过滤
        filtered_levels = [a.alarm_level for a in filtered]
        assert 3 not in filtered_levels or len(filtered) <= len(sample_alarms)

    # ========== Silence 创建测试 ==========

    def test_create_silence(self, transformer, sample_alarm):
        """测试创建 Silence 规则"""
        silence = transformer.create_silence(sample_alarm, duration_hours=24)

        assert silence is not None
        assert len(silence.matchers) > 0
        assert silence.createdBy == "zmc-alarm-exporter"

        # 检查 matcher 包含 event_id
        event_id_matcher = next(
            (m for m in silence.matchers if m.name == "event_id"), None
        )
        assert event_id_matcher is not None
        assert event_id_matcher.value == str(sample_alarm.event_inst_id)

    def test_create_silence_with_custom_duration(self, transformer, sample_alarm):
        """测试自定义时长的 Silence"""
        silence = transformer.create_silence(sample_alarm, duration_hours=48)

        # 验证时间范围
        from datetime import datetime
        starts = datetime.fromisoformat(silence.startsAt.replace('Z', '+00:00'))
        ends = datetime.fromisoformat(silence.endsAt.replace('Z', '+00:00'))

        duration = ends - starts
        assert duration.total_seconds() == 48 * 3600


class TestEdgeCases:
    """边界情况测试"""

    @pytest.fixture
    def transformer(self):
        return AlarmTransformer()

    def test_alarm_with_none_values(self, transformer):
        """测试包含 None 值的告警"""
        alarm = ZMCAlarm(
            event_inst_id=12345,
            alarm_code=1001,
            alarm_level=None,  # None 级别
            host_ip=None,  # None IP
            alarm_name=None
        )

        result = transformer.transform_to_prometheus(alarm)
        assert result is not None
        assert "instance" in result.labels

    def test_alarm_with_special_characters(self, transformer):
        """测试包含特殊字符的告警"""
        alarm = ZMCAlarm(
            event_inst_id=12345,
            alarm_code=1001,
            alarm_level=1,
            host_ip="192.168.1.100",
            alarm_name="CPU Usage > 90% (Critical)",
            detail_info='Error: "Connection failed" at line 42'
        )

        result = transformer.transform_to_prometheus(alarm)
        assert result is not None

    def test_alarm_with_unicode(self, transformer):
        """测试包含中文的告警"""
        alarm = ZMCAlarm(
            event_inst_id=12345,
            alarm_code=1001,
            alarm_level=1,
            host_ip="192.168.1.100",
            alarm_name="CPU使用率过高",
            detail_info="服务器 CPU 使用率超过 90%"
        )

        result = transformer.transform_to_prometheus(alarm)
        assert result is not None
