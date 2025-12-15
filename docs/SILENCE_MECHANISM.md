# Silence 机制设计文档

## 概述

本文档详细描述 zmc-alarm-exporter 中 Alertmanager Silence（静默）机制的实现逻辑，包括创建时机、匹配规则、生命周期管理以及与告警重触发的交互行为。

## 1. Silence 基本概念

### 1.1 什么是 Silence

Silence 是 Alertmanager 的一种告警抑制机制：
- **作用**: 匹配的告警仍然存在，但不会发送通知
- **范围**: 基于 label 匹配规则
- **时效**: 有明确的开始和结束时间

### 1.2 在 ZMC 场景中的用途

当 ZMC 中的告警被**手工清除（状态 M）** 时，创建 Silence 规则，防止：
- 告警在短时间内重新触发时产生重复通知
- 已处理的告警干扰运维人员

## 2. Silence 创建流程

### 2.1 触发条件

当 ZMC 告警状态变为 `M`（手工清除/屏蔽）时触发。

### 2.2 处理流程

```
ZMC 告警状态 U → M (手工清除)
        │
        ▼
┌─────────────────────────────────────┐
│  步骤 1: 推送 RESOLVED              │
│  - 关闭 OpsGenie 中已存在的告警     │
│  - 确保告警被正确关闭               │
└─────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────┐
│  步骤 2: 创建 Silence 规则          │
│  - 匹配条件: event_id = {当前事件ID} │
│  - 持续时间: 默认 24 小时（可配置）  │
│  - 防止告警重新触发时发送通知        │
└─────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────┐
│  步骤 3: 更新同步状态               │
│  - SYNC_STATUS = 'SILENCED'         │
│  - 记录 SILENCE_ID（Alertmanager返回）│
└─────────────────────────────────────┘
```

### 2.3 代码实现

```python
# sync_service.py: _handle_alarm_silenced()

# 步骤1: 推送 resolved 告警
resolved_alert = self.transformer.transform_to_prometheus(alarm, resolved=True)
resolve_result = await self.am_client.push_single_alert(resolved_alert)

# 步骤2: 创建 Silence 规则
silence = self.transformer.create_silence(alarm, comment="Shielded in ZMC...")
silence_result = await self.am_client.create_silence(silence)

# 步骤3: 更新状态
self.extractor.update_sync_status(
    sync_id=sync_id,
    sync_status="SILENCED",
    silence_id=silence_result.get("silence_id")
)
```

## 3. Silence 匹配规则

### 3.1 当前实现

Silence 基于 `event_id` 标签进行**精确匹配**：

```python
# prometheus.py: PrometheusSilence.create_for_alarm()
matchers = [
    SilenceMatcher(name="event_id", value=str(event_id), isRegex=False, isEqual=True),
]
```

### 3.2 匹配逻辑

```
告警推送时的 Labels:
{
    "alertname": "CPU High Usage (1001)",
    "instance": "192.168.1.100",
    "severity": "critical",
    "alarm_id": "5001",        # ALARM_INST_ID (CDR 唯一标识)
    "event_id": "12345",       # EVENT_INST_ID (事件流水ID)
    "alarm_code": "1001",
    ...
}

Silence 匹配规则:
{
    "matchers": [
        {"name": "event_id", "value": "12345", "isRegex": false, "isEqual": true}
    ]
}

匹配结果: 只有 event_id=12345 的告警会被静默
```

## 4. 告警重触发场景分析

### 4.1 ZMC 告警标识体系

```
NM_ALARM_CDR (告警汇总表)          NM_ALARM_EVENT (告警流水表)
├── ALARM_INST_ID                  ├── EVENT_INST_ID
│   (同一告警源唯一)                │   (每次触发新增)
│                                  │
└── 一条 CDR 对应多条 EVENT        └── 每次告警产生新记录
```

**关键点**: 同一个告警源（相同 ALARM_INST_ID）重新触发时，会产生**新的 EVENT_INST_ID**。

### 4.2 重触发场景时序图

```
时间线:
─────────────────────────────────────────────────────────────────────────────►

T0: 告警首次产生
    ┌─────────────────────────────────────┐
    │ ALARM_INST_ID = 1000                │
    │ EVENT_INST_ID = 12345               │
    │ ALARM_STATE = 'U' (未确认)          │
    └─────────────────────────────────────┘
    │
    └─► 推送 FIRING 到 Alertmanager
        Labels: { event_id: "12345", alarm_id: "1000", ... }
        │
        └─► OpsGenie 创建告警

T1: ZMC 手工清除
    ┌─────────────────────────────────────┐
    │ ALARM_STATE: 'U' → 'M' (手工清除)   │
    └─────────────────────────────────────┘
    │
    ├─► 步骤1: 推送 RESOLVED (event_id=12345)
    │   └─► OpsGenie 关闭告警
    │
    └─► 步骤2: 创建 Silence
        Matchers: [event_id = "12345"]
        Duration: 24 hours
        │
        └─► SYNC_STATUS = 'SILENCED'
            SILENCE_ID = 'abc-123-xyz'

T2: 同一告警重新触发 (Silence 有效期内)
    ┌─────────────────────────────────────┐
    │ ALARM_INST_ID = 1000 (不变)         │
    │ EVENT_INST_ID = 12346 (新的!)       │
    │ ALARM_STATE = 'U'                   │
    └─────────────────────────────────────┘
    │
    └─► 推送 FIRING 到 Alertmanager
        Labels: { event_id: "12346", alarm_id: "1000", ... }
        │
        └─► Silence 匹配检查:
            Silence: event_id = "12345"
            告警:    event_id = "12346"
            结果: ❌ 不匹配
            │
            └─► ✅ 告警正常发送到 OpsGenie

T3: Silence 过期 (24小时后)
    │
    └─► Alertmanager 自动删除 Silence 规则
```

### 4.3 行为总结

| 场景 | EVENT_INST_ID | Silence 匹配 | 通知发送 |
|------|---------------|--------------|----------|
| 首次告警 | 12345 | N/A | ✅ 是 |
| 手工清除 | 12345 | N/A | 推送 RESOLVED |
| 重新触发（Silence 有效） | 12346 (新) | ❌ 不匹配 | ✅ 是 |
| 重新触发（Silence 过期） | 12347 (新) | N/A | ✅ 是 |

### 4.4 设计意图

**这是预期行为，而非 Bug**：

1. **新事件应该被通知**: 新的 `EVENT_INST_ID` 表示新的告警事件，运维人员应该知道
2. **不遗漏告警**: 即使之前手工清除，新告警也会被正常推送
3. **避免信息丢失**: 告警重复发生可能表示问题未真正解决

## 5. Silence 生命周期管理

### 5.1 创建

- **时机**: 告警状态变为 `M`（手工清除）
- **来源**: zmc-alarm-exporter 调用 Alertmanager API
- **存储**: `NM_ALARM_SYNC_STATUS.SILENCE_ID`

### 5.2 持续时间

```python
# config.py
default_duration_hours: int = Field(default=24, description="默认静默时长(小时)")

# 环境变量配置
SILENCE_DEFAULT_DURATION_HOURS=24
```

### 5.3 清理机制

当 ZMC 告警状态从 `M` 变为 `A`（自动恢复）或 `C`（已确认）时：

```python
# sync_service.py: cleanup_silences()

# 查询需要清理的 Silence
silences = self.extractor.extract_silences_to_cleanup()

for silence_data in silences:
    # 删除 Alertmanager 中的 Silence
    await self.am_client.delete_silence(silence_id)

    # 更新同步状态
    self.extractor.update_sync_status(
        sync_id=sync_id,
        sync_status="RESOLVED",
        silence_id=None
    )
```

### 5.4 状态流转

```
                    ┌─────────────┐
                    │   FIRING    │
                    └──────┬──────┘
                           │
           ┌───────────────┴───────────────┐
           │                               │
           ▼                               ▼
    ┌─────────────┐                ┌─────────────┐
    │  RESOLVED   │                │  SILENCED   │
    │  (A/C 状态)  │◄──────────────│  (M 状态)   │
    └─────────────┘   状态变为 A/C  └─────────────┘
                      时清理 Silence
```

## 6. 数据库表设计

### 6.1 NM_ALARM_SYNC_STATUS 表

```sql
CREATE TABLE NM_ALARM_SYNC_STATUS (
    SYNC_ID           NUMBER PRIMARY KEY,
    ALARM_INST_ID     NUMBER NOT NULL,         -- CDR 告警汇总ID
    EVENT_INST_ID     NUMBER,                  -- 最新事件ID
    SYNC_STATUS       VARCHAR2(20),            -- FIRING/RESOLVED/SILENCED
    ZMC_ALARM_STATE   VARCHAR2(10),            -- U/A/M/C
    SILENCE_ID        VARCHAR2(100),           -- Alertmanager Silence ID
    LAST_PUSH_TIME    DATE,
    ...
);

COMMENT ON COLUMN NM_ALARM_SYNC_STATUS.SILENCE_ID IS
    '当告警被静默时，Alertmanager返回的Silence规则ID，用于后续删除静默';
```

### 6.2 Silence 相关查询

```sql
-- 查询需要清理 Silence 的告警
SELECT s.SYNC_ID, s.SILENCE_ID, c.ALARM_STATE
FROM NM_ALARM_SYNC_STATUS s
JOIN NM_ALARM_CDR c ON s.ALARM_INST_ID = c.ALARM_INST_ID
WHERE s.SYNC_STATUS = 'SILENCED'
  AND s.SILENCE_ID IS NOT NULL
  AND c.ALARM_STATE IN ('A', 'C');  -- 已恢复或已确认
```

## 7. 配置参数

| 参数 | 环境变量 | 默认值 | 说明 |
|------|----------|--------|------|
| 默认静默时长 | `SILENCE_DEFAULT_DURATION_HOURS` | 24 | Silence 持续时间（小时） |
| 创建者标识 | - | `zmc-alarm-exporter` | Silence 的 createdBy 字段 |

## 8. Alertmanager API 交互

### 8.1 创建 Silence

```http
POST /api/v2/silences
Content-Type: application/json

{
    "matchers": [
        {
            "name": "event_id",
            "value": "12345",
            "isRegex": false,
            "isEqual": true
        }
    ],
    "startsAt": "2024-01-15T10:00:00Z",
    "endsAt": "2024-01-16T10:00:00Z",
    "createdBy": "zmc-alarm-exporter",
    "comment": "Shielded in ZMC at 2024-01-15 18:00:00. Reason: Manual clear"
}
```

**响应**:
```json
{
    "silenceID": "abc-123-xyz-456"
}
```

### 8.2 删除 Silence

```http
DELETE /api/v2/silences/{silenceID}
```

## 9. 常见问题

### Q1: Silence 过期后会发生什么？

**A**: Silence 在 Alertmanager 中自动过期。由于：
- 新触发的告警有新的 `EVENT_INST_ID`
- Silence 只匹配特定的 `event_id`

因此 Silence 过期对新告警没有影响。

### Q2: 为什么使用 event_id 而不是 alarm_id 匹配？

**A**: 使用 `event_id` 匹配的设计意图：
- **精确匹配**: 只静默特定的告警事件
- **不遗漏告警**: 同一告警源的新事件仍会通知
- **符合运维需求**: 告警重复发生可能表示问题未解决

### Q3: 如何修改为基于 alarm_id 匹配？

如果业务需求是"同一告警源的所有事件都被静默"，可修改：

```python
# prometheus.py: PrometheusSilence.create_for_alarm()
matchers = [
    SilenceMatcher(name="alarm_id", value=str(alarm_inst_id), isRegex=False, isEqual=True),
]
```

### Q4: SILENCE_ID 是从哪里来的？

**A**: `SILENCE_ID` 是 Alertmanager 在创建 Silence 时返回的唯一标识，**不是**从 ZMC 原始表同步的。用于后续删除 Silence 规则。

---

*文档版本: 1.0*
*最后更新: 2024-01*
