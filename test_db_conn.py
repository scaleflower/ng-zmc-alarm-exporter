#!/usr/bin/env python3
"""Simple database connection test"""

import oracledb
import socket

# 生产环境数据库参数 (通过映射访问)
PROD_DB = {
    "host": "192.168.123.239",
    "port": 51015,
    "service_name": "zmc",
    "username": "zmc",
    "password": "Jsmart.868"
}

# 需要调查的告警 IDs
ALERT_IDS = [618103769009, 617556899009]

def test_network():
    """测试网络连接"""
    print(f"测试网络连接到 {PROD_DB['host']}:{PROD_DB['port']}...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        result = sock.connect_ex((PROD_DB['host'], PROD_DB['port']))
        sock.close()
        if result == 0:
            print("✅ 网络连接成功!")
            return True
        else:
            print(f"❌ 网络连接失败，错误码: {result}")
            return False
    except Exception as e:
        print(f"❌ 网络连接异常: {e}")
        return False

def test_db_connection():
    """测试数据库连接"""
    dsn = f"{PROD_DB['host']}:{PROD_DB['port']}/{PROD_DB['service_name']}"
    print(f"\n连接数据库 (thin mode): {dsn}")
    print(f"用户: {PROD_DB['username']}")

    try:
        conn = oracledb.connect(
            user=PROD_DB['username'],
            password=PROD_DB['password'],
            dsn=dsn
        )
        print("✅ 数据库连接成功!")

        # 简单查询测试
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM DUAL")
        result = cursor.fetchone()
        print(f"✅ 查询测试成功: {result}")

        # 查询特定告警
        print(f"\n查询告警 EVENT_INST_IDs: {ALERT_IDS}")
        ids_str = ",".join(str(id) for id in ALERT_IDS)

        cursor.execute(f"""
            SELECT EVENT_INST_ID, ALARM_INST_ID, ALARM_CODE, ALARM_STATE,
                   HOST_IP, CREATE_DATE
            FROM NM_ALARM_EVENT
            WHERE EVENT_INST_ID IN ({ids_str})
        """)

        rows = cursor.fetchall()
        if rows:
            print(f"✅ 找到 {len(rows)} 条记录:")
            for row in rows:
                print(f"  {row}")
        else:
            print("⚠️ 未找到记录，尝试作为 ALARM_INST_ID 查询...")
            cursor.execute(f"""
                SELECT ALARM_INST_ID, ALARM_CODE, ALARM_STATE, CREATE_DATE
                FROM NM_ALARM_CDR
                WHERE ALARM_INST_ID IN ({ids_str})
            """)
            rows = cursor.fetchall()
            if rows:
                print(f"✅ 在 CDR 中找到 {len(rows)} 条记录:")
                for row in rows:
                    print(f"  {row}")
            else:
                print("⚠️ 未在 CDR 中找到记录")

        cursor.close()
        conn.close()
        return True

    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("生产环境数据库连接测试")
    print("=" * 60)

    if test_network():
        test_db_connection()
    else:
        print("网络不通，跳过数据库连接测试")
