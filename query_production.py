#!/usr/bin/env python3
"""
生产环境数据库只读查询脚本
用于比较 NM_ALARM_CDR 与 NM_ALARM_SYNC_STATUS 的数据

警告: 此脚本仅执行 SELECT 查询，不会修改任何数据

使用 Oracle Instant Client thick 模式连接
"""

import os
import sys
from datetime import datetime, timedelta

try:
    from tabulate import tabulate
except ImportError:
    def tabulate(data, headers, tablefmt=None):
        """Fallback if tabulate not installed"""
        result = " | ".join(headers) + "\n"
        result += "-" * 80 + "\n"
        for row in data:
            result += " | ".join(str(x) for x in row) + "\n"
        return result

import oracledb

# 生产环境数据库参数 (通过映射访问)
PROD_DB = {
    "host": "192.168.123.239",
    "port": 51015,
    "service_name": "zmc",
    "username": "zmc",
    "password": "Jsmart.868"
}

# 需要调查的告警 IDs (来自钉钉告警)
ALERT_IDS_TO_INVESTIGATE = [618103769009, 617556899009]


def get_connection():
    """获取数据库连接 (使用 thin 模式，不需要 Oracle Instant Client)"""
    try:
        # 使用 thin 模式连接 (默认)
        dsn = f"{PROD_DB['host']}:{PROD_DB['port']}/{PROD_DB['service_name']}"
        print(f"正在连接生产数据库 (thin mode): {dsn}")
        print(f"用户: {PROD_DB['username']}")

        conn = oracledb.connect(
            user=PROD_DB['username'],
            password=PROD_DB['password'],
            dsn=dsn
        )
        print("✅ 数据库连接成功\n")
        return conn
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def execute_query(conn, sql, params=None):
    """执行查询并返回结果（字典格式）"""
    cursor = conn.cursor()
    try:
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)

        columns = [col[0].lower() for col in cursor.description]
        rows = []
        for row in cursor:
            rows.append(dict(zip(columns, row)))
        return rows
    finally:
        cursor.close()


def print_section(title):
    """打印分节标题"""
    print("\n" + "=" * 80)
    print(f"📋 {title}")
    print("=" * 80)


def query_specific_alerts(conn, event_ids):
    """查询特定的告警 (根据 EVENT_INST_ID)"""
    print_section("🎯 特定告警调查 (来自钉钉告警)")
    print(f"正在查询 EVENT_INST_IDs: {event_ids}")

    ids_str = ",".join(str(id) for id in event_ids)

    # 1. 查询 NM_ALARM_EVENT 表
    sql_event = f"""
    SELECT e.EVENT_INST_ID, e.ALARM_INST_ID, e.ALARM_CODE, e.ALARM_STATE,
           e.RESET_FLAG, e.ALARM_LEVEL, e.HOST_IP, e.HOST_NAME,
           e.DETAIL_INFO, e.CREATE_DATE, e.RESET_DATE, e.CLEAR_DATE
    FROM NM_ALARM_EVENT e
    WHERE e.EVENT_INST_ID IN ({ids_str})
    """

    print("\n📋 NM_ALARM_EVENT 查询结果:")
    print("-" * 80)
    events = execute_query(conn, sql_event)
    if events:
        for ev in events:
            print(f"  EVENT_INST_ID: {ev['event_inst_id']}")
            print(f"  ALARM_INST_ID: {ev['alarm_inst_id']}")
            print(f"  ALARM_CODE: {ev['alarm_code']}")
            print(f"  ALARM_STATE: {ev['alarm_state']}")
            print(f"  RESET_FLAG: {ev['reset_flag']}")
            print(f"  ALARM_LEVEL: {ev['alarm_level']}")
            print(f"  HOST_IP: {ev['host_ip']}")
            print(f"  HOST_NAME: {ev['host_name']}")
            print(f"  CREATE_DATE: {ev['create_date']}")
            print(f"  RESET_DATE: {ev['reset_date']}")
            print(f"  CLEAR_DATE: {ev['clear_date']}")
            print(f"  DETAIL_INFO: {str(ev['detail_info'])[:200]}...")
            print("-" * 40)

        # 提取 ALARM_INST_IDs 用于后续查询
        alarm_inst_ids = list(set(ev['alarm_inst_id'] for ev in events if ev['alarm_inst_id']))
        if alarm_inst_ids:
            print(f"\n📌 关联的 ALARM_INST_IDs: {alarm_inst_ids}")
            alarm_ids_str = ",".join(str(id) for id in alarm_inst_ids)

            # 2. 查询 NM_ALARM_CDR 表
            sql_cdr = f"""
            SELECT c.ALARM_INST_ID, c.ALARM_CODE, c.ALARM_STATE, c.ALARM_LEVEL,
                   c.TOTAL_ALARM, c.CREATE_DATE, c.RESET_DATE, c.CLEAR_DATE
            FROM NM_ALARM_CDR c
            WHERE c.ALARM_INST_ID IN ({alarm_ids_str})
            """

            print("\n📋 NM_ALARM_CDR 查询结果:")
            print("-" * 80)
            cdrs = execute_query(conn, sql_cdr)
            if cdrs:
                for cdr in cdrs:
                    state_desc = {
                        'U': '未确认(活跃)',
                        'A': '自动恢复',
                        'M': '手工清除',
                        'C': '已确认'
                    }.get(cdr['alarm_state'], '未知')
                    print(f"  ALARM_INST_ID: {cdr['alarm_inst_id']}")
                    print(f"  ALARM_CODE: {cdr['alarm_code']}")
                    print(f"  ALARM_STATE: {cdr['alarm_state']} ({state_desc})")
                    print(f"  ALARM_LEVEL: {cdr['alarm_level']}")
                    print(f"  TOTAL_ALARM: {cdr['total_alarm']}")
                    print(f"  CREATE_DATE: {cdr['create_date']}")
                    print(f"  RESET_DATE: {cdr['reset_date']}")
                    print(f"  CLEAR_DATE: {cdr['clear_date']}")
                    print("-" * 40)
            else:
                print("  ⚠️ 未在 NM_ALARM_CDR 中找到记录!")

            # 3. 查询 NM_ALARM_SYNC_STATUS 表
            sql_sync = f"""
            SELECT s.ALARM_INST_ID, s.SYNC_STATUS, s.ZMC_ALARM_STATE,
                   s.CREATE_TIME, s.UPDATE_TIME, s.LAST_PUSH_TIME,
                   s.PUSH_COUNT, s.ERROR_COUNT
            FROM NM_ALARM_SYNC_STATUS s
            WHERE s.ALARM_INST_ID IN ({alarm_ids_str})
            """

            print("\n📋 NM_ALARM_SYNC_STATUS 查询结果:")
            print("-" * 80)
            try:
                syncs = execute_query(conn, sql_sync)
                if syncs:
                    for sync in syncs:
                        print(f"  ALARM_INST_ID: {sync['alarm_inst_id']}")
                        print(f"  SYNC_STATUS: {sync['sync_status']}")
                        print(f"  ZMC_ALARM_STATE: {sync['zmc_alarm_state']}")
                        print(f"  CREATE_TIME: {sync['create_time']}")
                        print(f"  UPDATE_TIME: {sync['update_time']}")
                        print(f"  LAST_PUSH_TIME: {sync['last_push_time']}")
                        print(f"  PUSH_COUNT: {sync['push_count']}")
                        print(f"  ERROR_COUNT: {sync['error_count']}")
                        print("-" * 40)
                else:
                    print("  ⚠️ 未在 NM_ALARM_SYNC_STATUS 中找到记录!")
            except Exception as e:
                print(f"  ⚠️ 查询 NM_ALARM_SYNC_STATUS 失败: {e}")
    else:
        print("  ⚠️ 未在 NM_ALARM_EVENT 中找到记录!")
        print("  这可能意味着:")
        print("    1. 这些 EVENT_INST_ID 实际上是 ALARM_INST_ID")
        print("    2. 记录已被清理")
        print("    3. 数据在其他表中")

        # 尝试直接在 CDR 中查找
        print("\n🔄 尝试直接在 NM_ALARM_CDR 中查找...")
        sql_cdr_direct = f"""
        SELECT c.ALARM_INST_ID, c.ALARM_CODE, c.ALARM_STATE, c.ALARM_LEVEL,
               c.TOTAL_ALARM, c.CREATE_DATE, c.RESET_DATE, c.CLEAR_DATE
        FROM NM_ALARM_CDR c
        WHERE c.ALARM_INST_ID IN ({ids_str})
        """
        cdrs = execute_query(conn, sql_cdr_direct)
        if cdrs:
            print("📋 在 NM_ALARM_CDR 中找到记录 (作为 ALARM_INST_ID):")
            for cdr in cdrs:
                state_desc = {
                    'U': '未确认(活跃)',
                    'A': '自动恢复',
                    'M': '手工清除',
                    'C': '已确认'
                }.get(cdr['alarm_state'], '未知')
                print(f"  ALARM_INST_ID: {cdr['alarm_inst_id']}")
                print(f"  ALARM_STATE: {cdr['alarm_state']} ({state_desc})")
                print(f"  CREATE_DATE: {cdr['create_date']}")
                print("-" * 40)
        else:
            print("  ⚠️ 也未在 NM_ALARM_CDR 中找到记录!")


def main():
    print("=" * 80)
    print("🔍 ZMC 生产环境告警数据分析工具 (只读)")
    print("=" * 80)
    print(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("⚠️  此脚本仅执行 SELECT 查询，不会修改任何数据")
    print("=" * 80)

    conn = get_connection()

    try:
        # 0. 首先查询特定的告警 (来自钉钉)
        if ALERT_IDS_TO_INVESTIGATE:
            query_specific_alerts(conn, ALERT_IDS_TO_INVESTIGATE)

        # 1. 告警汇总统计
        print_section("1. 告警汇总统计 (NM_ALARM_CDR)")

        sql_summary = """
        SELECT
            ALARM_STATE,
            CASE ALARM_STATE
                WHEN 'U' THEN '未确认(活跃)'
                WHEN 'A' THEN '自动恢复'
                WHEN 'M' THEN '手工清除'
                WHEN 'C' THEN '已确认'
                ELSE '未知'
            END AS STATE_DESC,
            COUNT(*) AS ALARM_COUNT,
            MIN(CREATE_DATE) AS EARLIEST_ALARM,
            MAX(CREATE_DATE) AS LATEST_ALARM
        FROM NM_ALARM_CDR
        GROUP BY ALARM_STATE
        ORDER BY ALARM_STATE
        """

        summary = execute_query(conn, sql_summary)
        if summary:
            print("\n告警状态分布:")
            headers = ["状态", "描述", "数量", "最早告警", "最新告警"]
            rows = [[r['alarm_state'], r['state_desc'], r['alarm_count'],
                     r['earliest_alarm'], r['latest_alarm']] for r in summary]
            print(tabulate(rows, headers=headers, tablefmt="grid"))

            total = sum(r['alarm_count'] for r in summary)
            active = sum(r['alarm_count'] for r in summary if r['alarm_state'] == 'U')
            print(f"\n📊 总告警数: {total}, 活跃告警数: {active}")
        else:
            print("⚠️  没有找到告警记录")

        # 2. 同步状态统计
        print_section("2. 同步状态统计 (NM_ALARM_SYNC_STATUS)")

        sql_sync = """
        SELECT
            SYNC_STATUS,
            ZMC_ALARM_STATE,
            COUNT(*) AS COUNT,
            MIN(CREATE_TIME) AS EARLIEST,
            MAX(UPDATE_TIME) AS LATEST_UPDATE
        FROM NM_ALARM_SYNC_STATUS
        GROUP BY SYNC_STATUS, ZMC_ALARM_STATE
        ORDER BY SYNC_STATUS, ZMC_ALARM_STATE
        """

        try:
            sync_stats = execute_query(conn, sql_sync)
            if sync_stats:
                print("\n同步状态分布:")
                headers = ["同步状态", "ZMC状态", "数量", "最早创建", "最新更新"]
                rows = [[r['sync_status'], r['zmc_alarm_state'], r['count'],
                         r['earliest'], r['latest_update']] for r in sync_stats]
                print(tabulate(rows, headers=headers, tablefmt="grid"))
            else:
                print("⚠️  没有同步状态记录")
        except Exception as e:
            print(f"⚠️  查询同步状态失败: {e}")

        # 3. 活跃告警详情
        print_section("3. 活跃告警详情 (ALARM_STATE='U', 最近20条)")

        sql_active = """
        SELECT * FROM (
            SELECT
                c.ALARM_INST_ID,
                c.ALARM_CODE,
                c.ALARM_LEVEL,
                c.TOTAL_ALARM,
                c.CREATE_DATE,
                acl.ALARM_NAME,
                d.DEVICE_NAME AS HOST_NAME,
                d.IP_ADDR AS HOST_IP,
                ae.APP_NAME,
                sd.DOMAIN_NAME AS BUSINESS_DOMAIN
            FROM NM_ALARM_CDR c
            LEFT JOIN NM_ALARM_CODE_LIB acl ON c.ALARM_CODE = acl.ALARM_CODE
            LEFT JOIN APP_ENV ae ON c.APP_ENV_ID = ae.APP_ENV_ID
            LEFT JOIN DEVICE d ON ae.DEVICE_ID = d.DEVICE_ID
            LEFT JOIN SYS_DOMAIN sd ON ae.SYS_DOMAIN_ID = sd.DOMAIN_ID
            WHERE c.ALARM_STATE = 'U'
            ORDER BY c.CREATE_DATE DESC
        ) WHERE ROWNUM <= 20
        """

        active_alarms = execute_query(conn, sql_active)
        if active_alarms:
            print(f"\n找到 {len(active_alarms)} 条活跃告警:")
            headers = ["ALARM_INST_ID", "ALARM_CODE", "告警名称", "级别", "主机", "IP", "应用", "业务域", "创建时间", "次数"]
            rows = [[
                r['alarm_inst_id'],
                r['alarm_code'],
                (r.get('alarm_name') or '')[:20],
                r['alarm_level'],
                (r.get('host_name') or '')[:15],
                r.get('host_ip'),
                (r.get('app_name') or '')[:15],
                (r.get('business_domain') or '')[:10],
                r['create_date'],
                r['total_alarm']
            ] for r in active_alarms]
            print(tabulate(rows, headers=headers, tablefmt="grid"))
        else:
            print("⚠️  没有找到活跃告警")

        # 4. 对比分析：活跃告警 vs 同步状态
        print_section("4. 数据一致性分析")

        # 4.1 活跃告警但未同步
        sql_not_synced = """
        SELECT COUNT(*) AS COUNT FROM NM_ALARM_CDR c
        WHERE c.ALARM_STATE = 'U'
        AND NOT EXISTS (
            SELECT 1 FROM NM_ALARM_SYNC_STATUS s
            WHERE s.ALARM_INST_ID = c.ALARM_INST_ID
        )
        """

        try:
            result = execute_query(conn, sql_not_synced)
            not_synced_count = result[0]['count'] if result else 0
            print(f"\n🔸 活跃告警未同步数量: {not_synced_count}")

            if not_synced_count > 0:
                # 获取未同步的告警详情
                sql_not_synced_detail = """
                SELECT * FROM (
                    SELECT
                        c.ALARM_INST_ID,
                        c.ALARM_CODE,
                        c.ALARM_LEVEL,
                        c.CREATE_DATE,
                        acl.ALARM_NAME
                    FROM NM_ALARM_CDR c
                    LEFT JOIN NM_ALARM_CODE_LIB acl ON c.ALARM_CODE = acl.ALARM_CODE
                    WHERE c.ALARM_STATE = 'U'
                    AND NOT EXISTS (
                        SELECT 1 FROM NM_ALARM_SYNC_STATUS s
                        WHERE s.ALARM_INST_ID = c.ALARM_INST_ID
                    )
                    ORDER BY c.CREATE_DATE DESC
                ) WHERE ROWNUM <= 10
                """
                not_synced_alarms = execute_query(conn, sql_not_synced_detail)
                if not_synced_alarms:
                    print("\n未同步的活跃告警 (前10条):")
                    headers = ["ALARM_INST_ID", "ALARM_CODE", "告警名称", "级别", "创建时间"]
                    rows = [[r['alarm_inst_id'], r['alarm_code'],
                             (r.get('alarm_name') or '')[:30],
                             r['alarm_level'], r['create_date']] for r in not_synced_alarms]
                    print(tabulate(rows, headers=headers, tablefmt="grid"))
        except Exception as e:
            print(f"⚠️  查询未同步告警失败: {e}")

        # 4.2 同步状态为FIRING但ZMC已清除
        sql_stale_firing = """
        SELECT COUNT(*) AS COUNT FROM NM_ALARM_SYNC_STATUS s
        WHERE s.SYNC_STATUS = 'FIRING'
        AND EXISTS (
            SELECT 1 FROM NM_ALARM_CDR c
            WHERE c.ALARM_INST_ID = s.ALARM_INST_ID
            AND c.ALARM_STATE != 'U'
        )
        """

        try:
            result = execute_query(conn, sql_stale_firing)
            stale_count = result[0]['count'] if result else 0
            print(f"\n🔸 同步状态为FIRING但ZMC已清除的数量: {stale_count}")

            if stale_count > 0:
                sql_stale_detail = """
                SELECT * FROM (
                    SELECT
                        s.ALARM_INST_ID,
                        s.SYNC_STATUS,
                        s.ZMC_ALARM_STATE AS SYNC_ZMC_STATE,
                        c.ALARM_STATE AS ACTUAL_ZMC_STATE,
                        s.UPDATE_TIME AS SYNC_UPDATE,
                        c.CLEAR_DATE
                    FROM NM_ALARM_SYNC_STATUS s
                    JOIN NM_ALARM_CDR c ON c.ALARM_INST_ID = s.ALARM_INST_ID
                    WHERE s.SYNC_STATUS = 'FIRING'
                    AND c.ALARM_STATE != 'U'
                    ORDER BY s.UPDATE_TIME DESC
                ) WHERE ROWNUM <= 10
                """
                stale_alarms = execute_query(conn, sql_stale_detail)
                if stale_alarms:
                    print("\n状态不一致的同步记录 (前10条):")
                    headers = ["ALARM_INST_ID", "同步状态", "同步ZMC状态", "实际ZMC状态", "同步更新时间", "清除时间"]
                    rows = [[r['alarm_inst_id'], r['sync_status'], r['sync_zmc_state'],
                             r['actual_zmc_state'], r['sync_update'], r['clear_date']] for r in stale_alarms]
                    print(tabulate(rows, headers=headers, tablefmt="grid"))
        except Exception as e:
            print(f"⚠️  查询状态不一致记录失败: {e}")

        # 4.3 同步状态中不存在于CDR的孤儿记录
        sql_orphan = """
        SELECT COUNT(*) AS COUNT FROM NM_ALARM_SYNC_STATUS s
        WHERE NOT EXISTS (
            SELECT 1 FROM NM_ALARM_CDR c
            WHERE c.ALARM_INST_ID = s.ALARM_INST_ID
        )
        """

        try:
            result = execute_query(conn, sql_orphan)
            orphan_count = result[0]['count'] if result else 0
            print(f"\n🔸 同步状态中的孤儿记录数量: {orphan_count}")
        except Exception as e:
            print(f"⚠️  查询孤儿记录失败: {e}")

        # 5. 最近同步记录
        print_section("5. 最近同步记录 (NM_ALARM_SYNC_STATUS, 最近20条)")

        sql_recent_sync = """
        SELECT * FROM (
            SELECT
                s.ALARM_INST_ID,
                s.SYNC_STATUS,
                s.ZMC_ALARM_STATE,
                s.CREATE_TIME,
                s.UPDATE_TIME,
                s.LAST_PUSH_TIME,
                s.PUSH_COUNT,
                s.ERROR_COUNT
            FROM NM_ALARM_SYNC_STATUS s
            ORDER BY s.UPDATE_TIME DESC NULLS LAST
        ) WHERE ROWNUM <= 20
        """

        try:
            recent_sync = execute_query(conn, sql_recent_sync)
            if recent_sync:
                print(f"\n找到 {len(recent_sync)} 条最近同步记录:")
                headers = ["ALARM_INST_ID", "同步状态", "ZMC状态", "创建时间", "更新时间", "最后推送", "推送次数", "错误次数"]
                rows = [[
                    r['alarm_inst_id'],
                    r['sync_status'],
                    r['zmc_alarm_state'],
                    r['create_time'],
                    r['update_time'],
                    r['last_push_time'],
                    r['push_count'],
                    r['error_count']
                ] for r in recent_sync]
                print(tabulate(rows, headers=headers, tablefmt="grid"))
            else:
                print("⚠️  没有同步记录")
        except Exception as e:
            print(f"⚠️  查询最近同步记录失败: {e}")

        # 6. 告警级别分布
        print_section("6. 活跃告警级别分布")

        sql_level = """
        SELECT
            ALARM_LEVEL,
            CASE ALARM_LEVEL
                WHEN '1' THEN '严重'
                WHEN '2' THEN '重要'
                WHEN '3' THEN '次要'
                WHEN '4' THEN '警告'
                ELSE '未知'
            END AS LEVEL_DESC,
            COUNT(*) AS COUNT
        FROM NM_ALARM_CDR
        WHERE ALARM_STATE = 'U'
        GROUP BY ALARM_LEVEL
        ORDER BY ALARM_LEVEL
        """

        level_stats = execute_query(conn, sql_level)
        if level_stats:
            print("\n活跃告警级别分布:")
            headers = ["级别", "描述", "数量"]
            rows = [[r['alarm_level'], r['level_desc'], r['count']] for r in level_stats]
            print(tabulate(rows, headers=headers, tablefmt="grid"))

        print("\n" + "=" * 80)
        print("✅ 查询完成")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ 查询执行出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()
        print("数据库连接已关闭")


if __name__ == "__main__":
    main()
