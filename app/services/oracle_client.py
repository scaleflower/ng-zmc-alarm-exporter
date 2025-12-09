"""
Oracle 数据库客户端

提供与 ZMC Oracle 数据库的连接和查询功能。
"""

import logging
from typing import Any, Dict, List, Optional
from contextlib import contextmanager
from datetime import datetime

import oracledb

from app.config import OracleConfig, settings

logger = logging.getLogger(__name__)


class OracleClient:
    """Oracle 数据库客户端"""

    def __init__(self, config: Optional[OracleConfig] = None):
        """
        初始化 Oracle 客户端

        Args:
            config: Oracle 配置，默认使用全局配置
        """
        self.config = config or settings.oracle
        self._pool: Optional[oracledb.ConnectionPool] = None

    def init_pool(self) -> None:
        """初始化连接池"""
        if self._pool is not None:
            return

        logger.info(
            f"Initializing Oracle connection pool: {self.config.host}:{self.config.port}/{self.config.service_name}"
        )

        try:
            # 使用 thin 模式，无需 Oracle Client
            oracledb.init_oracle_client()
        except Exception:
            # thin 模式不需要初始化 client
            pass

        self._pool = oracledb.create_pool(
            user=self.config.username,
            password=self.config.password,
            dsn=self.config.dsn,
            min=self.config.pool_min,
            max=self.config.pool_max,
            increment=1,
            timeout=self.config.timeout,
            getmode=oracledb.POOL_GETMODE_WAIT,
        )

        logger.info("Oracle connection pool initialized successfully")

    def close_pool(self) -> None:
        """关闭连接池"""
        if self._pool:
            self._pool.close()
            self._pool = None
            logger.info("Oracle connection pool closed")

    @contextmanager
    def get_connection(self):
        """获取数据库连接（上下文管理器）"""
        if self._pool is None:
            self.init_pool()

        conn = self._pool.acquire()
        try:
            yield conn
        finally:
            self._pool.release(conn)

    def execute_query(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
        fetch_one: bool = False
    ) -> List[Dict[str, Any]]:
        """
        执行查询并返回结果

        Args:
            sql: SQL 查询语句
            params: 查询参数
            fetch_one: 是否只返回一条记录

        Returns:
            查询结果列表，每条记录为字典格式
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(sql, params or {})

                # 获取列名
                columns = [col[0].lower() for col in cursor.description]

                if fetch_one:
                    row = cursor.fetchone()
                    if row:
                        return [dict(zip(columns, row))]
                    return []

                rows = cursor.fetchall()
                return [dict(zip(columns, row)) for row in rows]

            finally:
                cursor.close()

    def execute_update(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
        commit: bool = True
    ) -> int:
        """
        执行更新语句

        Args:
            sql: SQL 更新语句
            params: 更新参数
            commit: 是否自动提交

        Returns:
            影响的行数
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(sql, params or {})
                rowcount = cursor.rowcount

                if commit:
                    conn.commit()

                return rowcount

            except Exception as e:
                conn.rollback()
                raise e
            finally:
                cursor.close()

    def execute_many(
        self,
        sql: str,
        params_list: List[Dict[str, Any]],
        commit: bool = True
    ) -> int:
        """
        批量执行更新语句

        Args:
            sql: SQL 更新语句
            params_list: 参数列表
            commit: 是否自动提交

        Returns:
            影响的总行数
        """
        if not params_list:
            return 0

        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.executemany(sql, params_list)
                rowcount = cursor.rowcount

                if commit:
                    conn.commit()

                return rowcount

            except Exception as e:
                conn.rollback()
                raise e
            finally:
                cursor.close()

    def get_sequence_value(self, sequence_name: str) -> int:
        """
        获取序列的下一个值

        Args:
            sequence_name: 序列名称

        Returns:
            序列值
        """
        sql = f"SELECT {sequence_name}.NEXTVAL FROM DUAL"
        result = self.execute_query(sql, fetch_one=True)
        return result[0]["nextval"] if result else 0

    def test_connection(self) -> bool:
        """
        测试数据库连接

        Returns:
            连接是否成功
        """
        try:
            result = self.execute_query("SELECT 1 FROM DUAL", fetch_one=True)
            return len(result) > 0
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False

    # ========== 告警相关查询方法 ==========

    def get_new_alarms(self, history_hours: int = 24, batch_size: int = 100) -> List[Dict]:
        """
        获取新产生的告警（尚未同步）

        Args:
            history_hours: 历史回溯时长
            batch_size: 批处理大小

        Returns:
            告警列表
        """
        sql = """
        SELECT
            e.EVENT_INST_ID, e.EVENT_TIME, e.CREATE_DATE, e.ALARM_CODE,
            e.ALARM_LEVEL, e.RESET_FLAG, e.TASK_TYPE, e.RES_INST_TYPE,
            e.RES_INST_ID, e.APP_ENV_ID, e.DETAIL_INFO,
            e.DATA_1, e.DATA_2, e.DATA_3, e.DATA_4, e.DATA_5,
            e.DATA_6, e.DATA_7, e.DATA_8, e.DATA_9, e.DATA_10,
            acl.ALARM_NAME, acl.FAULT_REASON, acl.DEAL_SUGGEST,
            d.DEVICE_NAME AS HOST_NAME, d.IP_ADDR AS HOST_IP,
            ae.APP_NAME,
            sd.DOMAIN_NAME AS BUSINESS_DOMAIN,
            CASE sd.DOMAIN_TYPE
                WHEN 'A' THEN 'Production'
                WHEN 'T' THEN 'Test'
                WHEN 'D' THEN 'DR'
                ELSE 'Unknown'
            END AS ENVIRONMENT
        FROM NM_ALARM_EVENT e
        LEFT JOIN NM_ALARM_CODE_LIB acl ON e.ALARM_CODE = acl.ALARM_CODE
        LEFT JOIN APP_ENV ae ON e.APP_ENV_ID = ae.APP_ENV_ID
        LEFT JOIN DEVICE d ON ae.DEVICE_ID = d.DEVICE_ID
        LEFT JOIN SYS_DOMAIN sd ON ae.SYS_DOMAIN_ID = sd.DOMAIN_ID
        WHERE e.RESET_FLAG = '1'
          AND NOT EXISTS (
              SELECT 1 FROM NM_ALARM_SYNC_STATUS s
              WHERE s.EVENT_INST_ID = e.EVENT_INST_ID
          )
          AND e.CREATE_DATE > SYSDATE - INTERVAL :history_hours HOUR
        ORDER BY e.CREATE_DATE ASC
        FETCH FIRST :batch_size ROWS ONLY
        """
        return self.execute_query(sql, {"history_hours": history_hours, "batch_size": batch_size})

    def get_status_changed_alarms(self) -> List[Dict]:
        """获取状态变更的告警"""
        sql = """
        SELECT
            s.SYNC_ID, s.EVENT_INST_ID, s.ALARM_INST_ID, s.SYNC_STATUS,
            s.ZMC_ALARM_STATE AS OLD_ZMC_STATE, s.SILENCE_ID,
            c.ALARM_STATE AS NEW_ZMC_STATE,
            c.RESET_DATE, c.CLEAR_DATE, c.CONFIRM_DATE, c.CLEAR_REASON,
            e.ALARM_CODE, e.ALARM_LEVEL, e.EVENT_TIME, e.DETAIL_INFO,
            acl.ALARM_NAME,
            d.DEVICE_NAME AS HOST_NAME, d.IP_ADDR AS HOST_IP,
            ae.APP_NAME,
            sd.DOMAIN_NAME AS BUSINESS_DOMAIN
        FROM NM_ALARM_SYNC_STATUS s
        JOIN NM_ALARM_EVENT e ON s.EVENT_INST_ID = e.EVENT_INST_ID
        LEFT JOIN NM_ALARM_CDR c ON e.ALARM_CODE = c.ALARM_CODE
                                 AND e.APP_ENV_ID = c.APP_ENV_ID
                                 AND e.RES_INST_ID = c.RES_INST_ID
        LEFT JOIN NM_ALARM_CODE_LIB acl ON e.ALARM_CODE = acl.ALARM_CODE
        LEFT JOIN APP_ENV ae ON e.APP_ENV_ID = ae.APP_ENV_ID
        LEFT JOIN DEVICE d ON ae.DEVICE_ID = d.DEVICE_ID
        LEFT JOIN SYS_DOMAIN sd ON ae.SYS_DOMAIN_ID = sd.DOMAIN_ID
        WHERE s.SYNC_STATUS IN ('FIRING', 'PENDING')
          AND c.ALARM_STATE IS NOT NULL
          AND c.ALARM_STATE != NVL(s.ZMC_ALARM_STATE, 'U')
        """
        return self.execute_query(sql)

    def get_heartbeat_alarms(self, heartbeat_interval: int = 120) -> List[Dict]:
        """获取需要心跳保活的活跃告警"""
        sql = """
        SELECT
            s.SYNC_ID, s.EVENT_INST_ID, s.LAST_PUSH_TIME, s.PUSH_COUNT,
            e.ALARM_CODE, e.ALARM_LEVEL, e.EVENT_TIME, e.DETAIL_INFO,
            acl.ALARM_NAME,
            d.DEVICE_NAME AS HOST_NAME, d.IP_ADDR AS HOST_IP,
            ae.APP_NAME,
            sd.DOMAIN_NAME AS BUSINESS_DOMAIN,
            CASE sd.DOMAIN_TYPE
                WHEN 'A' THEN 'Production'
                WHEN 'T' THEN 'Test'
                WHEN 'D' THEN 'DR'
                ELSE 'Unknown'
            END AS ENVIRONMENT
        FROM NM_ALARM_SYNC_STATUS s
        JOIN NM_ALARM_EVENT e ON s.EVENT_INST_ID = e.EVENT_INST_ID
        LEFT JOIN NM_ALARM_CODE_LIB acl ON e.ALARM_CODE = acl.ALARM_CODE
        LEFT JOIN APP_ENV ae ON e.APP_ENV_ID = ae.APP_ENV_ID
        LEFT JOIN DEVICE d ON ae.DEVICE_ID = d.DEVICE_ID
        LEFT JOIN SYS_DOMAIN sd ON ae.SYS_DOMAIN_ID = sd.DOMAIN_ID
        WHERE s.SYNC_STATUS = 'FIRING'
          AND (s.LAST_PUSH_TIME IS NULL
               OR s.LAST_PUSH_TIME < SYSTIMESTAMP - NUMTODSINTERVAL(:heartbeat_interval, 'SECOND'))
        """
        return self.execute_query(sql, {"heartbeat_interval": heartbeat_interval})

    def get_silences_to_remove(self) -> List[Dict]:
        """获取需要删除静默的告警"""
        sql = """
        SELECT
            s.SYNC_ID, s.EVENT_INST_ID, s.SILENCE_ID, s.ZMC_ALARM_STATE,
            c.ALARM_STATE AS CURRENT_ZMC_STATE,
            c.RESET_DATE, c.CLEAR_DATE
        FROM NM_ALARM_SYNC_STATUS s
        LEFT JOIN NM_ALARM_EVENT e ON s.EVENT_INST_ID = e.EVENT_INST_ID
        LEFT JOIN NM_ALARM_CDR c ON e.ALARM_CODE = c.ALARM_CODE
                                 AND e.APP_ENV_ID = c.APP_ENV_ID
                                 AND e.RES_INST_ID = c.RES_INST_ID
        WHERE s.SYNC_STATUS = 'SILENCED'
          AND s.SILENCE_ID IS NOT NULL
          AND c.ALARM_STATE IN ('A', 'C')
        """
        return self.execute_query(sql)

    def insert_sync_status(self, event_inst_id: int, alarm_inst_id: Optional[int],
                           sync_status: str, zmc_alarm_state: Optional[str]) -> int:
        """插入同步状态记录"""
        sql = """
        INSERT INTO NM_ALARM_SYNC_STATUS (
            SYNC_ID, EVENT_INST_ID, ALARM_INST_ID, SYNC_STATUS,
            ZMC_ALARM_STATE, CREATE_TIME, UPDATE_TIME
        ) VALUES (
            SEQ_ALARM_SYNC_STATUS.NEXTVAL, :event_inst_id, :alarm_inst_id,
            :sync_status, :zmc_alarm_state, SYSTIMESTAMP, SYSTIMESTAMP
        )
        """
        return self.execute_update(sql, {
            "event_inst_id": event_inst_id,
            "alarm_inst_id": alarm_inst_id,
            "sync_status": sync_status,
            "zmc_alarm_state": zmc_alarm_state
        })

    def update_sync_status_success(self, sync_id: int, sync_status: str,
                                    zmc_alarm_state: Optional[str],
                                    am_fingerprint: Optional[str] = None,
                                    silence_id: Optional[str] = None) -> int:
        """更新同步状态（成功）"""
        sql = """
        UPDATE NM_ALARM_SYNC_STATUS
        SET SYNC_STATUS = :sync_status,
            ZMC_ALARM_STATE = :zmc_alarm_state,
            LAST_PUSH_TIME = SYSTIMESTAMP,
            PUSH_COUNT = PUSH_COUNT + 1,
            AM_FINGERPRINT = :am_fingerprint,
            SILENCE_ID = :silence_id,
            ERROR_COUNT = 0,
            LAST_ERROR = NULL,
            UPDATE_TIME = SYSTIMESTAMP
        WHERE SYNC_ID = :sync_id
        """
        return self.execute_update(sql, {
            "sync_id": sync_id,
            "sync_status": sync_status,
            "zmc_alarm_state": zmc_alarm_state,
            "am_fingerprint": am_fingerprint,
            "silence_id": silence_id
        })

    def update_sync_status_error(self, sync_id: int, error_message: str) -> int:
        """更新同步状态（失败）"""
        sql = """
        UPDATE NM_ALARM_SYNC_STATUS
        SET ERROR_COUNT = ERROR_COUNT + 1,
            LAST_ERROR = :error_message,
            UPDATE_TIME = SYSTIMESTAMP
        WHERE SYNC_ID = :sync_id
        """
        return self.execute_update(sql, {
            "sync_id": sync_id,
            "error_message": error_message[:2000]  # 截断到字段长度
        })

    def insert_sync_log(self, log_data: Dict[str, Any]) -> int:
        """插入同步日志"""
        sql = """
        INSERT INTO NM_ALARM_SYNC_LOG (
            LOG_ID, SYNC_BATCH_ID, EVENT_INST_ID, OPERATION,
            OLD_STATUS, NEW_STATUS, REQUEST_URL, REQUEST_METHOD,
            REQUEST_PAYLOAD, RESPONSE_CODE, RESPONSE_BODY,
            ERROR_MESSAGE, DURATION_MS, CREATE_TIME
        ) VALUES (
            SEQ_ALARM_SYNC_LOG.NEXTVAL, :sync_batch_id, :event_inst_id, :operation,
            :old_status, :new_status, :request_url, :request_method,
            :request_payload, :response_code, :response_body,
            :error_message, :duration_ms, SYSTIMESTAMP
        )
        """
        return self.execute_update(sql, log_data)

    def get_sync_statistics(self) -> List[Dict]:
        """获取同步统计信息"""
        sql = """
        SELECT
            SYNC_STATUS,
            COUNT(*) AS ALARM_COUNT,
            MIN(CREATE_TIME) AS EARLIEST_ALARM,
            MAX(UPDATE_TIME) AS LATEST_UPDATE,
            SUM(PUSH_COUNT) AS TOTAL_PUSHES,
            SUM(ERROR_COUNT) AS TOTAL_ERRORS,
            COUNT(CASE WHEN ERROR_COUNT > 0 THEN 1 END) AS ALARMS_WITH_ERRORS
        FROM NM_ALARM_SYNC_STATUS
        GROUP BY SYNC_STATUS
        ORDER BY SYNC_STATUS
        """
        return self.execute_query(sql)

    def get_config(self, config_group: str, config_key: str) -> Optional[str]:
        """获取配置值"""
        sql = """
        SELECT
            CONFIG_VALUE, CONFIG_VALUE_ENC, IS_ENCRYPTED, DEFAULT_VALUE
        FROM NM_ALARM_SYNC_CONFIG
        WHERE CONFIG_GROUP = :config_group AND CONFIG_KEY = :config_key
        """
        result = self.execute_query(sql, {
            "config_group": config_group,
            "config_key": config_key
        }, fetch_one=True)

        if not result:
            return None

        row = result[0]
        if row.get("is_encrypted") == "Y":
            # TODO: 实现解密逻辑
            return row.get("config_value_enc")
        return row.get("config_value") or row.get("default_value")

    def get_label_mappings(self) -> List[Dict]:
        """获取标签映射配置"""
        sql = """
        SELECT
            SOURCE_FIELD, TARGET_LABEL, TRANSFORM_TYPE,
            TRANSFORM_EXPR, LABEL_TYPE
        FROM NM_ALARM_LABEL_MAPPING
        WHERE IS_ENABLED = 'Y'
        ORDER BY LABEL_TYPE, SORT_ORDER
        """
        return self.execute_query(sql)


# 全局客户端实例
oracle_client = OracleClient()
