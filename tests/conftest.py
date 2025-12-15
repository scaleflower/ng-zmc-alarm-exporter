"""
Pytest 配置和共享 Fixtures

提供测试所需的模拟数据和配置。
"""

import pytest
from datetime import datetime
from typing import List, Dict, Any

from app.models.alarm import ZMCAlarm


# ============================================================================
# 告警数据 Fixtures
# ============================================================================

@pytest.fixture
def sample_alarm() -> ZMCAlarm:
    """单个告警样本"""
    return ZMCAlarm(
        event_inst_id=12345,
        alarm_inst_id=1000,
        alarm_code=1001,
        alarm_level="1",  # String type
        alarm_state="U",
        reset_flag="1",  # Required field
        event_time=datetime(2024, 1, 15, 10, 30, 0),
        create_date=datetime(2024, 1, 15, 10, 30, 5),
        detail_info="CPU usage exceeded 90%",
        host_ip="192.168.1.100",
        host_name="app-server-01",
        app_name="ZMC-Core",
        alarm_name="CPU High Usage",
        business_domain="Production",
        environment="Production"
    )


@pytest.fixture
def sample_alarms() -> List[ZMCAlarm]:
    """多个告警样本"""
    return [
        ZMCAlarm(
            event_inst_id=12345,
            alarm_inst_id=1000,
            alarm_code=1001,
            alarm_level="1",  # Critical
            alarm_state="U",
            reset_flag="1",
            host_ip="192.168.1.100",
            alarm_name="CPU High Usage"
        ),
        ZMCAlarm(
            event_inst_id=12346,
            alarm_inst_id=1001,
            alarm_code=1002,
            alarm_level="2",  # Major
            alarm_state="U",
            reset_flag="1",
            host_ip="192.168.1.101",
            alarm_name="Memory High Usage"
        ),
        ZMCAlarm(
            event_inst_id=12347,
            alarm_inst_id=1002,
            alarm_code=1003,
            alarm_level="3",  # Minor
            alarm_state="U",
            reset_flag="1",
            host_ip="192.168.1.102",
            alarm_name="Disk Space Low"
        ),
    ]


@pytest.fixture
def resolved_alarm(sample_alarm: ZMCAlarm) -> ZMCAlarm:
    """已恢复的告警"""
    alarm = sample_alarm.model_copy()
    alarm.alarm_state = "A"
    alarm.reset_flag = "0"
    return alarm


@pytest.fixture
def silenced_alarm(sample_alarm: ZMCAlarm) -> ZMCAlarm:
    """被静默的告警"""
    alarm = sample_alarm.model_copy()
    alarm.alarm_state = "M"
    alarm.reset_flag = "0"
    return alarm


# ============================================================================
# 数据库查询结果 Fixtures
# ============================================================================

@pytest.fixture
def db_alarm_row() -> Dict[str, Any]:
    """模拟数据库查询返回的告警行"""
    return {
        "EVENT_INST_ID": 12345,
        "ALARM_INST_ID": 1000,
        "ALARM_CODE": 1001,
        "ALARM_LEVEL": "1",
        "ALARM_STATE": "U",
        "RESET_FLAG": "1",
        "EVENT_TIME": datetime(2024, 1, 15, 10, 30, 0),
        "CREATE_DATE": datetime(2024, 1, 15, 10, 30, 5),
        "DETAIL_INFO": "CPU usage exceeded 90%",
        "HOST_IP": "192.168.1.100",
        "HOST_NAME": "app-server-01",
        "APP_NAME": "ZMC-Core",
        "ALARM_NAME": "CPU High Usage",
        "BUSINESS_DOMAIN": "Production",
        "ENVIRONMENT": "Production",
        "TOTAL_ALARM": 5,
        "DATA_1": None,
        "DATA_2": None,
    }


@pytest.fixture
def db_status_changed_row() -> Dict[str, Any]:
    """模拟状态变更的告警行"""
    return {
        "SYNC_ID": 100,
        "EVENT_INST_ID": 12345,
        "ALARM_INST_ID": 1000,
        "ALARM_CODE": 1001,
        "OLD_ZMC_STATE": "U",
        "NEW_ZMC_STATE": "A",
        "PUSH_COUNT": 1,
    }


# ============================================================================
# Alertmanager 响应 Fixtures
# ============================================================================

@pytest.fixture
def alertmanager_success_response() -> Dict[str, Any]:
    """Alertmanager 成功响应"""
    return {
        "status": "success"
    }


@pytest.fixture
def alertmanager_silence_response() -> Dict[str, Any]:
    """Alertmanager 创建 Silence 成功响应"""
    return {
        "silenceID": "abc-123-xyz-456"
    }


# ============================================================================
# 环境配置 Fixtures
# ============================================================================

@pytest.fixture
def mock_env_vars(monkeypatch):
    """设置测试环境变量"""
    monkeypatch.setenv("ZMC_ORACLE_HOST", "localhost")
    monkeypatch.setenv("ZMC_ORACLE_PORT", "1521")
    monkeypatch.setenv("ZMC_ORACLE_SERVICE_NAME", "XEPDB1")
    monkeypatch.setenv("ZMC_ORACLE_USERNAME", "test")
    monkeypatch.setenv("ZMC_ORACLE_PASSWORD", "test123")
    monkeypatch.setenv("ALERTMANAGER_URL", "http://localhost:9093")
