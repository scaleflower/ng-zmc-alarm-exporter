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
        self._thick_mode_initialized = False

    def _init_thick_mode(self) -> None:
        """
        尝试初始化 Oracle Client thick 模式

        thick 模式需要 Oracle Instant Client 库，用于支持：
        - 旧版密码加密 (DPY-3015 错误)
        - 高级安全特性
        - 某些特定的 Oracle 功能
        """
        if self._thick_mode_initialized:
            return

        # 定义可能的 Oracle 客户端库路径
        search_paths = []

        # 1. 首先检查配置的路径
        if self.config.client_lib_dir:
            search_paths.append(self.config.client_lib_dir)

        # 2. 常见的 Oracle 客户端安装路径
        search_paths.extend([
            "/soft/oracle/lib",  # 当前服务器的路径
            "/u01/app/oracle/product/19.0.0/dbhome_1/lib",
            "/u01/app/oracle/product/12.2.0/dbhome_1/lib",
            "/u01/app/oracle/product/12.1.0/dbhome_1/lib",
            "/u01/app/oracle/product/11.2.0/dbhome_1/lib",
            "/opt/oracle/instantclient_21_1",
            "/opt/oracle/instantclient_19_8",
            "/opt/oracle/instantclient_19_19",
            "/opt/oracle/instantclient",
            "/usr/lib/oracle/21/client64/lib",
            "/usr/lib/oracle/19.8/client64/lib",
            "/usr/lib/oracle/12.2/client64/lib",
        ])

        # 3. 检查环境变量
        import os
        oracle_home = os.environ.get("ORACLE_HOME")
        if oracle_home:
            search_paths.insert(0, f"{oracle_home}/lib")

        ld_library_path = os.environ.get("LD_LIBRARY_PATH", "")
        for path in ld_library_path.split(":"):
            if path and "oracle" in path.lower():
                search_paths.insert(0, path)

        # 尝试每个路径
        for lib_dir in search_paths:
            if not lib_dir:
                continue
            try:
                import os.path
                # 检查目录是否存在且包含 libclntsh.so
                if os.path.isdir(lib_dir):
                    libclntsh_path = os.path.join(lib_dir, "libclntsh.so")
                    if os.path.exists(libclntsh_path):
                        oracledb.init_oracle_client(lib_dir=lib_dir)
                        self._thick_mode_initialized = True
                        logger.info(f"Oracle thick mode initialized with client lib: {lib_dir}")
                        return
            except oracledb.ProgrammingError as e:
                if "already initialized" in str(e).lower():
                    self._thick_mode_initialized = True
                    logger.info("Oracle thick mode was already initialized")
                    return
                logger.debug(f"Failed to init thick mode with {lib_dir}: {e}")
            except Exception as e:
                logger.debug(f"Failed to init thick mode with {lib_dir}: {e}")

        logger.warning(
            "Oracle thick mode not available. If you encounter DPY-3015 errors, "
            "please set ZMC_ORACLE_CLIENT_LIB_DIR to your Oracle Instant Client path"
        )

    def init_pool(self) -> None:
        """初始化连接池"""
        if self._pool is not None:
            return

        logger.info(
            f"Initializing Oracle connection pool: {self.config.host}:{self.config.port}/{self.config.service_name}"
        )

        # 尝试启用 thick 模式以支持旧版密码加密
        self._init_thick_mode()

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

    def health_check(self) -> bool:
        """
        检查数据库连接健康状态

        Returns:
            True 如果连接正常，False 如果连接失败
        """
        try:
            if self._pool is None:
                return False

            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM DUAL")
                cursor.fetchone()
                cursor.close()
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False

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
    #
    # 架构说明：以 NM_ALARM_CDR（告警汇总表）为核心
    # - NM_ALARM_CDR: 每个告警源唯一一条记录，记录告警当前状态
    # - NM_ALARM_EVENT: 告警流水日志，用于获取详细信息
    # - 同步状态表以 ALARM_INST_ID 为主键关联
    #

    def get_active_alarms(self, batch_size: int = 100) -> List[Dict]:
        """
        获取活跃告警（基于 NM_ALARM_CDR）

        从告警汇总表查询 ALARM_STATE = 'U'（未确认）的活跃告警，
        JOIN 最新的告警事件获取详细信息。

        Args:
            batch_size: 批处理大小

        Returns:
            活跃告警列表
        """
        sql = """
        SELECT * FROM (
            SELECT
                -- 告警汇总信息（核心）
                c.ALARM_INST_ID,
                c.ALARM_CODE,
                c.APP_ENV_ID,
                c.RES_INST_ID,
                c.ALARM_STATE,
                c.ALARM_LEVEL,
                c.TOTAL_ALARM,
                c.CREATE_DATE AS CDR_CREATE_DATE,
                c.RESET_DATE,
                c.CLEAR_DATE,
                c.CONFIRM_DATE,
                c.CLEAR_REASON,

                -- 最新告警事件详情（通过子查询获取最新一条）
                e.EVENT_INST_ID,
                e.EVENT_TIME,
                e.CREATE_DATE AS EVENT_CREATE_DATE,
                e.DETAIL_INFO,
                e.DATA_1, e.DATA_2, e.DATA_3, e.DATA_4, e.DATA_5,
                e.DATA_6, e.DATA_7, e.DATA_8, e.DATA_9, e.DATA_10,
                e.TASK_TYPE,
                e.RES_INST_TYPE,

                -- 告警码详情
                acl.ALARM_NAME,
                acl.FAULT_REASON,
                acl.DEAL_SUGGEST,
                acl.WARN_LEVEL AS DEFAULT_WARN_LEVEL,

                -- 主机信息
                d.DEVICE_ID,
                d.DEVICE_NAME AS HOST_NAME,
                d.IP_ADDR AS HOST_IP,
                d.DEVICE_MODEL,

                -- 应用信息
                ae.APP_NAME,
                ae.USERNAME AS APP_USER,

                -- 业务域信息
                sd.DOMAIN_ID,
                sd.DOMAIN_NAME AS BUSINESS_DOMAIN,
                sd.DOMAIN_TYPE,
                CASE sd.DOMAIN_TYPE
                    WHEN 'A' THEN 'Production'
                    WHEN 'T' THEN 'Test'
                    WHEN 'D' THEN 'DR'
                    ELSE 'Unknown'
                END AS ENVIRONMENT

            FROM NM_ALARM_CDR c

            -- 获取该告警的最新事件记录
            LEFT JOIN (
                SELECT e1.*
                FROM NM_ALARM_EVENT e1
                WHERE e1.EVENT_INST_ID = (
                    SELECT MAX(e2.EVENT_INST_ID)
                    FROM NM_ALARM_EVENT e2
                    WHERE e2.ALARM_CODE = e1.ALARM_CODE
                      AND e2.APP_ENV_ID = e1.APP_ENV_ID
                      AND e2.RES_INST_ID = e1.RES_INST_ID
                      AND e2.RESET_FLAG = '1'
                )
            ) e ON c.ALARM_CODE = e.ALARM_CODE
                AND c.APP_ENV_ID = e.APP_ENV_ID
                AND c.RES_INST_ID = e.RES_INST_ID

            -- 关联告警码库
            LEFT JOIN NM_ALARM_CODE_LIB acl ON c.ALARM_CODE = acl.ALARM_CODE

            -- 关联应用环境
            LEFT JOIN APP_ENV ae ON c.APP_ENV_ID = ae.APP_ENV_ID

            -- 关联设备表
            LEFT JOIN DEVICE d ON ae.DEVICE_ID = d.DEVICE_ID

            -- 关联业务域表
            LEFT JOIN SYS_DOMAIN sd ON ae.SYS_DOMAIN_ID = sd.DOMAIN_ID

            WHERE c.ALARM_STATE = 'U'  -- 只查询活跃告警
              AND NOT EXISTS (
                  SELECT 1 FROM NM_ALARM_SYNC_STATUS s
                  WHERE s.ALARM_INST_ID = c.ALARM_INST_ID
              )
            ORDER BY c.CREATE_DATE ASC
        ) WHERE ROWNUM <= :batch_size
        """
        return self.execute_query(sql, {"batch_size": batch_size})

    def get_new_alarms(self, history_hours: int = 24, batch_size: int = 100) -> List[Dict]:
        """
        获取新产生的告警（兼容旧接口，内部调用 get_active_alarms）

        Args:
            history_hours: 历史回溯时长（此参数在新架构中已弱化，因为基于 CDR 状态过滤）
            batch_size: 批处理大小

        Returns:
            告警列表
        """
        # 新架构下，直接查询活跃告警，不再依赖时间窗口
        # 因为 NM_ALARM_CDR.ALARM_STATE = 'U' 已经表示告警仍然活跃
        return self.get_active_alarms(batch_size=batch_size)

    def get_refired_alarms(self, batch_size: int = 100) -> List[Dict]:
        """
        获取重新触发的告警（基于 NM_ALARM_CDR）

        检测曾经同步过但已恢复，现在又重新变为活跃状态的告警：
        - SYNC_STATUS = 'RESOLVED' 但 ALARM_STATE = 'U'

        这解决了历史告警重复出现时漏报的问题。
        """
        sql = """
        SELECT * FROM (
            SELECT
                -- 同步状态信息
                s.SYNC_ID,
                s.ALARM_INST_ID,
                s.EVENT_INST_ID AS OLD_EVENT_INST_ID,
                s.SYNC_STATUS,
                s.ZMC_ALARM_STATE AS OLD_ZMC_STATE,
                s.PUSH_COUNT,

                -- 告警汇总信息（核心）
                c.ALARM_CODE,
                c.APP_ENV_ID,
                c.RES_INST_ID,
                c.ALARM_STATE AS NEW_ZMC_STATE,
                c.ALARM_LEVEL,
                c.TOTAL_ALARM,
                c.CREATE_DATE AS CDR_CREATE_DATE,
                c.RESET_DATE,
                c.CLEAR_DATE,
                c.CONFIRM_DATE,
                c.CLEAR_REASON,

                -- 最新告警事件详情
                e.EVENT_INST_ID,
                e.EVENT_TIME,
                e.CREATE_DATE AS EVENT_CREATE_DATE,
                e.DETAIL_INFO,
                e.DATA_1, e.DATA_2, e.DATA_3, e.DATA_4, e.DATA_5,
                e.DATA_6, e.DATA_7, e.DATA_8, e.DATA_9, e.DATA_10,
                e.TASK_TYPE,
                e.RES_INST_TYPE,

                -- 告警码详情
                acl.ALARM_NAME,
                acl.FAULT_REASON,
                acl.DEAL_SUGGEST,
                acl.WARN_LEVEL AS DEFAULT_WARN_LEVEL,

                -- 主机信息
                d.DEVICE_ID,
                d.DEVICE_NAME AS HOST_NAME,
                d.IP_ADDR AS HOST_IP,
                d.DEVICE_MODEL,

                -- 应用信息
                ae.APP_NAME,
                ae.USERNAME AS APP_USER,

                -- 业务域信息
                sd.DOMAIN_ID,
                sd.DOMAIN_NAME AS BUSINESS_DOMAIN,
                sd.DOMAIN_TYPE,
                CASE sd.DOMAIN_TYPE
                    WHEN 'A' THEN 'Production'
                    WHEN 'T' THEN 'Test'
                    WHEN 'D' THEN 'DR'
                    ELSE 'Unknown'
                END AS ENVIRONMENT

            FROM NM_ALARM_SYNC_STATUS s

            -- 关联告警汇总表（核心）
            JOIN NM_ALARM_CDR c ON s.ALARM_INST_ID = c.ALARM_INST_ID

            -- 获取该告警的最新事件记录
            LEFT JOIN (
                SELECT e1.*
                FROM NM_ALARM_EVENT e1
                WHERE e1.EVENT_INST_ID = (
                    SELECT MAX(e2.EVENT_INST_ID)
                    FROM NM_ALARM_EVENT e2
                    WHERE e2.ALARM_CODE = e1.ALARM_CODE
                      AND e2.APP_ENV_ID = e1.APP_ENV_ID
                      AND e2.RES_INST_ID = e1.RES_INST_ID
                      AND e2.RESET_FLAG = '1'
                )
            ) e ON c.ALARM_CODE = e.ALARM_CODE
                AND c.APP_ENV_ID = e.APP_ENV_ID
                AND c.RES_INST_ID = e.RES_INST_ID

            -- 关联告警码库
            LEFT JOIN NM_ALARM_CODE_LIB acl ON c.ALARM_CODE = acl.ALARM_CODE

            -- 关联应用环境
            LEFT JOIN APP_ENV ae ON c.APP_ENV_ID = ae.APP_ENV_ID

            -- 关联设备表
            LEFT JOIN DEVICE d ON ae.DEVICE_ID = d.DEVICE_ID

            -- 关联业务域表
            LEFT JOIN SYS_DOMAIN sd ON ae.SYS_DOMAIN_ID = sd.DOMAIN_ID

            WHERE s.SYNC_STATUS = 'RESOLVED'           -- 之前已恢复
              AND s.ZMC_ALARM_STATE IN ('A', 'C', 'M') -- 确实是从非活跃状态
              AND c.ALARM_STATE = 'U'                  -- 但现在又活跃了
            ORDER BY c.CREATE_DATE ASC
        ) WHERE ROWNUM <= :batch_size
        """
        return self.execute_query(sql, {"batch_size": batch_size})

    def get_status_changed_alarms(self) -> List[Dict]:
        """
        获取状态变更的告警（基于 NM_ALARM_CDR）

        直接检测 NM_ALARM_CDR.ALARM_STATE 是否发生变化：
        - U -> A: 自动恢复
        - U -> M: 手工清除
        - U -> C: 已确认

        Returns full alarm details for RESOLVED messages to include in notifications.
        """
        sql = """
        SELECT
            -- Sync status info
            s.SYNC_ID,
            s.ALARM_INST_ID,
            s.EVENT_INST_ID,
            s.SYNC_STATUS,
            s.ZMC_ALARM_STATE AS OLD_ZMC_STATE,
            s.SILENCE_ID,
            s.PUSH_COUNT,

            -- CDR status info
            c.ALARM_STATE AS NEW_ZMC_STATE,
            c.ALARM_CODE,
            c.ALARM_LEVEL,
            c.RESET_DATE,
            c.CLEAR_DATE,
            c.CONFIRM_DATE,
            c.CLEAR_REASON,
            c.TOTAL_ALARM,

            -- Event details (full info for RESOLVED messages)
            e.EVENT_INST_ID AS LATEST_EVENT_ID,
            e.EVENT_TIME,
            e.CREATE_DATE AS EVENT_CREATE_DATE,
            e.DETAIL_INFO,
            e.RES_INST_TYPE,
            e.RES_INST_ID,
            e.APP_ENV_ID,
            e.TASK_TYPE,
            e.DATA_1, e.DATA_2, e.DATA_3, e.DATA_4, e.DATA_5,
            e.DATA_6, e.DATA_7, e.DATA_8, e.DATA_9, e.DATA_10,

            -- Alarm code library info
            acl.ALARM_NAME,
            acl.FAULT_REASON,
            acl.DEAL_SUGGEST,
            acl.WARN_LEVEL AS DEFAULT_WARN_LEVEL,

            -- Device/Host info
            d.DEVICE_NAME AS HOST_NAME,
            d.IP_ADDR AS HOST_IP,
            d.DEVICE_MODEL,

            -- App environment info
            ae.APP_NAME,
            ae.USERNAME AS APP_USER,

            -- Business domain info
            sd.DOMAIN_NAME AS BUSINESS_DOMAIN,
            CASE sd.DOMAIN_TYPE
                WHEN 'A' THEN 'Production'
                WHEN 'T' THEN 'Test'
                WHEN 'D' THEN 'DR'
                ELSE 'Unknown'
            END AS ENVIRONMENT

        FROM NM_ALARM_SYNC_STATUS s

        -- Join CDR table (core)
        JOIN NM_ALARM_CDR c ON s.ALARM_INST_ID = c.ALARM_INST_ID

        -- Get latest event record for full details
        LEFT JOIN (
            SELECT e1.*
            FROM NM_ALARM_EVENT e1
            WHERE e1.EVENT_INST_ID = (
                SELECT MAX(e2.EVENT_INST_ID)
                FROM NM_ALARM_EVENT e2
                WHERE e2.ALARM_CODE = e1.ALARM_CODE
                  AND e2.APP_ENV_ID = e1.APP_ENV_ID
                  AND e2.RES_INST_ID = e1.RES_INST_ID
            )
        ) e ON c.ALARM_CODE = e.ALARM_CODE
            AND c.APP_ENV_ID = e.APP_ENV_ID
            AND c.RES_INST_ID = e.RES_INST_ID

        -- Join alarm code library
        LEFT JOIN NM_ALARM_CODE_LIB acl ON c.ALARM_CODE = acl.ALARM_CODE

        -- Join app environment
        LEFT JOIN APP_ENV ae ON c.APP_ENV_ID = ae.APP_ENV_ID

        -- Join device table
        LEFT JOIN DEVICE d ON ae.DEVICE_ID = d.DEVICE_ID

        -- Join business domain table
        LEFT JOIN SYS_DOMAIN sd ON ae.SYS_DOMAIN_ID = sd.DOMAIN_ID

        WHERE s.SYNC_STATUS IN ('FIRING', 'PENDING')
          AND c.ALARM_STATE != NVL(s.ZMC_ALARM_STATE, 'U')  -- Status changed
        """
        return self.execute_query(sql)

    def get_heartbeat_alarms(self, heartbeat_interval: int = 120) -> List[Dict]:
        """
        获取需要心跳保活的活跃告警（基于 NM_ALARM_CDR）

        查询 SYNC_STATUS = 'FIRING' 且超过心跳间隔未推送的告警
        """
        sql = """
        SELECT
            s.SYNC_ID,
            s.ALARM_INST_ID,
            s.EVENT_INST_ID,
            s.LAST_PUSH_TIME,
            s.PUSH_COUNT,

            -- CDR 信息
            c.ALARM_CODE,
            c.ALARM_LEVEL,
            c.ALARM_STATE,

            -- 最新事件详情
            e.EVENT_TIME,
            e.DETAIL_INFO,

            -- 告警码详情
            acl.ALARM_NAME,

            -- 主机信息
            d.DEVICE_NAME AS HOST_NAME,
            d.IP_ADDR AS HOST_IP,

            -- 应用信息
            ae.APP_NAME,

            -- 业务域信息
            sd.DOMAIN_NAME AS BUSINESS_DOMAIN,
            CASE sd.DOMAIN_TYPE
                WHEN 'A' THEN 'Production'
                WHEN 'T' THEN 'Test'
                WHEN 'D' THEN 'DR'
                ELSE 'Unknown'
            END AS ENVIRONMENT

        FROM NM_ALARM_SYNC_STATUS s

        -- 关联告警汇总表
        JOIN NM_ALARM_CDR c ON s.ALARM_INST_ID = c.ALARM_INST_ID

        -- 获取最新事件记录
        LEFT JOIN (
            SELECT e1.*
            FROM NM_ALARM_EVENT e1
            WHERE e1.EVENT_INST_ID = (
                SELECT MAX(e2.EVENT_INST_ID)
                FROM NM_ALARM_EVENT e2
                WHERE e2.ALARM_CODE = e1.ALARM_CODE
                  AND e2.APP_ENV_ID = e1.APP_ENV_ID
                  AND e2.RES_INST_ID = e1.RES_INST_ID
            )
        ) e ON c.ALARM_CODE = e.ALARM_CODE
            AND c.APP_ENV_ID = e.APP_ENV_ID
            AND c.RES_INST_ID = e.RES_INST_ID

        -- 关联告警码库
        LEFT JOIN NM_ALARM_CODE_LIB acl ON c.ALARM_CODE = acl.ALARM_CODE

        -- 关联应用环境
        LEFT JOIN APP_ENV ae ON c.APP_ENV_ID = ae.APP_ENV_ID

        -- 关联设备表
        LEFT JOIN DEVICE d ON ae.DEVICE_ID = d.DEVICE_ID

        -- 关联业务域表
        LEFT JOIN SYS_DOMAIN sd ON ae.SYS_DOMAIN_ID = sd.DOMAIN_ID

        WHERE s.SYNC_STATUS = 'FIRING'
          AND c.ALARM_STATE = 'U'  -- 确保 CDR 中仍然是活跃状态
          AND (s.LAST_PUSH_TIME IS NULL
               OR s.LAST_PUSH_TIME < SYSTIMESTAMP - NUMTODSINTERVAL(:heartbeat_interval, 'SECOND'))
        """
        return self.execute_query(sql, {"heartbeat_interval": heartbeat_interval})

    def get_silences_to_remove(self) -> List[Dict]:
        """
        获取需要删除静默的告警（基于 NM_ALARM_CDR）

        查询 SYNC_STATUS = 'SILENCED' 但 CDR 中已恢复（A/C）的告警
        """
        sql = """
        SELECT
            s.SYNC_ID,
            s.ALARM_INST_ID,
            s.EVENT_INST_ID,
            s.SILENCE_ID,
            s.ZMC_ALARM_STATE,
            c.ALARM_STATE AS CURRENT_ZMC_STATE,
            c.RESET_DATE,
            c.CLEAR_DATE
        FROM NM_ALARM_SYNC_STATUS s
        JOIN NM_ALARM_CDR c ON s.ALARM_INST_ID = c.ALARM_INST_ID
        WHERE s.SYNC_STATUS = 'SILENCED'
          AND s.SILENCE_ID IS NOT NULL
          AND c.ALARM_STATE IN ('A', 'C')  -- 已自动恢复或已确认
        """
        return self.execute_query(sql)

    def insert_sync_status(self, alarm_inst_id: int, event_inst_id: Optional[int],
                           sync_status: str, zmc_alarm_state: Optional[str]) -> int:
        """
        插入同步状态记录（以 ALARM_INST_ID 为核心）

        Args:
            alarm_inst_id: 告警汇总ID（必填，作为唯一标识）
            event_inst_id: 告警事件ID（可选，记录最新事件）
            sync_status: 同步状态
            zmc_alarm_state: ZMC 告警状态

        Returns:
            影响的行数
        """
        sql = """
        INSERT INTO NM_ALARM_SYNC_STATUS (
            SYNC_ID, ALARM_INST_ID, EVENT_INST_ID, SYNC_STATUS,
            ZMC_ALARM_STATE, CREATE_TIME, UPDATE_TIME,
            PUSH_COUNT, LAST_PUSH_TIME
        ) VALUES (
            SEQ_ALARM_SYNC_STATUS.NEXTVAL, :alarm_inst_id, :event_inst_id,
            :sync_status, :zmc_alarm_state, SYSTIMESTAMP, SYSTIMESTAMP,
            1, SYSTIMESTAMP
        )
        """
        return self.execute_update(sql, {
            "alarm_inst_id": alarm_inst_id,
            "event_inst_id": event_inst_id,
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
