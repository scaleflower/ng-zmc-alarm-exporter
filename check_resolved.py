#!/usr/bin/env python3
"""
简单的查询脚本：检查生产环境告警resolved状态
"""

import oracledb
from datetime import datetime

# 生产环境数据库参数
PROD_DB = {
    "host": "192.168.123.239",
    "port": 51015,
    "service_name": "zmc",
    "username": "zmc",
    "password": "Jsmart.868"
}


def main():
    print("=" * 80)
    print(f"🔍 检查生产环境告警 Resolved 状态")
    print(f"时间: {datetime.now()}")
    print("=" * 80)

    dsn = f"{PROD_DB['host']}:{PROD_DB['port']}/{PROD_DB['service_name']}"
    print(f"正在连接: {dsn}")

    try:
        conn = oracledb.connect(
            user=PROD_DB['username'],
            password=PROD_DB['password'],
            dsn=dsn
        )
        print("✅ 连接成功\n")
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return

    cursor = conn.cursor()

    try:
        # 1. 检查 NM_ALARM_SYNC_STATUS 表是否存在
        print("=" * 60)
        print("1. 检查 NM_ALARM_SYNC_STATUS 表")
        print("-" * 60)
        cursor.execute("""
            SELECT COUNT(*) FROM user_tables
            WHERE table_name = 'NM_ALARM_SYNC_STATUS'
        """)
        exists = cursor.fetchone()[0]
        if exists:
            print("✅ NM_ALARM_SYNC_STATUS 表存在")
        else:
            print("❌ NM_ALARM_SYNC_STATUS 表不存在!")
            return

        # 2. 同步状态统计
        print("\n" + "=" * 60)
        print("2. 同步状态分布统计")
        print("-" * 60)
        cursor.execute("""
            SELECT
                SYNC_STATUS,
                ZMC_ALARM_STATE,
                COUNT(*) AS CNT
            FROM NM_ALARM_SYNC_STATUS
            GROUP BY SYNC_STATUS, ZMC_ALARM_STATE
            ORDER BY SYNC_STATUS, ZMC_ALARM_STATE
        """)
        rows = cursor.fetchall()
        print(f"{'同步状态':<15} {'ZMC状态':<12} {'数量':<10}")
        print("-" * 40)
        total_firing = 0
        total_resolved = 0
        for row in rows:
            sync_status, zmc_state, cnt = row
            print(f"{sync_status:<15} {zmc_state or 'NULL':<12} {cnt:<10}")
            if sync_status == 'FIRING':
                total_firing += cnt
            elif sync_status == 'RESOLVED':
                total_resolved += cnt
        print("-" * 40)
        print(f"总计: FIRING={total_firing}, RESOLVED={total_resolved}")

        # 3. 检查最近的 RESOLVED 记录
        print("\n" + "=" * 60)
        print("3. 最近的 RESOLVED 同步记录 (前20条)")
        print("-" * 60)
        cursor.execute("""
            SELECT * FROM (
                SELECT
                    ALARM_INST_ID,
                    SYNC_STATUS,
                    ZMC_ALARM_STATE,
                    UPDATE_TIME,
                    LAST_PUSH_TIME
                FROM NM_ALARM_SYNC_STATUS
                WHERE SYNC_STATUS = 'RESOLVED'
                ORDER BY UPDATE_TIME DESC NULLS LAST
            ) WHERE ROWNUM <= 20
        """)
        resolved_rows = cursor.fetchall()
        if resolved_rows:
            print(f"{'ALARM_INST_ID':<18} {'同步状态':<12} {'ZMC状态':<10} {'更新时间':<22} {'最后推送':<22}")
            print("-" * 90)
            for row in resolved_rows:
                aid, ss, zas, ut, lp = row
                print(f"{aid:<18} {ss:<12} {zas or 'NULL':<10} {str(ut):<22} {str(lp):<22}")
        else:
            print("⚠️ 没有找到 RESOLVED 状态的记录!")

        # 4. 检查 NM_ALARM_CDR 中已恢复的告警 vs 同步状态
        print("\n" + "=" * 60)
        print("4. 已恢复告警 vs 同步状态对比")
        print("-" * 60)

        # CDR 中的状态分布
        cursor.execute("""
            SELECT
                ALARM_STATE,
                CASE ALARM_STATE
                    WHEN 'U' THEN '未确认'
                    WHEN 'A' THEN '自动恢复'
                    WHEN 'M' THEN '手工清除'
                    WHEN 'C' THEN '已确认'
                    ELSE '未知'
                END AS DESC_TEXT,
                COUNT(*) AS CNT
            FROM NM_ALARM_CDR
            GROUP BY ALARM_STATE
            ORDER BY ALARM_STATE
        """)
        cdr_rows = cursor.fetchall()
        print("CDR 告警状态分布:")
        for row in cdr_rows:
            state, desc, cnt = row
            print(f"  {state} ({desc}): {cnt}")

        # 5. 检查已恢复但同步状态仍为 FIRING 的告警
        print("\n" + "=" * 60)
        print("5. 问题诊断: 已恢复但同步未更新的告警")
        print("-" * 60)
        cursor.execute("""
            SELECT COUNT(*) FROM NM_ALARM_SYNC_STATUS s
            JOIN NM_ALARM_CDR c ON s.ALARM_INST_ID = c.ALARM_INST_ID
            WHERE s.SYNC_STATUS = 'FIRING'
            AND c.ALARM_STATE != 'U'
        """)
        mismatch_count = cursor.fetchone()[0]
        print(f"⚠️ 同步状态为 FIRING 但 CDR 已非活跃的告警数: {mismatch_count}")

        if mismatch_count > 0:
            print("\n这些告警需要被推送 RESOLVED 但未被更新:")
            cursor.execute("""
                SELECT * FROM (
                    SELECT
                        s.ALARM_INST_ID,
                        s.SYNC_STATUS,
                        c.ALARM_STATE AS CDR_STATE,
                        c.CLEAR_DATE,
                        s.UPDATE_TIME AS SYNC_UPDATE
                    FROM NM_ALARM_SYNC_STATUS s
                    JOIN NM_ALARM_CDR c ON s.ALARM_INST_ID = c.ALARM_INST_ID
                    WHERE s.SYNC_STATUS = 'FIRING'
                    AND c.ALARM_STATE != 'U'
                    ORDER BY c.CLEAR_DATE DESC NULLS LAST
                ) WHERE ROWNUM <= 20
            """)
            mismatch_rows = cursor.fetchall()
            print(f"{'ALARM_INST_ID':<18} {'同步状态':<12} {'CDR状态':<10} {'清除时间':<22} {'同步更新':<22}")
            print("-" * 90)
            for row in mismatch_rows:
                aid, ss, cs, cd, su = row
                print(f"{aid:<18} {ss:<12} {cs:<10} {str(cd):<22} {str(su):<22}")

        # 6. 最近更新的同步记录
        print("\n" + "=" * 60)
        print("6. 最近更新的同步记录 (无论状态)")
        print("-" * 60)
        cursor.execute("""
            SELECT * FROM (
                SELECT
                    ALARM_INST_ID,
                    SYNC_STATUS,
                    ZMC_ALARM_STATE,
                    UPDATE_TIME,
                    LAST_PUSH_TIME,
                    PUSH_COUNT
                FROM NM_ALARM_SYNC_STATUS
                ORDER BY UPDATE_TIME DESC NULLS LAST
            ) WHERE ROWNUM <= 15
        """)
        recent_rows = cursor.fetchall()
        print(f"{'ALARM_INST_ID':<18} {'同步状态':<12} {'ZMC状态':<10} {'更新时间':<22} {'推送次数':<8}")
        print("-" * 75)
        for row in recent_rows:
            aid, ss, zas, ut, lp, pc = row
            print(f"{aid:<18} {ss:<12} {zas or 'NULL':<10} {str(ut):<22} {pc or 0:<8}")

        print("\n" + "=" * 80)
        print("✅ 查询完成")

    except Exception as e:
        print(f"❌ 查询错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cursor.close()
        conn.close()
        print("数据库连接已关闭")


if __name__ == "__main__":
    main()
