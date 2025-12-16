#!/usr/bin/env python3
"""
查询 ZMC 数据库最新告警记录，用于分析告警内容优化
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import Settings
from app.services.oracle_client import OracleClient


def main():
    settings = Settings()
    client = OracleClient(settings.oracle)

    print("=" * 80)
    print("ZMC 告警数据库查询工具")
    print("=" * 80)
    print(f"数据库: {settings.oracle.host}:{settings.oracle.port}/{settings.oracle.service_name}")
    print(f"用户: {settings.oracle.username}")
    print("=" * 80)

    try:
        client.init_pool()
        print("✅ 数据库连接成功\n")

        # 1. 查询最新的活跃告警 (NM_ALARM_CDR)
        print("\n" + "=" * 80)
        print("📋 1. 最新活跃告警 (NM_ALARM_CDR, ALARM_STATE='U')")
        print("=" * 80)

        sql_active = """
        SELECT * FROM (
            SELECT
                c.ALARM_INST_ID,
                c.ALARM_CODE,
                c.APP_ENV_ID,
                c.RES_INST_ID,
                c.ALARM_STATE,
                c.ALARM_LEVEL,
                c.TOTAL_ALARM,
                c.CREATE_DATE,
                c.RESET_DATE,
                c.CLEAR_DATE,
                acl.ALARM_NAME,
                acl.FAULT_REASON,
                acl.DEAL_SUGGEST,
                d.DEVICE_NAME AS HOST_NAME,
                d.IP_ADDR AS HOST_IP,
                ae.APP_NAME,
                sd.DOMAIN_NAME AS BUSINESS_DOMAIN,
                CASE sd.DOMAIN_TYPE
                    WHEN 'A' THEN 'Production'
                    WHEN 'T' THEN 'Test'
                    WHEN 'D' THEN 'DR'
                    ELSE 'Unknown'
                END AS ENVIRONMENT
            FROM NM_ALARM_CDR c
            LEFT JOIN NM_ALARM_CODE_LIB acl ON c.ALARM_CODE = acl.ALARM_CODE
            LEFT JOIN APP_ENV ae ON c.APP_ENV_ID = ae.APP_ENV_ID
            LEFT JOIN DEVICE d ON ae.DEVICE_ID = d.DEVICE_ID
            LEFT JOIN SYS_DOMAIN sd ON ae.SYS_DOMAIN_ID = sd.DOMAIN_ID
            WHERE c.ALARM_STATE = 'U'
            ORDER BY c.CREATE_DATE DESC
        ) WHERE ROWNUM <= 10
        """

        active_alarms = client.execute_query(sql_active)
        if active_alarms:
            print(f"\n✅ 找到 {len(active_alarms)} 条活跃告警:\n")
            for i, row in enumerate(active_alarms, 1):
                print(f"--- 活跃告警 #{i} ---")
                print(f"  ALARM_INST_ID: {row.get('alarm_inst_id')}")
                print(f"  ALARM_CODE: {row.get('alarm_code')}")
                print(f"  ALARM_NAME: {row.get('alarm_name')}")
                print(f"  ALARM_LEVEL: {row.get('alarm_level')}")
                print(f"  HOST_NAME: {row.get('host_name')}")
                print(f"  HOST_IP: {row.get('host_ip')}")
                print(f"  APP_NAME: {row.get('app_name')}")
                print(f"  BUSINESS_DOMAIN: {row.get('business_domain')}")
                print(f"  ENVIRONMENT: {row.get('environment')}")
                print(f"  CREATE_DATE: {row.get('create_date')}")
                print(f"  TOTAL_ALARM: {row.get('total_alarm')}")
                print(f"  FAULT_REASON: {row.get('fault_reason')}")
                print(f"  DEAL_SUGGEST: {row.get('deal_suggest')}")
                print()
        else:
            print("⚠️  没有找到活跃告警")

        # 2. 查询最新的告警事件 (NM_ALARM_EVENT)
        print("\n" + "=" * 80)
        print("📋 2. 最新告警事件 (NM_ALARM_EVENT)")
        print("=" * 80)

        sql_events = """
        SELECT * FROM (
            SELECT
                e.EVENT_INST_ID,
                e.EVENT_TIME,
                e.CREATE_DATE,
                e.ALARM_CODE,
                e.ALARM_LEVEL,
                e.RESET_FLAG,
                e.RES_INST_TYPE,
                e.RES_INST_ID,
                e.APP_ENV_ID,
                e.TASK_TYPE,
                e.DETAIL_INFO,
                e.DATA_1, e.DATA_2, e.DATA_3, e.DATA_4, e.DATA_5,
                e.DATA_6, e.DATA_7, e.DATA_8, e.DATA_9, e.DATA_10,
                acl.ALARM_NAME,
                d.DEVICE_NAME AS HOST_NAME,
                d.IP_ADDR AS HOST_IP,
                ae.APP_NAME
            FROM NM_ALARM_EVENT e
            LEFT JOIN NM_ALARM_CODE_LIB acl ON e.ALARM_CODE = acl.ALARM_CODE
            LEFT JOIN APP_ENV ae ON e.APP_ENV_ID = ae.APP_ENV_ID
            LEFT JOIN DEVICE d ON ae.DEVICE_ID = d.DEVICE_ID
            ORDER BY e.CREATE_DATE DESC
        ) WHERE ROWNUM <= 10
        """

        events = client.execute_query(sql_events)
        if events:
            print(f"\n✅ 找到 {len(events)} 条告警事件:\n")
            for i, row in enumerate(events, 1):
                print(f"--- 告警事件 #{i} ---")
                print(f"  EVENT_INST_ID: {row.get('event_inst_id')}")
                print(f"  ALARM_CODE: {row.get('alarm_code')}")
                print(f"  ALARM_NAME: {row.get('alarm_name')}")
                print(f"  ALARM_LEVEL: {row.get('alarm_level')}")
                print(f"  RESET_FLAG: {row.get('reset_flag')} ({'恢复' if row.get('reset_flag') == '0' else '告警'})")
                print(f"  HOST_NAME: {row.get('host_name')}")
                print(f"  HOST_IP: {row.get('host_ip')}")
                print(f"  APP_NAME: {row.get('app_name')}")
                print(f"  RES_INST_TYPE: {row.get('res_inst_type')}")
                print(f"  TASK_TYPE: {row.get('task_type')}")
                print(f"  EVENT_TIME: {row.get('event_time')}")
                print(f"  CREATE_DATE: {row.get('create_date')}")
                print(f"  DETAIL_INFO: {row.get('detail_info')}")
                # 打印非空的 DATA 字段
                for j in range(1, 11):
                    data_val = row.get(f'data_{j}')
                    if data_val:
                        print(f"  DATA_{j}: {data_val}")
                print()
        else:
            print("⚠️  没有找到告警事件")

        # 3. 查看告警码库信息
        print("\n" + "=" * 80)
        print("📋 3. 告警码库概览 (NM_ALARM_CODE_LIB)")
        print("=" * 80)

        sql_codes = """
        SELECT * FROM (
            SELECT
                ALARM_CODE,
                ALARM_NAME,
                ALARM_TYPE_CODE,
                WARN_LEVEL,
                FAULT_REASON,
                DEAL_SUGGEST,
                IS_USE
            FROM NM_ALARM_CODE_LIB
            WHERE IS_USE = 'Y'
            ORDER BY ALARM_CODE
        ) WHERE ROWNUM <= 20
        """

        codes = client.execute_query(sql_codes)
        if codes:
            print(f"\n✅ 找到 {len(codes)} 条告警码定义:\n")
            print(f"{'CODE':<10} {'NAME':<40} {'LEVEL':<6} {'FAULT_REASON':<40}")
            print("-" * 100)
            for row in codes:
                name = str(row.get('alarm_name', ''))[:38]
                reason = str(row.get('fault_reason', ''))[:38]
                print(f"{row.get('alarm_code'):<10} {name:<40} {row.get('warn_level', ''):<6} {reason:<40}")
        else:
            print("⚠️  没有找到告警码定义")

        # 4. 查询同步状态统计
        print("\n" + "=" * 80)
        print("📋 4. 同步状态统计 (NM_ALARM_SYNC_STATUS)")
        print("=" * 80)

        sql_sync = """
        SELECT
            SYNC_STATUS,
            COUNT(*) AS ALARM_COUNT,
            MIN(CREATE_TIME) AS EARLIEST_ALARM,
            MAX(UPDATE_TIME) AS LATEST_UPDATE,
            SUM(PUSH_COUNT) AS TOTAL_PUSHES,
            SUM(ERROR_COUNT) AS TOTAL_ERRORS
        FROM NM_ALARM_SYNC_STATUS
        GROUP BY SYNC_STATUS
        ORDER BY SYNC_STATUS
        """

        try:
            sync_stats = client.execute_query(sql_sync)
            if sync_stats:
                print(f"\n✅ 同步状态统计:\n")
                print(f"{'STATUS':<15} {'COUNT':<10} {'PUSHES':<10} {'ERRORS':<10}")
                print("-" * 50)
                for row in sync_stats:
                    print(f"{row.get('sync_status'):<15} {row.get('alarm_count'):<10} {row.get('total_pushes', 0):<10} {row.get('total_errors', 0):<10}")
            else:
                print("⚠️  没有同步状态记录")
        except Exception as e:
            print(f"⚠️  查询同步状态失败 (表可能不存在): {e}")

    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.close_pool()
        print("\n" + "=" * 80)
        print("数据库连接已关闭")


if __name__ == "__main__":
    main()
