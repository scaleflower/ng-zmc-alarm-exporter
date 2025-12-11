-- ============================================================================
-- ZMC Alarm Exporter - 数据库升级脚本
-- 版本: 2.0.0
-- 描述: 将同步架构从 NM_ALARM_EVENT 为核心改为 NM_ALARM_CDR 为核心
--
-- 重要变更:
-- 1. NM_ALARM_SYNC_STATUS 表的主关联键从 EVENT_INST_ID 改为 ALARM_INST_ID
-- 2. 唯一约束从 EVENT_INST_ID 改为 ALARM_INST_ID
-- 3. 新增 ALARM_INST_ID 索引
-- ============================================================================

-- ============================================================================
-- 升级前准备
-- ============================================================================

-- 1. 备份现有数据（可选，建议在生产环境执行）
-- CREATE TABLE NM_ALARM_SYNC_STATUS_BAK AS SELECT * FROM NM_ALARM_SYNC_STATUS;

-- 2. 查看当前数据量
SELECT 'Current sync status count: ' || COUNT(*) AS info FROM NM_ALARM_SYNC_STATUS;
SELECT 'FIRING count: ' || COUNT(*) AS info FROM NM_ALARM_SYNC_STATUS WHERE SYNC_STATUS = 'FIRING';
SELECT 'RESOLVED count: ' || COUNT(*) AS info FROM NM_ALARM_SYNC_STATUS WHERE SYNC_STATUS = 'RESOLVED';


-- ============================================================================
-- 步骤 1: 清理旧数据（建议在升级前执行）
-- ============================================================================

-- 清理已解决的历史记录（保留最近 7 天）
DELETE FROM NM_ALARM_SYNC_STATUS
WHERE SYNC_STATUS = 'RESOLVED'
  AND UPDATE_TIME < SYSTIMESTAMP - INTERVAL '7' DAY;

COMMIT;


-- ============================================================================
-- 步骤 2: 修改约束和索引
-- ============================================================================

-- 2.1 删除旧的唯一约束（EVENT_INST_ID）
-- 注意: 约束名称可能不同，请先查询确认
-- SELECT constraint_name FROM user_constraints WHERE table_name = 'NM_ALARM_SYNC_STATUS' AND constraint_type = 'U';

BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE NM_ALARM_SYNC_STATUS DROP CONSTRAINT UK_SYNC_EVENT_INST';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -2443 THEN  -- ORA-02443: constraint does not exist
            RAISE;
        END IF;
END;
/

-- 2.2 添加新的唯一约束（ALARM_INST_ID）
-- 注意: 如果表中已有重复的 ALARM_INST_ID，需要先清理
ALTER TABLE NM_ALARM_SYNC_STATUS
ADD CONSTRAINT UK_SYNC_ALARM_INST UNIQUE (ALARM_INST_ID);

-- 2.3 添加 ALARM_INST_ID 索引（如果不存在）
BEGIN
    EXECUTE IMMEDIATE 'CREATE INDEX IDX_SYNC_STATUS_ALARM_INST ON NM_ALARM_SYNC_STATUS(ALARM_INST_ID)';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -1408 THEN  -- ORA-01408: such column list already indexed
            RAISE;
        END IF;
END;
/


-- ============================================================================
-- 步骤 3: 更新字段注释
-- ============================================================================

COMMENT ON COLUMN NM_ALARM_SYNC_STATUS.ALARM_INST_ID IS '关联NM_ALARM_CDR表的告警汇总ID，作为唯一标识（核心关联键）';
COMMENT ON COLUMN NM_ALARM_SYNC_STATUS.EVENT_INST_ID IS '关联NM_ALARM_EVENT表的告警事件ID，记录最新事件（非必填）';


-- ============================================================================
-- 步骤 4: 数据迁移（将旧记录的 ALARM_INST_ID 补全）
-- ============================================================================

-- 4.1 更新已有记录的 ALARM_INST_ID（如果为空）
UPDATE NM_ALARM_SYNC_STATUS s
SET ALARM_INST_ID = (
    SELECT c.ALARM_INST_ID
    FROM NM_ALARM_EVENT e
    JOIN NM_ALARM_CDR c ON e.ALARM_CODE = c.ALARM_CODE
                        AND e.APP_ENV_ID = c.APP_ENV_ID
                        AND e.RES_INST_ID = c.RES_INST_ID
    WHERE e.EVENT_INST_ID = s.EVENT_INST_ID
      AND ROWNUM = 1
)
WHERE s.ALARM_INST_ID IS NULL
  AND s.EVENT_INST_ID IS NOT NULL;

COMMIT;

-- 4.2 删除无法关联到 CDR 的孤儿记录
DELETE FROM NM_ALARM_SYNC_STATUS
WHERE ALARM_INST_ID IS NULL;

COMMIT;


-- ============================================================================
-- 步骤 5: 验证升级结果
-- ============================================================================

-- 检查唯一约束
SELECT constraint_name, constraint_type, status
FROM user_constraints
WHERE table_name = 'NM_ALARM_SYNC_STATUS'
  AND constraint_type = 'U';

-- 检查索引
SELECT index_name, column_name
FROM user_ind_columns
WHERE table_name = 'NM_ALARM_SYNC_STATUS'
ORDER BY index_name, column_position;

-- 检查数据完整性
SELECT 'Records with NULL ALARM_INST_ID: ' || COUNT(*) AS info
FROM NM_ALARM_SYNC_STATUS
WHERE ALARM_INST_ID IS NULL;

SELECT 'Total records: ' || COUNT(*) AS info FROM NM_ALARM_SYNC_STATUS;


-- ============================================================================
-- 回滚脚本（如需回滚）
-- ============================================================================
/*
-- 删除新约束
ALTER TABLE NM_ALARM_SYNC_STATUS DROP CONSTRAINT UK_SYNC_ALARM_INST;

-- 恢复旧约束
ALTER TABLE NM_ALARM_SYNC_STATUS ADD CONSTRAINT UK_SYNC_EVENT_INST UNIQUE (EVENT_INST_ID);

-- 删除新索引
DROP INDEX IDX_SYNC_STATUS_ALARM_INST;

-- 恢复备份数据（如果有备份）
-- TRUNCATE TABLE NM_ALARM_SYNC_STATUS;
-- INSERT INTO NM_ALARM_SYNC_STATUS SELECT * FROM NM_ALARM_SYNC_STATUS_BAK;
-- COMMIT;
*/


-- ============================================================================
-- 升级完成
-- ============================================================================
SELECT 'Upgrade completed successfully!' AS status FROM DUAL;
