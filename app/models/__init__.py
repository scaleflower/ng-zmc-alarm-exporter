"""
数据模型模块
"""

from .alarm import ZMCAlarm, AlarmSyncStatus, AlarmSyncLog
from .prometheus import PrometheusAlert, PrometheusSilence

__all__ = [
    "ZMCAlarm",
    "AlarmSyncStatus",
    "AlarmSyncLog",
    "PrometheusAlert",
    "PrometheusSilence",
]
