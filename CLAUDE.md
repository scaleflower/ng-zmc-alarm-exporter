# ZMC Alarm Exporter

将 ZMC 告警同步到 Prometheus Alertmanager / OpsGenie 的服务。

## 部署信息

- **应用部署**: 10.101.1.42 (root/EnablingSoft@2025)
- **Prometheus/Alertmanager**: 10.101.1.79 (root/EnablingSoft@2025)
- **ZMC Oracle 数据库**:
  - Host: 10.101.1.42
  - Port: 1522
  - Service: rb
  - User: zmc
  - Password: smart

## 架构说明 (v2.0)

### 核心设计：以 NM_ALARM_CDR 为中心

```
NM_ALARM_CDR (告警汇总表)      NM_ALARM_SYNC_STATUS (同步状态表)
├── ALARM_INST_ID (唯一) ──────► ALARM_INST_ID (主关联键)
├── ALARM_STATE (U/A/M/C)       ├── SYNC_STATUS
├── ALARM_CODE                  ├── ZMC_ALARM_STATE
├── APP_ENV_ID                  └── LAST_PUSH_TIME
└── RES_INST_ID
        │
        │ JOIN (获取详情)
        ▼
NM_ALARM_EVENT (告警流水表)
├── EVENT_INST_ID
├── DETAIL_INFO
└── DATA_1 ~ DATA_10
```

### 表关系说明

| 表名 | 用途 | 关键字段 |
|------|------|----------|
| NM_ALARM_CDR | 告警汇总（核心） | ALARM_INST_ID, ALARM_STATE |
| NM_ALARM_EVENT | 告警流水日志 | EVENT_INST_ID, DETAIL_INFO |
| NM_ALARM_SYNC_STATUS | 同步状态跟踪 | ALARM_INST_ID (唯一约束) |

### 状态映射

| ZMC ALARM_STATE | 含义 | 同步操作 |
|-----------------|------|----------|
| U | 未确认 | 推送 FIRING |
| A | 自动恢复 | 推送 RESOLVED |
| M | 手工清除 | 推送 RESOLVED + 创建 Silence |
| C | 已确认 | 推送 RESOLVED |

### 优势

1. **避免历史告警风暴**: 只同步 ALARM_STATE='U' 的活跃告警
2. **天然去重**: 同一告警源只有一条 CDR 记录
3. **状态一致**: 直接对应 OpsGenie 告警模型

## 升级说明

从 v1.x 升级到 v2.0 需要执行数据库迁移脚本:

```bash
sqlplus zmc/smart@10.101.1.42:1522/rb @sql/upgrade_v2_cdr_based.sql
```