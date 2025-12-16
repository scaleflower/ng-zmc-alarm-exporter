#!/usr/bin/env python3
"""
查询昨天插入的测试数据
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

    print("=" * 60)
    print("连接数据库...")
    print(f"Host: {settings.oracle.host}:{settings.oracle.port}")
    print(f"Service: {settings.oracle.service_name}")
    print(f"User: {settings.oracle.username}")
    print("=" * 60)

    try:
        client.init_pool()
        print("✅ 数据库连接成功\n")

        # 查询昨天的测试数据
        sql = """
        SELECT
            EVENT_INST_ID,
            EVENT_TIME,
            CREATE_DATE,
            ALARM_CODE,
            ALARM_LEVEL,
            RESET_FLAG,
            RES_INST_TYPE,
            RES_INST_ID,
            APP_ENV_ID,
            DETAIL_INFO
        FROM NM_ALARM_EVENT
        WHERE CREATE_DATE >= TRUNC(SYSDATE - 1)
          AND CREATE_DATE < TRUNC(SYSDATE)
        ORDER BY CREATE_DATE DESC
        """

        print("📋 查询昨天 (CREATE_DATE) 的告警记录...")
        print("-" * 60)

        results = client.execute_query(sql)

        if not results:
            print("⚠️  昨天没有找到告警记录")
            print("\n尝试查询最近2天的记录...")

            sql2 = """
            SELECT
                EVENT_INST_ID,
                EVENT_TIME,
                CREATE_DATE,
                ALARM_CODE,
                ALARM_LEVEL,
                RESET_FLAG,
                RES_INST_TYPE,
                RES_INST_ID,
                APP_ENV_ID,
                DETAIL_INFO
            FROM NM_ALARM_EVENT
            WHERE CREATE_DATE >= SYSDATE - 2
            ORDER BY CREATE_DATE DESC
            FETCH FIRST 10 ROWS ONLY
            """
            results = client.execute_query(sql2)

        if results:
            print(f"\n✅ 找到 {len(results)} 条记录:\n")
            for i, row in enumerate(results, 1):
                print(f"--- 记录 {i} ---")
                for key, value in row.items():
                    print(f"  {key}: {value}")
                print()
        else:
            print("❌ 没有找到任何告警记录")

    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.close_pool()
        print("\n数据库连接已关闭")

if __name__ == "__main__":
    main()
