# ZMC Alarm Exporter 数据库设计与业务模型说明

> 版本: 2.0.0
> 更新日期: 2024-12
> 架构: 以 NM_ALARM_CDR（告警汇总表）为核心

---

## 一、系统架构概述

### 1.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           ZMC Alarm Exporter 系统架构                            │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                         ZMC Oracle 数据库 (只读)                         │   │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐  │   │
│  │  │  NM_ALARM_CDR   │  │ NM_ALARM_EVENT  │  │  NM_ALARM_CODE_LIB      │  │   │
│  │  │  (告警汇总表)    │  │  (告警事件表)    │  │  (告警码配置表)          │  │   │
│  │  │  ──────────────  │  │  ──────────────  │  │  ──────────────────────  │  │   │
│  │  │  ALARM_INST_ID  │◀─│  ALARM_CODE     │──│  ALARM_CODE             │  │   │
│  │  │  ALARM_STATE    │  │  EVENT_INST_ID  │  │  ALARM_NAME             │  │   │
│  │  │  ALARM_CODE     │  │  DETAIL_INFO    │  │  FAULT_REASON           │  │   │
│  │  │  APP_ENV_ID     │  │  DATA_1~10      │  │  DEAL_SUGGEST           │  │   │
│  │  │  RES_INST_ID    │  │  EVENT_TIME     │  │                         │  │   │
│  │  └────────┬────────┘  └─────────────────┘  └─────────────────────────┘  │   │
│  │           │                                                              │   │
│  │           │  ┌─────────────────┐  ┌─────────────────┐                   │   │
│  │           │  │    APP_ENV      │  │     DEVICE      │                   │   │
│  │           └─▶│  (应用环境表)    │─▶│   (设备表)       │                   │   │
│  │              │  APP_ENV_ID     │  │  DEVICE_ID      │                   │   │
│  │              │  APP_NAME       │  │  DEVICE_NAME    │                   │   │
│  │              │  DEVICE_ID      │  │  IP_ADDR        │                   │   │
│  │              │  SYS_DOMAIN_ID  │  └─────────────────┘                   │   │
│  │              └────────┬────────┘                                        │   │
│  │                       │         ┌─────────────────┐                     │   │
│  │                       └────────▶│   SYS_DOMAIN    │                     │   │
│  │                                 │  (业务域表)      │                     │   │
│  │                                 │  DOMAIN_NAME    │                     │   │
│  │                                 │  DOMAIN_TYPE    │                     │   │
│  │                                 └─────────────────┘                     │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                         │
│                                      │ 定时扫描                                 │
│                                      ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                       Exporter 同步状态表 (读写)                          │   │
│  │  ┌─────────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │   │
│  │  │ NM_ALARM_SYNC_STATUS│  │NM_ALARM_SYNC_LOG│  │NM_ALARM_SYNC_CONFIG │  │   │
│  │  │  (同步状态跟踪表)    │  │  (同步日志表)    │  │  (配置表)            │  │   │
│  │  │  ──────────────────  │  │  ──────────────  │  │  ──────────────────  │  │   │
│  │  │  ALARM_INST_ID (UK) │  │  LOG_ID         │  │  CONFIG_GROUP       │  │   │
│  │  │  SYNC_STATUS        │  │  OPERATION      │  │  CONFIG_KEY         │  │   │
│  │  │  ZMC_ALARM_STATE    │  │  REQUEST_URL    │  │  CONFIG_VALUE       │  │   │
│  │  │  LAST_PUSH_TIME     │  │  RESPONSE_CODE  │  │                     │  │   │
│  │  └─────────────────────┘  └─────────────────┘  └─────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                         │
│                                      │ HTTP POST                               │
│                                      ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                         Prometheus Alertmanager                          │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐    │   │
│  │  │  POST /api/v2/alerts     - 推送告警 (firing/resolved)            │    │   │
│  │  │  POST /api/v2/silences   - 创建静默规则                          │    │   │
│  │  │  DELETE /api/v2/silence  - 删除静默规则                          │    │   │
│  │  └─────────────────────────────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                         │
│                                      ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                              OpsGenie                                    │   │
│  │                     (通过 Alertmanager 集成)                             │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 核心设计理念

**v2.0 架构以 `NM_ALARM_CDR`（告警汇总表）为核心**，而非 `NM_ALARM_EVENT`（告警事件表）：

| 对比维度 | NM_ALARM_EVENT | NM_ALARM_CDR |
|----------|----------------|--------------|
| 记录粒度 | 每次告警/恢复一条记录 | 每个告警源唯一一条记录 |
| 数据量 | 大（流水日志） | 小（汇总） |
| 状态管理 | RESET_FLAG (1/0) | ALARM_STATE (U/A/M/C) |
| 唯一标识 | EVENT_INST_ID | ALARM_INST_ID |
| 适用场景 | 告警历史查询 | **状态同步（推荐）** |

---

## 二、数据库表结构详解

### 2.1 ZMC 原有表（只读）

#### 2.1.1 NM_ALARM_CDR - 告警汇总表（核心数据源）

> **作用**：记录每个告警源的当前状态，一个告警源只有一条记录

| 字段名 | 类型 | 必填 | 说明 | 用途 |
|--------|------|------|------|------|
| `ALARM_INST_ID` | NUMBER(13) | Y | 告警汇总唯一ID | **主键，同步状态关联键** |
| `ALARM_CODE` | NUMBER | Y | 告警码 | 关联告警码表 |
| `APP_ENV_ID` | NUMBER | Y | 应用环境ID | 关联应用/设备信息 |
| `RES_INST_ID` | NUMBER | Y | 资源实例ID | 告警源标识 |
| `ALARM_STATE` | CHAR(1) | Y | **告警状态** | **状态变更检测核心字段** |
| `ALARM_LEVEL` | VARCHAR2 | N | 告警级别 1-4 | Prometheus severity 映射 |
| `CREATE_DATE` | TIMESTAMP | N | 首次告警时间 | Prometheus startsAt |
| `RESET_DATE` | TIMESTAMP | N | 自动恢复时间 | Prometheus endsAt (状态=A) |
| `CLEAR_DATE` | TIMESTAMP | N | 手工清除时间 | Prometheus endsAt (状态=M) |
| `CONFIRM_DATE` | TIMESTAMP | N | 确认时间 | Prometheus endsAt (状态=C) |
| `TOTAL_ALARM` | NUMBER | N | 累计告警次数 | 统计信息 |
| `CLEAR_REASON` | VARCHAR2 | N | 清除原因 | Silence 注释 |

**ALARM_STATE 状态值说明**：

| 值 | 含义 | 英文 | Alertmanager 操作 |
|----|------|------|-------------------|
| `U` | 未确认 | Unconfirmed | 推送 FIRING 告警 |
| `A` | 自动恢复 | Auto-recovered | 推送 RESOLVED 告警 |
| `M` | 手工清除 | Manual clear | 推送 RESOLVED + 创建 Silence |
| `C` | 已确认 | Confirmed | 推送 RESOLVED 告警 |

---

#### 2.1.2 NM_ALARM_EVENT - 告警事件表

> **作用**：记录告警流水日志，用于获取告警详细信息

| 字段名 | 类型 | 必填 | 说明 | 用途 |
|--------|------|------|------|------|
| `EVENT_INST_ID` | NUMBER(13) | Y | 事件唯一ID | 主键 |
| `ALARM_CODE` | NUMBER | Y | 告警码 | 关联 CDR |
| `APP_ENV_ID` | NUMBER | Y | 应用环境ID | 关联 CDR |
| `RES_INST_ID` | NUMBER | Y | 资源实例ID | 关联 CDR |
| `RESET_FLAG` | CHAR(1) | Y | 恢复标志 | 1=告警, 0=恢复 |
| `EVENT_TIME` | TIMESTAMP | N | 告警发生时间 | Prometheus startsAt |
| `CREATE_DATE` | TIMESTAMP | N | 记录创建时间 | 时间过滤 |
| `ALARM_LEVEL` | VARCHAR2 | N | 告警级别 | severity 映射 |
| `DETAIL_INFO` | VARCHAR2 | N | 告警详情 | Prometheus description |
| `DATA_1` ~ `DATA_10` | VARCHAR2 | N | 扩展字段 | Prometheus annotation |
| `TASK_TYPE` | VARCHAR2 | N | 任务类型 | Prometheus label |
| `RES_INST_TYPE` | VARCHAR2 | N | 资源类型 | Prometheus label |

---

#### 2.1.3 NM_ALARM_CODE_LIB - 告警码配置表

| 字段名 | 类型 | 说明 | 用途 |
|--------|------|------|------|
| `ALARM_CODE` | NUMBER | 告警码 | 关联键 |
| `ALARM_NAME` | VARCHAR2 | 告警名称 | Prometheus `alertname` |
| `WARN_LEVEL` | VARCHAR2 | 默认告警级别 | 备用 severity |
| `FAULT_REASON` | VARCHAR2 | 故障原因 | Prometheus annotation |
| `DEAL_SUGGEST` | VARCHAR2 | 处理建议 | Prometheus `runbook` |
| `ALARM_TYPE` | VARCHAR2 | 告警类型代码 | 分类信息 |

---

#### 2.1.4 APP_ENV - 应用环境表

| 字段名 | 类型 | 说明 | 用途 |
|--------|------|------|------|
| `APP_ENV_ID` | NUMBER | 应用环境ID | 关联键 |
| `APP_NAME` | VARCHAR2 | 应用名称 | Prometheus `application` label |
| `DEVICE_ID` | NUMBER | 设备ID | 关联设备表 |
| `SYS_DOMAIN_ID` | NUMBER | 业务域ID | 关联业务域表 |
| `USERNAME` | VARCHAR2 | 应用用户 | 附加信息 |

---

#### 2.1.5 DEVICE - 设备表

| 字段名 | 类型 | 说明 | 用途 |
|--------|------|------|------|
| `DEVICE_ID` | NUMBER | 设备ID | 关联键 |
| `DEVICE_NAME` | VARCHAR2 | 主机名 | Prometheus `host` label |
| `IP_ADDR` | VARCHAR2 | IP地址 | Prometheus `instance` label |
| `DEVICE_MODEL` | VARCHAR2 | 设备型号 | 附加信息 |

---

#### 2.1.6 SYS_DOMAIN - 业务域表

| 字段名 | 类型 | 说明 | 用途 |
|--------|------|------|------|
| `DOMAIN_ID` | NUMBER | 业务域ID | 关联键 |
| `DOMAIN_NAME` | VARCHAR2 | 业务域名称 | Prometheus `domain` label |
| `DOMAIN_TYPE` | CHAR(1) | 域类型 | Prometheus `env` label |

**DOMAIN_TYPE 映射**：

| 值 | 含义 | Prometheus env |
|----|------|----------------|
| `A` | 生产环境 | `production` |
| `T` | 测试环境 | `test` |
| `D` | 灾备环境 | `dr` |

---

### 2.2 Exporter 自建表（读写）

#### 2.2.1 NM_ALARM_SYNC_STATUS - 同步状态跟踪表

> **作用**：跟踪每条告警的同步状态，以 `ALARM_INST_ID` 为唯一标识

| 字段名 | 类型 | 必填 | 说明 | 索引 |
|--------|------|------|------|------|
| `SYNC_ID` | NUMBER(12) | Y | 同步记录ID | PK |
| `ALARM_INST_ID` | NUMBER(13) | Y | **告警汇总ID（核心关联键）** | **UK** |
| `EVENT_INST_ID` | NUMBER(13) | N | 最新事件ID（可选） | |
| `SYNC_STATUS` | VARCHAR2(20) | Y | 同步状态 | IDX |
| `ZMC_ALARM_STATE` | VARCHAR2(10) | N | 上次同步时的 ZMC 状态 | IDX |
| `LAST_PUSH_TIME` | TIMESTAMP | N | 最后推送时间 | IDX |
| `PUSH_COUNT` | NUMBER(9) | N | 累计推送次数 | |
| `AM_FINGERPRINT` | VARCHAR2(100) | N | Alertmanager 指纹 | |
| `SILENCE_ID` | VARCHAR2(100) | N | Silence 规则ID | |
| `ERROR_COUNT` | NUMBER(9) | N | 错误次数 | |
| `LAST_ERROR` | VARCHAR2(2000) | N | 最后错误信息 | |
| `CREATE_TIME` | TIMESTAMP | N | 创建时间 | IDX |
| `UPDATE_TIME` | TIMESTAMP | N | 更新时间 | |

**SYNC_STATUS 状态值说明**：

| 值 | 含义 | 触发条件 | 后续处理 |
|----|------|----------|----------|
| `PENDING` | 待同步 | 新建记录，尚未推送 | 等待推送 |
| `FIRING` | 告警中 | 已推送到 Alertmanager | 心跳保活 / 状态变更检测 |
| `RESOLVED` | 已恢复 | ZMC 状态变为 A/C | 可清理 |
| `SILENCED` | 已静默 | ZMC 状态变为 M（手工清除） | 清理 Silence |
| `ERROR` | 同步错误 | 推送失败 | 重试 |

---

#### 2.2.2 NM_ALARM_SYNC_LOG - 同步日志表

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `LOG_ID` | NUMBER(12) | 日志ID |
| `SYNC_BATCH_ID` | VARCHAR2(50) | 同步批次ID |
| `EVENT_INST_ID` | NUMBER(13) | 关联事件ID |
| `OPERATION` | VARCHAR2(30) | 操作类型 |
| `OLD_STATUS` | VARCHAR2(20) | 操作前状态 |
| `NEW_STATUS` | VARCHAR2(20) | 操作后状态 |
| `REQUEST_URL` | VARCHAR2(500) | 请求URL |
| `REQUEST_METHOD` | VARCHAR2(10) | HTTP方法 |
| `REQUEST_PAYLOAD` | CLOB | 请求体 |
| `RESPONSE_CODE` | NUMBER(5) | 响应码 |
| `RESPONSE_BODY` | CLOB | 响应体 |
| `ERROR_MESSAGE` | VARCHAR2(2000) | 错误信息 |
| `DURATION_MS` | NUMBER(9) | 耗时(ms) |
| `CREATE_TIME` | TIMESTAMP | 创建时间 |

**OPERATION 操作类型**：

| 值 | 说明 |
|----|------|
| `PUSH_FIRING` | 推送活跃告警 |
| `PUSH_RESOLVED` | 推送恢复告警 |
| `CREATE_SILENCE` | 创建静默规则 |
| `DELETE_SILENCE` | 删除静默规则 |
| `HEARTBEAT` | 心跳保活 |
| `ERROR` | 错误记录 |

---

## 三、数据流转与同步逻辑

### 3.1 表关联关系图

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              表关联关系                                          │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   NM_ALARM_CDR (核心)                                                           │
│   ├── ALARM_INST_ID ─────────────────────────────► NM_ALARM_SYNC_STATUS        │
│   │                                                 └── ALARM_INST_ID (UK)      │
│   │                                                                             │
│   ├── ALARM_CODE ─┬──────────────────────────────► NM_ALARM_CODE_LIB           │
│   ├── APP_ENV_ID ─┼──────────────────────────────► APP_ENV                     │
│   └── RES_INST_ID ┘                                 ├── DEVICE_ID ──► DEVICE   │
│                                                      └── SYS_DOMAIN_ID ──► SYS_DOMAIN
│                                                                                 │
│   NM_ALARM_EVENT (详情)                                                         │
│   ├── ALARM_CODE  ─┐                                                            │
│   ├── APP_ENV_ID  ─┼── 关联 NM_ALARM_CDR（获取最新事件详情）                      │
│   └── RES_INST_ID ─┘                                                            │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 新告警同步流程

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           新告警同步流程                                         │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  步骤 1: 查询活跃告警                                                            │
│  ┌────────────────────────────────────────────────────────────────────────┐    │
│  │  SELECT c.*, e.DETAIL_INFO, e.DATA_1~10, acl.ALARM_NAME, d.IP_ADDR...  │    │
│  │  FROM NM_ALARM_CDR c                                                   │    │
│  │  LEFT JOIN NM_ALARM_EVENT e ON (关联最新事件)                           │    │
│  │  LEFT JOIN NM_ALARM_CODE_LIB acl ON c.ALARM_CODE = acl.ALARM_CODE      │    │
│  │  LEFT JOIN APP_ENV ae ON c.APP_ENV_ID = ae.APP_ENV_ID                  │    │
│  │  LEFT JOIN DEVICE d ON ae.DEVICE_ID = d.DEVICE_ID                      │    │
│  │  LEFT JOIN SYS_DOMAIN sd ON ae.SYS_DOMAIN_ID = sd.DOMAIN_ID            │    │
│  │  WHERE c.ALARM_STATE = 'U'  -- 只查询活跃告警                           │    │
│  │    AND NOT EXISTS (SELECT 1 FROM NM_ALARM_SYNC_STATUS WHERE ...)       │    │
│  └────────────────────────────────────────────────────────────────────────┘    │
│                                      │                                         │
│                                      ▼                                         │
│  步骤 2: 转换为 Prometheus Alert 格式                                           │
│  ┌────────────────────────────────────────────────────────────────────────┐    │
│  │  {                                                                     │    │
│  │    "labels": {                                                         │    │
│  │      "alertname": "CPU使用率过高",     ◄── NM_ALARM_CODE_LIB.ALARM_NAME │    │
│  │      "instance": "192.168.1.100",     ◄── DEVICE.IP_ADDR              │    │
│  │      "severity": "critical",          ◄── ALARM_LEVEL 映射             │    │
│  │      "alarm_id": "12345",             ◄── NM_ALARM_CDR.ALARM_INST_ID   │    │
│  │      "alarm_code": "5001",            ◄── NM_ALARM_CDR.ALARM_CODE      │    │
│  │      "host": "server-01",             ◄── DEVICE.DEVICE_NAME           │    │
│  │      "application": "WebApp",         ◄── APP_ENV.APP_NAME             │    │
│  │      "domain": "Production",          ◄── SYS_DOMAIN.DOMAIN_NAME       │    │
│  │      "env": "production",             ◄── SYS_DOMAIN.DOMAIN_TYPE 映射   │    │
│  │      "source": "zmc"                  ◄── 静态配置                      │    │
│  │    },                                                                  │    │
│  │    "annotations": {                                                    │    │
│  │      "summary": "CPU使用率过高",       ◄── NM_ALARM_CODE_LIB.ALARM_NAME │    │
│  │      "description": "当前CPU 95%",    ◄── NM_ALARM_EVENT.DETAIL_INFO   │    │
│  │      "fault_reason": "负载过高",       ◄── NM_ALARM_CODE_LIB.FAULT_REASON│    │
│  │      "runbook": "检查进程...",        ◄── NM_ALARM_CODE_LIB.DEAL_SUGGEST│    │
│  │      "data_1": "...",                 ◄── NM_ALARM_EVENT.DATA_1~10     │    │
│  │    },                                                                  │    │
│  │    "startsAt": "2024-01-01T10:00:00Z" ◄── NM_ALARM_EVENT.EVENT_TIME    │    │
│  │  }                                                                     │    │
│  └────────────────────────────────────────────────────────────────────────┘    │
│                                      │                                         │
│                                      ▼                                         │
│  步骤 3: 推送到 Alertmanager                                                    │
│  ┌────────────────────────────────────────────────────────────────────────┐    │
│  │  POST http://alertmanager:9093/api/v2/alerts                           │    │
│  │  Content-Type: application/json                                        │    │
│  │  Body: [{ labels, annotations, startsAt }]                             │    │
│  └────────────────────────────────────────────────────────────────────────┘    │
│                                      │                                         │
│                                      ▼                                         │
│  步骤 4: 记录同步状态                                                            │
│  ┌────────────────────────────────────────────────────────────────────────┐    │
│  │  INSERT INTO NM_ALARM_SYNC_STATUS (                                    │    │
│  │    ALARM_INST_ID,      -- 告警汇总ID                                    │    │
│  │    EVENT_INST_ID,      -- 最新事件ID                                    │    │
│  │    SYNC_STATUS,        -- 'FIRING'                                     │    │
│  │    ZMC_ALARM_STATE,    -- 'U'                                          │    │
│  │    LAST_PUSH_TIME      -- SYSTIMESTAMP                                 │    │
│  │  )                                                                     │    │
│  └────────────────────────────────────────────────────────────────────────┘    │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 3.3 状态变更检测与同步流程

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         状态变更检测与同步流程                                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  检测条件:                                                                       │
│  ┌────────────────────────────────────────────────────────────────────────┐    │
│  │  SELECT s.*, c.ALARM_STATE AS NEW_ZMC_STATE                            │    │
│  │  FROM NM_ALARM_SYNC_STATUS s                                           │    │
│  │  JOIN NM_ALARM_CDR c ON s.ALARM_INST_ID = c.ALARM_INST_ID              │    │
│  │  WHERE s.SYNC_STATUS IN ('FIRING', 'PENDING')                          │    │
│  │    AND c.ALARM_STATE != NVL(s.ZMC_ALARM_STATE, 'U')  -- 状态发生变化    │    │
│  └────────────────────────────────────────────────────────────────────────┘    │
│                                                                                 │
│  状态变更处理逻辑:                                                               │
│  ┌────────────────────────────────────────────────────────────────────────┐    │
│  │                                                                        │    │
│  │   OLD_STATE     NEW_STATE      操作                                    │    │
│  │   ─────────────────────────────────────────────────────────────────    │    │
│  │                                                                        │    │
│  │      U      ──►    A         1. 推送 RESOLVED 告警                      │    │
│  │   (活跃)        (自动恢复)       endsAt = RESET_DATE                    │    │
│  │                              2. 更新 SYNC_STATUS = 'RESOLVED'          │    │
│  │                                                                        │    │
│  │      U      ──►    M         1. 推送 RESOLVED 告警                      │    │
│  │   (活跃)        (手工清除)       endsAt = CLEAR_DATE                    │    │
│  │                              2. 创建 Silence 规则（防止重新触发）        │    │
│  │                              3. 更新 SYNC_STATUS = 'SILENCED'          │    │
│  │                                                                        │    │
│  │      U      ──►    C         1. 推送 RESOLVED 告警                      │    │
│  │   (活跃)        (已确认)         endsAt = CONFIRM_DATE                  │    │
│  │                              2. 更新 SYNC_STATUS = 'RESOLVED'          │    │
│  │                                                                        │    │
│  └────────────────────────────────────────────────────────────────────────┘    │
│                                                                                 │
│  RESOLVED 告警格式:                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐    │
│  │  {                                                                     │    │
│  │    "labels": { ... },          -- 与 FIRING 时相同                      │    │
│  │    "annotations": { ... },     -- 与 FIRING 时相同                      │    │
│  │    "startsAt": "...",          -- 原始告警时间                          │    │
│  │    "endsAt": "..."             -- 恢复时间 (RESET_DATE/CLEAR_DATE/...)  │    │
│  │  }                                                                     │    │
│  └────────────────────────────────────────────────────────────────────────┘    │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 3.4 完整状态流转图

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              状态流转图                                          │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   ZMC 告警状态                      Exporter 同步状态                            │
│   (NM_ALARM_CDR.ALARM_STATE)       (NM_ALARM_SYNC_STATUS.SYNC_STATUS)          │
│                                                                                 │
│   ┌─────────┐                       ┌─────────┐                                │
│   │    U    │                       │ PENDING │  ← 新建记录                     │
│   │ (活跃)   │ ────新告警────────────►│ (待同步) │                                │
│   └────┬────┘                       └────┬────┘                                │
│        │                                 │                                      │
│        │                                 │ 推送成功                              │
│        │                                 ▼                                      │
│        │                           ┌─────────┐                                 │
│        │                           │ FIRING  │                                 │
│        │                           │ (告警中) │ ◄─── 心跳保活                    │
│        │                           └────┬────┘                                 │
│        │                                 │                                      │
│   ┌────┴────┐                           │                                      │
│   │ 状态变更 │                           │                                      │
│   └────┬────┘                           │                                      │
│        │                                 │                                      │
│   ┌────┼────────────────────────────────┼────┐                                 │
│   │    │                                 │    │                                 │
│   ▼    ▼                                 ▼    ▼                                 │
│ ┌───┐ ┌───┐                         ┌─────────┐                                │
│ │ A │ │ C │ ──────推送 RESOLVED──────►│RESOLVED │                               │
│ │自动│ │已 │                         │ (已恢复) │                                │
│ │恢复│ │确认│                         └─────────┘                                │
│ └───┘ └───┘                                                                    │
│                                                                                 │
│ ┌───┐                               ┌─────────┐                                │
│ │ M │ ──推送 RESOLVED + Silence────►│SILENCED │                                │
│ │手工│                               │ (已静默) │                                │
│ │清除│                               └────┬────┘                                │
│ └───┘                                    │                                      │
│                                          │ 告警最终恢复 (A/C)                     │
│                                          │ 删除 Silence                         │
│                                          ▼                                      │
│                                     ┌─────────┐                                │
│                                     │RESOLVED │                                │
│                                     │ (已恢复) │                                │
│                                     └─────────┘                                │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 四、字段映射详解

### 4.1 Prometheus Alert Labels 映射

| Prometheus Label | 来源表 | 来源字段 | 转换规则 |
|------------------|--------|----------|----------|
| `alertname` | NM_ALARM_CODE_LIB | ALARM_NAME | 直接映射 |
| `instance` | DEVICE | IP_ADDR | 直接映射，无值则用 DEVICE_NAME |
| `severity` | NM_ALARM_CDR | ALARM_LEVEL | 映射：1→critical, 2→error, 3→warning, 4→info |
| `alarm_id` | NM_ALARM_CDR | ALARM_INST_ID | 直接映射（v2.0 核心标识） |
| `alarm_code` | NM_ALARM_CDR | ALARM_CODE | 直接映射 |
| `host` | DEVICE | DEVICE_NAME | 直接映射 |
| `application` | APP_ENV | APP_NAME | 直接映射 |
| `domain` | SYS_DOMAIN | DOMAIN_NAME | 直接映射 |
| `env` | SYS_DOMAIN | DOMAIN_TYPE | 映射：A→production, T→test, D→dr |
| `resource_type` | NM_ALARM_EVENT | RES_INST_TYPE | 直接映射 |
| `task_type` | NM_ALARM_EVENT | TASK_TYPE | 直接映射（如有值） |
| `source` | 静态配置 | - | 固定值 "zmc" |

### 4.2 Prometheus Alert Annotations 映射

| Prometheus Annotation | 来源表 | 来源字段 | 说明 |
|----------------------|--------|----------|------|
| `summary` | NM_ALARM_CODE_LIB | ALARM_NAME | 告警摘要 |
| `description` | NM_ALARM_EVENT | DETAIL_INFO | 告警详情 + 主机信息组合 |
| `fault_reason` | NM_ALARM_CODE_LIB | FAULT_REASON | 故障原因 |
| `runbook` | NM_ALARM_CODE_LIB | DEAL_SUGGEST | 处理建议 |
| `alarm_type` | NM_ALARM_CODE_LIB | ALARM_TYPE | 告警类型 |
| `data_1` ~ `data_10` | NM_ALARM_EVENT | DATA_1 ~ DATA_10 | 扩展字段 |

### 4.3 时间字段映射

| Prometheus 字段 | 来源表 | 来源字段 | 使用场景 |
|----------------|--------|----------|----------|
| `startsAt` | NM_ALARM_EVENT | EVENT_TIME 或 CREATE_DATE | 告警开始时间 |
| `endsAt` | NM_ALARM_CDR | RESET_DATE / CLEAR_DATE / CONFIRM_DATE | 告警结束时间（根据状态选择） |

---

## 五、核心 SQL 查询

### 5.1 查询活跃告警

```sql
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
        c.RESET_DATE,
        c.CLEAR_DATE,
        c.CONFIRM_DATE,

        -- 最新告警事件详情
        e.EVENT_INST_ID,
        e.EVENT_TIME,
        e.DETAIL_INFO,
        e.DATA_1, e.DATA_2, e.DATA_3, e.DATA_4, e.DATA_5,
        e.DATA_6, e.DATA_7, e.DATA_8, e.DATA_9, e.DATA_10,

        -- 告警码详情
        acl.ALARM_NAME,
        acl.FAULT_REASON,
        acl.DEAL_SUGGEST,

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

    FROM NM_ALARM_CDR c

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
              AND e2.RESET_FLAG = '1'
        )
    ) e ON c.ALARM_CODE = e.ALARM_CODE
        AND c.APP_ENV_ID = e.APP_ENV_ID
        AND c.RES_INST_ID = e.RES_INST_ID

    LEFT JOIN NM_ALARM_CODE_LIB acl ON c.ALARM_CODE = acl.ALARM_CODE
    LEFT JOIN APP_ENV ae ON c.APP_ENV_ID = ae.APP_ENV_ID
    LEFT JOIN DEVICE d ON ae.DEVICE_ID = d.DEVICE_ID
    LEFT JOIN SYS_DOMAIN sd ON ae.SYS_DOMAIN_ID = sd.DOMAIN_ID

    WHERE c.ALARM_STATE = 'U'  -- 只查询活跃告警
      AND NOT EXISTS (
          SELECT 1 FROM NM_ALARM_SYNC_STATUS s
          WHERE s.ALARM_INST_ID = c.ALARM_INST_ID
      )
    ORDER BY c.CREATE_DATE ASC
) WHERE ROWNUM <= :batch_size
```

### 5.2 查询状态变更的告警

```sql
SELECT
    s.SYNC_ID,
    s.ALARM_INST_ID,
    s.SYNC_STATUS,
    s.ZMC_ALARM_STATE AS OLD_ZMC_STATE,
    s.SILENCE_ID,

    -- 当前 CDR 状态
    c.ALARM_STATE AS NEW_ZMC_STATE,
    c.RESET_DATE,
    c.CLEAR_DATE,
    c.CONFIRM_DATE,
    c.CLEAR_REASON,

    -- 其他信息...

FROM NM_ALARM_SYNC_STATUS s
JOIN NM_ALARM_CDR c ON s.ALARM_INST_ID = c.ALARM_INST_ID
-- JOIN 其他表获取详情...

WHERE s.SYNC_STATUS IN ('FIRING', 'PENDING')
  AND c.ALARM_STATE != NVL(s.ZMC_ALARM_STATE, 'U')  -- 状态发生变化
```

---

## 六、功能清单与数据表对应

| 功能 | 读取的表 | 写入的表 | 关键字段 |
|------|----------|----------|----------|
| **新告警同步** | NM_ALARM_CDR, NM_ALARM_EVENT, NM_ALARM_CODE_LIB, APP_ENV, DEVICE, SYS_DOMAIN | NM_ALARM_SYNC_STATUS, NM_ALARM_SYNC_LOG | ALARM_STATE='U' |
| **状态变更检测** | NM_ALARM_CDR, NM_ALARM_SYNC_STATUS | NM_ALARM_SYNC_STATUS, NM_ALARM_SYNC_LOG | ALARM_STATE 变化 |
| **心跳保活** | NM_ALARM_CDR, NM_ALARM_SYNC_STATUS | NM_ALARM_SYNC_STATUS | LAST_PUSH_TIME |
| **静默清理** | NM_ALARM_CDR, NM_ALARM_SYNC_STATUS | NM_ALARM_SYNC_STATUS | SILENCE_ID |
| **告警过滤** | NM_ALARM_CDR | - | ALARM_LEVEL |
| **配置管理** | NM_ALARM_SYNC_CONFIG | NM_ALARM_SYNC_CONFIG | CONFIG_GROUP, CONFIG_KEY |

---

## 七、附录

### 7.1 告警级别映射表

| ZMC ALARM_LEVEL | 含义 | Prometheus severity | OpsGenie priority |
|-----------------|------|---------------------|-------------------|
| 1 | 严重 | critical | P1 |
| 2 | 重要 | error | P2 |
| 3 | 次要 | warning | P3 |
| 4 | 警告 | info | P4 |
| 0 或空 | 未定义 | warning | P3 |

### 7.2 环境类型映射表

| ZMC DOMAIN_TYPE | 含义 | Prometheus env |
|-----------------|------|----------------|
| A | 生产环境 | production |
| T | 测试环境 | test |
| D | 灾备环境 | dr |
| 其他 | 未知 | unknown |

### 7.3 同步状态转换矩阵

| 当前 SYNC_STATUS | ZMC ALARM_STATE 变更 | 目标 SYNC_STATUS | Alertmanager 操作 |
|------------------|---------------------|------------------|-------------------|
| PENDING/FIRING | U → A | RESOLVED | POST resolved alert |
| PENDING/FIRING | U → C | RESOLVED | POST resolved alert |
| PENDING/FIRING | U → M | SILENCED | POST resolved + POST silence |
| SILENCED | M → A | RESOLVED | DELETE silence |
| SILENCED | M → C | RESOLVED | DELETE silence |

---

*文档版本: 2.0.0*
*最后更新: 2024-12*
