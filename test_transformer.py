#!/usr/bin/env python3
"""
测试告警转换器优化效果
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.models.alarm import ZMCAlarm
from app.services.alarm_transformer import AlarmTransformer, DetailInfoParser

def test_detail_parser():
    """测试 detail_info 解析器"""
    print("=" * 80)
    print("测试 DetailInfoParser")
    print("=" * 80)

    # 创建一个模拟告警对象
    class MockAlarm:
        alarm_name = "Test Alarm"
        alarm_code = 31041

    mock_alarm = MockAlarm()

    # 测试用例
    test_cases = [
        # KPI 缺失
        {
            "name": "KPI 缺失告警",
            "detail_info": """The following KPIs are missing(lost):[402,404,406,412,414,418,424,400]
Start Time:2025-12-11 15:25:00
End Time  :2025-12-11 15:30:00"""
        },
        # 磁盘使用率
        {
            "name": "磁盘使用率告警",
            "detail_info": "Filesystem usage is limited [Fs:/var,Usd=83%,Limt =80,Fs:/oracle,Usd=78%,Limt =70,Fs:/junosoft,Usd=74%,Limt =70]!"
        },
        # 心跳错误
        {
            "name": "心跳错误告警",
            "detail_info": "NE(test42_1.42-zmc:29009) HeartBeat not exists,maybe disconnect to server!"
        },
        # Ping 超时
        {
            "name": "Ping 超时告警",
            "detail_info": """Ping ZMC agent(10.45.66.44) ... Timeout.Result is
[PING 10.45.66.44 (10.45.66.44) 56(84) bytes of data.

--- 10.45.66.44 ping statistics ---
5 packets transmitted, 0 received, 100% packet loss, time 4086ms]"""
        },
        # JSON 格式
        {
            "name": "JSON 格式告警",
            "detail_info": '{"AlarmErrMsg":"---------------------------------------------\\nerrorCode=[]\\nerrorDesc=./PingExt not exists!"}'
        },
    ]

    for tc in test_cases:
        print(f"\n--- {tc['name']} ---")
        result = DetailInfoParser.parse(tc["detail_info"], mock_alarm)
        print(f"  Summary: {result['summary']}")
        print(f"  Detail: {result['detail'][:100]}..." if len(result['detail']) > 100 else f"  Detail: {result['detail']}")
        if result['structured']:
            print(f"  Structured: {json.dumps(result['structured'], ensure_ascii=False, indent=2)[:200]}")


def test_transformer():
    """测试告警转换器"""
    print("\n" + "=" * 80)
    print("测试 AlarmTransformer")
    print("=" * 80)

    transformer = AlarmTransformer()

    # 模拟一个完整的告警
    alarm_data = {
        "event_inst_id": 74705689009,
        "alarm_inst_id": 74670949009,
        "event_time": None,
        "create_date": None,
        "alarm_code": 3200203,
        "alarm_level": "3",
        "reset_flag": "1",
        "alarm_name": "Abnormal disk utilization rate threshold-Minor",
        "fault_reason": "Host disk utilization rate threshold reaches alarm threshold.",
        "deal_suggest": "Check disk usage and clean up if needed.",
        "host_name": "testocs_1.31",
        "host_ip": "10.101.1.31",
        "app_name": "OCS后台",
        "business_domain": "测试域",
        "environment": "Test",
        "total_alarm": 7,
        "detail_info": "Filesystem usage is limited [Fs:/var,Usd=83%,Limt =80,Fs:/oracle,Usd=78%,Limt =70]!",
        "data_1": "FsUsedLimit",
        "data_2": "1",
        "data_3": "MoniDisk",
        "res_inst_type": "DEVICE",
    }

    alarm = ZMCAlarm(**alarm_data)

    # 转换为 Prometheus 格式
    prom_alert = transformer.transform_to_prometheus(alarm, resolved=False)

    print("\n--- Labels ---")
    for k, v in sorted(prom_alert.labels.items()):
        print(f"  {k}: {v}")

    print("\n--- Annotations ---")
    for k, v in sorted(prom_alert.annotations.items()):
        # 对于多行内容，缩进显示
        if "\n" in v:
            print(f"  {k}:")
            for line in v.split("\n"):
                print(f"    {line}")
        else:
            print(f"  {k}: {v[:100]}..." if len(v) > 100 else f"  {k}: {v}")

    print("\n--- Full Alert JSON ---")
    print(json.dumps(prom_alert.to_dict(), indent=2, ensure_ascii=False))


def test_kpi_alarm():
    """测试 KPI 告警"""
    print("\n" + "=" * 80)
    print("测试 KPI Missing 告警")
    print("=" * 80)

    transformer = AlarmTransformer()

    alarm_data = {
        "event_inst_id": 74705689009,
        "alarm_code": 31041,
        "alarm_level": "2",
        "reset_flag": "1",
        "alarm_name": "KPI Missing(Lost)",
        "fault_reason": "KPI data collection failed.",
        "host_name": "testocs_1.31",
        "host_ip": "10.101.1.31",
        "app_name": "OCS后台",
        "detail_info": """The following KPIs are missing(lost):[402,404,406,412,414,418,424,400]
Start Time:2025-12-11 15:25:00
End Time  :2025-12-11 15:30:00""",
        "data_1": "KPI_INTEGRITY",
        "res_inst_type": "APP_SERVICE",
    }

    alarm = ZMCAlarm(**alarm_data)
    prom_alert = transformer.transform_to_prometheus(alarm, resolved=False)

    print("\n--- Labels ---")
    for k, v in sorted(prom_alert.labels.items()):
        print(f"  {k}: {v}")

    print("\n--- Description ---")
    print(prom_alert.annotations.get("description", ""))


if __name__ == "__main__":
    test_detail_parser()
    test_transformer()
    test_kpi_alarm()
    print("\n" + "=" * 80)
    print("测试完成!")
    print("=" * 80)
