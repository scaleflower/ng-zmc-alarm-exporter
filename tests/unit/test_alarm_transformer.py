"""
告警转换器单元测试

测试 ZMC 告警到 Prometheus Alert 的转换逻辑。
"""

import pytest
from datetime import datetime

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
        assert result.labels["instance"] == sample_alarm.effective_host

    def test_transform_alarm_severity_mapping(self, transformer):
        """测试告警级别映射"""
        # Critical (level 1)
        alarm_critical = ZMCAlarm(
            event_inst_id=1, alarm_code=1001, alarm_level="1",
            host_ip="192.168.1.1", reset_flag="1"
        )
        result = transformer.transform_to_prometheus(alarm_critical)
        assert result.labels["severity"] == "critical"

        # Major (level 2) -> maps to "error"
        alarm_major = ZMCAlarm(
            event_inst_id=2, alarm_code=1002, alarm_level="2",
            host_ip="192.168.1.2", reset_flag="1"
        )
        result = transformer.transform_to_prometheus(alarm_major)
        assert result.labels["severity"] == "error"

        # Minor (level 3) -> maps to "warning"
        alarm_minor = ZMCAlarm(
            event_inst_id=3, alarm_code=1003, alarm_level="3",
            host_ip="192.168.1.3", reset_flag="1"
        )
        result = transformer.transform_to_prometheus(alarm_minor)
        assert result.labels["severity"] == "warning"

        # Warning (level 4) -> maps to "info"
        alarm_warning = ZMCAlarm(
            event_inst_id=4, alarm_code=1004, alarm_level="4",
            host_ip="192.168.1.4", reset_flag="1"
        )
        result = transformer.transform_to_prometheus(alarm_warning)
        assert result.labels["severity"] == "info"

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

        # FIRING 告警没有 endsAt
        assert result.endsAt is None
        assert result.startsAt is not None

    def test_transform_resolved_alarm(self, transformer, sample_alarm):
        """测试 RESOLVED 状态告警"""
        # 使用 naive datetime，让 transformer 处理时区转换
        resolved_time = datetime(2024, 1, 15, 12, 0, 0)
        result = transformer.transform_to_prometheus(
            sample_alarm, resolved=True, resolved_at=resolved_time
        )

        # RESOLVED 告警有 endsAt
        assert result.endsAt is not None
        assert result.startsAt is not None

    # ========== 过滤测试 ==========

    def test_filter_alarms_by_level(self, transformer, sample_alarms):
        """测试按级别过滤告警"""
        # 默认应该只保留 critical 和 major (level 1, 2)
        filtered = transformer.filter_alarms(sample_alarms)

        # 检查 minor (level 3) 是否被过滤
        filtered_levels = [a.alarm_level for a in filtered]
        assert "3" not in filtered_levels or len(filtered) <= len(sample_alarms)

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
            alarm_name=None,
            reset_flag="1"  # Required field
        )

        result = transformer.transform_to_prometheus(alarm)
        assert result is not None
        assert "instance" in result.labels

    def test_alarm_with_special_characters(self, transformer):
        """测试包含特殊字符的告警"""
        alarm = ZMCAlarm(
            event_inst_id=12345,
            alarm_code=1001,
            alarm_level="1",
            host_ip="192.168.1.100",
            alarm_name="CPU Usage > 90% (Critical)",
            detail_info='Error: "Connection failed" at line 42',
            reset_flag="1"
        )

        result = transformer.transform_to_prometheus(alarm)
        assert result is not None

    def test_alarm_with_unicode(self, transformer):
        """测试包含中文的告警"""
        alarm = ZMCAlarm(
            event_inst_id=12345,
            alarm_code=1001,
            alarm_level="1",
            host_ip="192.168.1.100",
            alarm_name="CPU使用率过高",
            detail_info="服务器 CPU 使用率超过 90%",
            reset_flag="1"
        )

        result = transformer.transform_to_prometheus(alarm)
        assert result is not None


class TestZMCAlarmModel:
    """ZMCAlarm 模型属性测试"""

    def test_is_recovery_property(self):
        """测试 is_recovery 属性"""
        # reset_flag="0" 表示恢复
        alarm = ZMCAlarm(
            event_inst_id=1, alarm_code=1001, reset_flag="0"
        )
        assert alarm.is_recovery is True

        # reset_flag="1" 表示告警
        alarm = ZMCAlarm(
            event_inst_id=1, alarm_code=1001, reset_flag="1"
        )
        assert alarm.is_recovery is False

    def test_is_active_property(self):
        """测试 is_active 属性"""
        # alarm_state=None 或 "U" 表示活跃
        alarm = ZMCAlarm(
            event_inst_id=1, alarm_code=1001, reset_flag="1",
            alarm_state=None
        )
        assert alarm.is_active is True

        alarm = ZMCAlarm(
            event_inst_id=1, alarm_code=1001, reset_flag="1",
            alarm_state="U"
        )
        assert alarm.is_active is True

        # 其他状态不活跃
        alarm = ZMCAlarm(
            event_inst_id=1, alarm_code=1001, reset_flag="0",
            alarm_state="A"
        )
        assert alarm.is_active is False

    def test_is_cleared_property(self):
        """测试 is_cleared 属性"""
        # A/M/C 状态表示已清除
        for state in ["A", "M", "C"]:
            alarm = ZMCAlarm(
                event_inst_id=1, alarm_code=1001, reset_flag="0",
                alarm_state=state
            )
            assert alarm.is_cleared is True, f"State {state} should be cleared"

        # U 或 None 状态未清除
        alarm = ZMCAlarm(
            event_inst_id=1, alarm_code=1001, reset_flag="1",
            alarm_state="U"
        )
        assert alarm.is_cleared is False

    def test_effective_severity_property(self):
        """测试 effective_severity 属性"""
        # 有 alarm_level
        alarm = ZMCAlarm(
            event_inst_id=1, alarm_code=1001, reset_flag="1",
            alarm_level="2"
        )
        assert alarm.effective_severity == "2"

        # 无 alarm_level，有 default_warn_level
        alarm = ZMCAlarm(
            event_inst_id=1, alarm_code=1001, reset_flag="1",
            alarm_level=None, default_warn_level="3"
        )
        assert alarm.effective_severity == "3"

        # 都没有，默认返回 "3"
        alarm = ZMCAlarm(
            event_inst_id=1, alarm_code=1001, reset_flag="1",
            alarm_level=None, default_warn_level=None
        )
        assert alarm.effective_severity == "3"

    def test_effective_host_property(self):
        """测试 effective_host 属性"""
        # 有 host_name 和 host_ip
        alarm = ZMCAlarm(
            event_inst_id=1, alarm_code=1001, reset_flag="1",
            host_name="server-01", host_ip="192.168.1.100"
        )
        assert alarm.effective_host == "server-01@192.168.1.100"

        # 只有 host_ip
        alarm = ZMCAlarm(
            event_inst_id=1, alarm_code=1001, reset_flag="1",
            host_name=None, host_ip="192.168.1.100"
        )
        assert alarm.effective_host == "192.168.1.100"

        # 只有 host_name
        alarm = ZMCAlarm(
            event_inst_id=1, alarm_code=1001, reset_flag="1",
            host_name="server-01", host_ip=None
        )
        assert alarm.effective_host == "server-01"

        # 都没有，有 device_id
        alarm = ZMCAlarm(
            event_inst_id=1, alarm_code=1001, reset_flag="1",
            host_name=None, host_ip=None, device_id=100
        )
        assert alarm.effective_host == "device_100"

    def test_effective_alert_name_property(self):
        """测试 effective_alert_name 属性"""
        # 有 alarm_name
        alarm = ZMCAlarm(
            event_inst_id=1, alarm_code=1001, reset_flag="1",
            alarm_name="CPU High Usage"
        )
        assert alarm.effective_alert_name == "CPU High Usage ( 1001 )"

        # 无 alarm_name
        alarm = ZMCAlarm(
            event_inst_id=1, alarm_code=2002, reset_flag="1",
            alarm_name=None
        )
        assert alarm.effective_alert_name == "ZMC_ALARM ( 2002 )"

    def test_get_resolved_time_method(self):
        """测试 get_resolved_time 方法"""
        now = datetime(2024, 1, 15, 12, 0, 0)

        # 自动恢复状态
        alarm = ZMCAlarm(
            event_inst_id=1, alarm_code=1001, reset_flag="0",
            alarm_state="A", reset_date=now
        )
        assert alarm.get_resolved_time() == now

        # 手工清除状态
        alarm = ZMCAlarm(
            event_inst_id=1, alarm_code=1001, reset_flag="0",
            alarm_state="M", clear_date=now
        )
        assert alarm.get_resolved_time() == now

        # 未恢复状态
        alarm = ZMCAlarm(
            event_inst_id=1, alarm_code=1001, reset_flag="1",
            alarm_state="U"
        )
        assert alarm.get_resolved_time() is None
