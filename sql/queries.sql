-- ============================================================================
-- ZMC Alarm Exporter - SQL 查询语句
-- 版本: 1.0.0
-- 描述: 告警数据抽取、状态变更检测、同步管理所需的SQL查询
-- ============================================================================


-- ============================================================================
-- 1. 完整告警信息查询 (包含主机名、IP、业务域等所有关联信息)
-- 用途: 抽取新告警时获取完整的告警上下文信息
-- ============================================================================
-- query_name: get_full_alarm_info
SELECT
    -- ========== 告警事件基础信息 ==========
    e.EVENT_INST_ID,                              -- 告警事件唯一ID
    e.EVENT_TIME,                                 -- 告警发生时间(网元时间)
    e.CREATE_DATE,                                -- 记录创建时间(服务器时间)
    e.ALARM_CODE,                                 -- 告警码
    e.ALARM_LEVEL,                                -- 告警级别: 1-严重, 2-重要, 3-次要, 4-警告
    e.RESET_FLAG,                                 -- 恢复标志: 0-恢复消息, 1-告警消息
    e.TASK_TYPE,                                  -- 任务类型
    e.TASK_ID,                                    -- 任务ID
    e.RES_INST_TYPE,                              -- 资源类型: DEVICE/APP_SERVICE/APP_PROCESS
    e.RES_INST_ID,                                -- 资源实例ID
    e.APP_ENV_ID,                                 -- 应用环境ID
    e.DETAIL_INFO,                                -- 告警详细信息
    e.DATA_1, e.DATA_2, e.DATA_3, e.DATA_4, e.DATA_5,
    e.DATA_6, e.DATA_7, e.DATA_8, e.DATA_9, e.DATA_10,

    -- ========== 告警汇总状态 (来自 NM_ALARM_CDR) ==========
    c.ALARM_INST_ID,                              -- 告警汇总ID
    c.ALARM_STATE,                                -- 告警状态: U-未确认, A-自动恢复, M-手工清除, C-已确认
    c.RESET_DATE,                                 -- 自动恢复时间
    c.CLEAR_DATE,                                 -- 手工清除时间
    c.CONFIRM_DATE,                               -- 确认时间
    c.TOTAL_ALARM,                                -- 累计告警次数
    c.CLEAR_REASON,                               -- 清除原因

    -- ========== 告警码详情 (来自 NM_ALARM_CODE_LIB) ==========
    acl.ALARM_NAME,                               -- 告警名称
    acl.ALARM_TYPE AS ALARM_TYPE_CODE,            -- 告警类型代码
    CASE acl.ALARM_TYPE
        WHEN '0' THEN 'Communication'
        WHEN '1' THEN 'ProcessingError'
        WHEN '2' THEN 'QualityOfService'
        WHEN '3' THEN 'Equipment'
        WHEN '4' THEN 'Environmental'
        ELSE 'Unknown'
    END AS ALARM_TYPE_NAME,                       -- 告警类型名称
    acl.WARN_LEVEL AS DEFAULT_WARN_LEVEL,         -- 默认告警级别
    acl.FAULT_REASON,                             -- 故障原因
    acl.DEAL_SUGGEST,                             -- 处理建议

    -- ========== 设备/主机信息 (来自 DEVICE) ==========
    d.DEVICE_ID,                                  -- 设备ID
    d.DEVICE_NAME AS HOST_NAME,                   -- 主机名
    d.IP_ADDR AS HOST_IP,                         -- 主机IP地址
    d.DEVICE_MODEL,                               -- 设备型号

    -- ========== 应用环境信息 (来自 APP_ENV) ==========
    ae.APP_NAME,                                  -- 应用名称
    ae.USERNAME AS APP_USER,                      -- 应用用户

    -- ========== 业务域信息 (来自 SYS_DOMAIN) ==========
    sd.DOMAIN_ID,                                 -- 业务域ID
    sd.DOMAIN_NAME AS BUSINESS_DOMAIN,            -- 业务域名称
    sd.DOMAIN_TYPE,                               -- 域类型代码
    CASE sd.DOMAIN_TYPE
        WHEN 'A' THEN 'Production'
        WHEN 'T' THEN 'Test'
        WHEN 'D' THEN 'DR'
        ELSE 'Unknown'
    END AS ENVIRONMENT,                           -- 环境类型名称

    -- ========== 应用服务信息 (当 RES_INST_TYPE = 'APP_SERVICE') ==========
    asv.APP_SERVICE_NAME,                         -- 应用服务名称
    asv.IP_ADDR AS SERVICE_IP,                    -- 服务IP地址

    -- ========== 应用进程信息 (当 RES_INST_TYPE = 'APP_PROCESS') ==========
    ap.PROCESS_NAME                               -- 进程名称

FROM NM_ALARM_EVENT e

-- 关联告警汇总表 (获取告警状态)
LEFT JOIN NM_ALARM_CDR c ON e.ALARM_CODE = c.ALARM_CODE
                         AND e.APP_ENV_ID = c.APP_ENV_ID
                         AND e.RES_INST_ID = c.RES_INST_ID

-- 关联告警码库 (获取告警名称和处理建议)
LEFT JOIN NM_ALARM_CODE_LIB acl ON e.ALARM_CODE = acl.ALARM_CODE

-- 关联应用环境 (获取应用信息)
LEFT JOIN APP_ENV ae ON e.APP_ENV_ID = ae.APP_ENV_ID

-- 关联设备表 (通过应用环境获取主机信息)
LEFT JOIN DEVICE d ON ae.DEVICE_ID = d.DEVICE_ID

-- 关联业务域表 (通过应用环境获取业务域)
LEFT JOIN SYS_DOMAIN sd ON ae.SYS_DOMAIN_ID = sd.DOMAIN_ID

-- 关联应用服务表 (当资源类型为 APP_SERVICE)
LEFT JOIN APP_SERVICE asv ON e.RES_INST_TYPE = 'APP_SERVICE'
                          AND e.RES_INST_ID = asv.APP_SERVICE_ID

-- 关联应用进程表 (当资源类型为 APP_PROCESS)
LEFT JOIN APP_PROCESS ap ON e.RES_INST_TYPE = 'APP_PROCESS'
                         AND e.RES_INST_ID = ap.PROCESS_ID

WHERE e.CREATE_DATE > SYSDATE - INTERVAL :history_hours HOUR
ORDER BY e.CREATE_DATE DESC;


-- ============================================================================
-- 2. 查询新产生的告警 (尚未同步)
-- 用途: 定时任务扫描新告警
-- ============================================================================
-- query_name: get_new_alarms
SELECT
    e.EVENT_INST_ID,
    e.EVENT_TIME,
    e.CREATE_DATE,
    e.ALARM_CODE,
    e.ALARM_LEVEL,
    e.RESET_FLAG,
    e.TASK_TYPE,
    e.RES_INST_TYPE,
    e.RES_INST_ID,
    e.APP_ENV_ID,
    e.DETAIL_INFO,
    e.DATA_1, e.DATA_2, e.DATA_3, e.DATA_4, e.DATA_5,
    e.DATA_6, e.DATA_7, e.DATA_8, e.DATA_9, e.DATA_10,
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
FROM NM_ALARM_EVENT e
LEFT JOIN NM_ALARM_CODE_LIB acl ON e.ALARM_CODE = acl.ALARM_CODE
LEFT JOIN APP_ENV ae ON e.APP_ENV_ID = ae.APP_ENV_ID
LEFT JOIN DEVICE d ON ae.DEVICE_ID = d.DEVICE_ID
LEFT JOIN SYS_DOMAIN sd ON ae.SYS_DOMAIN_ID = sd.DOMAIN_ID
WHERE e.RESET_FLAG = '1'  -- 仅告警消息(非恢复消息)
  AND NOT EXISTS (
      SELECT 1 FROM NM_ALARM_SYNC_STATUS s
      WHERE s.EVENT_INST_ID = e.EVENT_INST_ID
  )
  AND e.CREATE_DATE > SYSDATE - INTERVAL :history_hours HOUR
ORDER BY e.CREATE_DATE ASC
FETCH FIRST :batch_size ROWS ONLY;


-- ============================================================================
-- 3. 查询状态变更的告警 (需要更新同步状态)
-- 用途: 检测ZMC侧告警状态变化，触发Prometheus端更新
-- ============================================================================
-- query_name: get_status_changed_alarms
SELECT
    s.SYNC_ID,
    s.EVENT_INST_ID,
    s.ALARM_INST_ID,
    s.SYNC_STATUS,
    s.ZMC_ALARM_STATE AS OLD_ZMC_STATE,
    c.ALARM_STATE AS NEW_ZMC_STATE,
    c.RESET_DATE,
    c.CLEAR_DATE,
    c.CONFIRM_DATE,
    c.CLEAR_REASON,
    e.ALARM_CODE,
    e.ALARM_LEVEL,
    acl.ALARM_NAME,
    d.DEVICE_NAME AS HOST_NAME,
    d.IP_ADDR AS HOST_IP
FROM NM_ALARM_SYNC_STATUS s
JOIN NM_ALARM_EVENT e ON s.EVENT_INST_ID = e.EVENT_INST_ID
LEFT JOIN NM_ALARM_CDR c ON e.ALARM_CODE = c.ALARM_CODE
                         AND e.APP_ENV_ID = c.APP_ENV_ID
                         AND e.RES_INST_ID = c.RES_INST_ID
LEFT JOIN NM_ALARM_CODE_LIB acl ON e.ALARM_CODE = acl.ALARM_CODE
LEFT JOIN APP_ENV ae ON e.APP_ENV_ID = ae.APP_ENV_ID
LEFT JOIN DEVICE d ON ae.DEVICE_ID = d.DEVICE_ID
WHERE s.SYNC_STATUS IN ('FIRING', 'PENDING')
  AND c.ALARM_STATE IS NOT NULL
  AND c.ALARM_STATE != NVL(s.ZMC_ALARM_STATE, 'U');


-- ============================================================================
-- 4. 查询需要心跳保活的活跃告警
-- 用途: 定期重新推送活跃告警到Alertmanager，保持告警状态
-- ============================================================================
-- query_name: get_heartbeat_alarms
SELECT
    s.SYNC_ID,
    s.EVENT_INST_ID,
    s.LAST_PUSH_TIME,
    s.PUSH_COUNT,
    e.ALARM_CODE,
    e.ALARM_LEVEL,
    e.EVENT_TIME,
    e.DETAIL_INFO,
    acl.ALARM_NAME,
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
FROM NM_ALARM_SYNC_STATUS s
JOIN NM_ALARM_EVENT e ON s.EVENT_INST_ID = e.EVENT_INST_ID
LEFT JOIN NM_ALARM_CODE_LIB acl ON e.ALARM_CODE = acl.ALARM_CODE
LEFT JOIN APP_ENV ae ON e.APP_ENV_ID = ae.APP_ENV_ID
LEFT JOIN DEVICE d ON ae.DEVICE_ID = d.DEVICE_ID
LEFT JOIN SYS_DOMAIN sd ON ae.SYS_DOMAIN_ID = sd.DOMAIN_ID
WHERE s.SYNC_STATUS = 'FIRING'
  AND (s.LAST_PUSH_TIME IS NULL
       OR s.LAST_PUSH_TIME < SYSTIMESTAMP - NUMTODSINTERVAL(:heartbeat_interval, 'SECOND'));


-- ============================================================================
-- 5. 查询需要删除静默的告警 (告警已恢复但仍有静默规则)
-- 用途: 清理已恢复告警的静默规则
-- ============================================================================
-- query_name: get_silences_to_remove
SELECT
    s.SYNC_ID,
    s.EVENT_INST_ID,
    s.SILENCE_ID,
    s.ZMC_ALARM_STATE,
    c.ALARM_STATE AS CURRENT_ZMC_STATE,
    c.RESET_DATE,
    c.CLEAR_DATE
FROM NM_ALARM_SYNC_STATUS s
LEFT JOIN NM_ALARM_EVENT e ON s.EVENT_INST_ID = e.EVENT_INST_ID
LEFT JOIN NM_ALARM_CDR c ON e.ALARM_CODE = c.ALARM_CODE
                         AND e.APP_ENV_ID = c.APP_ENV_ID
                         AND e.RES_INST_ID = c.RES_INST_ID
WHERE s.SYNC_STATUS = 'SILENCED'
  AND s.SILENCE_ID IS NOT NULL
  AND c.ALARM_STATE IN ('A', 'C')  -- 自动恢复或已确认
;


-- ============================================================================
-- 6. 查询恢复消息 (RESET_FLAG = 0)
-- 用途: 处理告警恢复消息，更新同步状态
-- ============================================================================
-- query_name: get_recovery_events
SELECT
    e.EVENT_INST_ID,
    e.ALARM_CODE,
    e.APP_ENV_ID,
    e.RES_INST_ID,
    e.EVENT_TIME AS RECOVERY_TIME,
    e.CREATE_DATE,
    e.DETAIL_INFO,
    s.SYNC_ID,
    s.SYNC_STATUS,
    s.SILENCE_ID
FROM NM_ALARM_EVENT e
JOIN NM_ALARM_SYNC_STATUS s ON e.ALARM_CODE = (
    SELECT e2.ALARM_CODE FROM NM_ALARM_EVENT e2
    WHERE e2.EVENT_INST_ID = s.EVENT_INST_ID
)
WHERE e.RESET_FLAG = '0'  -- 恢复消息
  AND s.SYNC_STATUS IN ('FIRING', 'SILENCED')
  AND e.CREATE_DATE > s.CREATE_TIME
  AND e.CREATE_DATE > SYSDATE - INTERVAL :history_hours HOUR;


-- ============================================================================
-- 7. 插入同步状态记录
-- ============================================================================
-- query_name: insert_sync_status
INSERT INTO NM_ALARM_SYNC_STATUS (
    SYNC_ID,
    EVENT_INST_ID,
    ALARM_INST_ID,
    SYNC_STATUS,
    ZMC_ALARM_STATE,
    CREATE_TIME,
    UPDATE_TIME
) VALUES (
    SEQ_ALARM_SYNC_STATUS.NEXTVAL,
    :event_inst_id,
    :alarm_inst_id,
    :sync_status,
    :zmc_alarm_state,
    SYSTIMESTAMP,
    SYSTIMESTAMP
);


-- ============================================================================
-- 8. 更新同步状态 (推送成功)
-- ============================================================================
-- query_name: update_sync_status_success
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
WHERE SYNC_ID = :sync_id;


-- ============================================================================
-- 9. 更新同步状态 (推送失败)
-- ============================================================================
-- query_name: update_sync_status_error
UPDATE NM_ALARM_SYNC_STATUS
SET ERROR_COUNT = ERROR_COUNT + 1,
    LAST_ERROR = :error_message,
    UPDATE_TIME = SYSTIMESTAMP
WHERE SYNC_ID = :sync_id;


-- ============================================================================
-- 10. 插入同步日志
-- ============================================================================
-- query_name: insert_sync_log
INSERT INTO NM_ALARM_SYNC_LOG (
    LOG_ID,
    SYNC_BATCH_ID,
    EVENT_INST_ID,
    OPERATION,
    OLD_STATUS,
    NEW_STATUS,
    REQUEST_URL,
    REQUEST_METHOD,
    REQUEST_PAYLOAD,
    RESPONSE_CODE,
    RESPONSE_BODY,
    ERROR_MESSAGE,
    DURATION_MS,
    CREATE_TIME
) VALUES (
    SEQ_ALARM_SYNC_LOG.NEXTVAL,
    :sync_batch_id,
    :event_inst_id,
    :operation,
    :old_status,
    :new_status,
    :request_url,
    :request_method,
    :request_payload,
    :response_code,
    :response_body,
    :error_message,
    :duration_ms,
    SYSTIMESTAMP
);


-- ============================================================================
-- 11. 获取配置项
-- ============================================================================
-- query_name: get_config
SELECT
    CONFIG_VALUE,
    CONFIG_VALUE_ENC,
    IS_ENCRYPTED,
    DEFAULT_VALUE
FROM NM_ALARM_SYNC_CONFIG
WHERE CONFIG_GROUP = :config_group
  AND CONFIG_KEY = :config_key;


-- ============================================================================
-- 12. 获取配置组所有配置
-- ============================================================================
-- query_name: get_config_group
SELECT
    CONFIG_KEY,
    CONFIG_VALUE,
    CONFIG_VALUE_ENC,
    IS_ENCRYPTED,
    DEFAULT_VALUE
FROM NM_ALARM_SYNC_CONFIG
WHERE CONFIG_GROUP = :config_group
ORDER BY CONFIG_KEY;


-- ============================================================================
-- 13. 获取标签映射配置
-- ============================================================================
-- query_name: get_label_mappings
SELECT
    SOURCE_FIELD,
    TARGET_LABEL,
    TRANSFORM_TYPE,
    TRANSFORM_EXPR,
    LABEL_TYPE
FROM NM_ALARM_LABEL_MAPPING
WHERE IS_ENABLED = 'Y'
ORDER BY LABEL_TYPE, SORT_ORDER;


-- ============================================================================
-- 14. 同步统计信息
-- ============================================================================
-- query_name: get_sync_statistics
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
ORDER BY SYNC_STATUS;


-- ============================================================================
-- 15. 获取最近的同步日志
-- ============================================================================
-- query_name: get_recent_sync_logs
SELECT
    LOG_ID,
    SYNC_BATCH_ID,
    EVENT_INST_ID,
    OPERATION,
    OLD_STATUS,
    NEW_STATUS,
    RESPONSE_CODE,
    ERROR_MESSAGE,
    DURATION_MS,
    CREATE_TIME
FROM NM_ALARM_SYNC_LOG
WHERE CREATE_TIME > SYSTIMESTAMP - NUMTODSINTERVAL(:hours, 'HOUR')
ORDER BY CREATE_TIME DESC
FETCH FIRST :limit ROWS ONLY;


-- ============================================================================
-- 16. 清理已完成的同步记录 (可选，用于归档)
-- ============================================================================
-- query_name: archive_resolved_alarms
DELETE FROM NM_ALARM_SYNC_STATUS
WHERE SYNC_STATUS = 'RESOLVED'
  AND UPDATE_TIME < SYSTIMESTAMP - NUMTODSINTERVAL(:retention_days, 'DAY');
