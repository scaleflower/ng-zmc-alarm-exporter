# OpsGenie 集成配置指南

## 概述

本文档介绍如何配置 zmc-alarm-exporter 与 OpsGenie 集成。支持两种集成模式：

### 集成模式对比

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| **alertmanager** | 通过 Alertmanager 转发到 OpsGenie | 已有 Prometheus/Alertmanager 基础设施，需要多渠道告警（钉钉+OpsGenie） |
| **opsgenie** | 直连 OpsGenie API | 仅需 OpsGenie 集成，希望简化架构 |

### 架构对比

**模式 1: 通过 Alertmanager (默认)**
```
ZMC 数据库 → zmc-alarm-exporter → Alertmanager → OpsGenie
                                       ↓
                                   钉钉 (可选)
```

**模式 2: 直连 OpsGenie**
```
ZMC 数据库 → zmc-alarm-exporter → OpsGenie API
```

---

## 模式选择

在 `.env` 文件中设置 `INTEGRATION_MODE`：

```bash
# 使用 Alertmanager 转发 (默认)
INTEGRATION_MODE=alertmanager

# 或直连 OpsGenie
INTEGRATION_MODE=opsgenie
```

---

## 模式 1: 通过 Alertmanager 集成 (默认)

## OpsGenie 配置信息

| 配置项 | 值 |
|--------|-----|
| API URL | `https://api.opsgenie.com` |
| API Key | `0458859b-8f30-4bb1-a59a-7e95cb440859` |
| Team | `YTLC BSS OSS L1` |
| Region | `US` |

## Alertmanager 配置

### 配置文件位置

```
服务器: 10.101.1.79
路径: /usr/local/alertmanager/alertmanager.yml
```

### 完整配置示例

```yaml
global:
  resolve_timeout: 5m
  # OpsGenie 全局配置
  opsgenie_api_url: https://api.opsgenie.com
  opsgenie_api_key: 0458859b-8f30-4bb1-a59a-7e95cb440859

route:
  receiver: 'dingding-webhook'
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 1h
  group_by: ['alertname', 'cluster']
  routes:
    # ZMC 告警专用路由 - 发送到钉钉和 OpsGenie
    - match:
        source: zmc
      receiver: 'zmc-opsgenie'
      group_by: ['alertname', 'alarm_code', 'host_name']
      group_wait: 10s
      group_interval: 1m
      repeat_interval: 30m
      continue: true  # 继续匹配下一条路由

    # ZMC 告警 - 钉钉通知
    - match:
        source: zmc
      receiver: 'zmc-dingding-webhook'
      group_by: ['alertname', 'alarm_code', 'host_name']
      group_wait: 10s
      group_interval: 1m
      repeat_interval: 30m

receivers:
# 默认接收器 - 钉钉 webhook1
- name: 'dingding-webhook'
  webhook_configs:
  - url: 'http://10.101.1.79:8060/dingtalk/webhook1/send'
    send_resolved: true

# ZMC 钉钉接收器 - webhook2
- name: 'zmc-dingding-webhook'
  webhook_configs:
  - url: 'http://10.101.1.79:8060/dingtalk/webhook2/send'
    send_resolved: true

# ZMC OpsGenie 接收器
- name: 'zmc-opsgenie'
  opsgenie_configs:
  - api_key: 0458859b-8f30-4bb1-a59a-7e95cb440859
    api_url: https://api.opsgenie.com
    message: '{{ .CommonAnnotations.summary }}'
    description: '{{ .CommonAnnotations.description }}'
    source: 'ZMC Alarm Exporter'
    # 告警详情
    details:
      alarm_code: '{{ .CommonLabels.alarm_code }}'
      host_name: '{{ .CommonLabels.host_name }}'
      severity: '{{ .CommonLabels.severity }}'
      resource: '{{ .CommonLabels.resource }}'
    # 优先级映射
    priority: '{{ if eq .CommonLabels.severity "critical" }}P1{{ else if eq .CommonLabels.severity "error" }}P2{{ else if eq .CommonLabels.severity "warning" }}P3{{ else }}P4{{ end }}'
    # 指定团队
    responders:
    - name: 'YTLC BSS OSS L1'
      type: team
    # 标签
    tags:
    - 'zmc'
    - '{{ .CommonLabels.alarm_code }}'
    send_resolved: true

inhibit_rules:
  - source_match:
      severity: 'critical'
    target_match:
      severity: 'warning'
    equal: ['alertname', 'instance']
```

## 配置步骤

### 1. 备份当前配置

```bash
ssh root@10.101.1.79
cd /usr/local/alertmanager
cp alertmanager.yml alertmanager.yml.bak.$(date +%Y%m%d)
```

### 2. 编辑配置文件

```bash
vim alertmanager.yml
```

### 3. 验证配置语法

```bash
./amtool check-config alertmanager.yml
```

### 4. 重载配置

方法一：发送 SIGHUP 信号
```bash
kill -HUP $(pgrep alertmanager)
```

方法二：调用 API
```bash
curl -X POST http://localhost:9093/-/reload
```

方法三：重启服务
```bash
systemctl restart alertmanager
# 或
./alertmanager --config.file=alertmanager.yml &
```

### 5. 验证配置生效

```bash
# 查看当前配置
curl -s http://localhost:9093/api/v2/status | jq '.config'

# 查看接收器列表
curl -s http://localhost:9093/api/v2/receivers | jq '.[].name'
```

## OpsGenie 优先级映射

| ZMC 级别 | Prometheus Severity | OpsGenie Priority | 说明 |
|----------|---------------------|-------------------|------|
| 1 | critical | P1 | 严重 - 立即响应 |
| 2 | error | P2 | 重要 - 高优先级 |
| 3 | warning | P3 | 次要 - 中优先级 |
| 4 | info | P4 | 警告 - 低优先级 |

## 告警字段映射

| OpsGenie 字段 | 来源 | 说明 |
|---------------|------|------|
| message | `summary` annotation | 告警摘要 |
| description | `description` annotation | 详细描述 |
| alias | `alertname` + `alarm_code` | 告警唯一标识（用于去重） |
| priority | severity 映射 | P1-P5 |
| responders | 配置的 team | YTLC BSS OSS L1 |
| tags | labels | zmc, alarm_code |
| details | labels | 所有告警标签 |

## 测试告警

### 发送测试告警

```bash
curl -X POST http://10.101.1.79:9093/api/v2/alerts \
  -H "Content-Type: application/json" \
  -d '[{
    "labels": {
      "alertname": "TestAlert",
      "source": "zmc",
      "severity": "warning",
      "alarm_code": "TEST001",
      "host_name": "test-server"
    },
    "annotations": {
      "summary": "测试告警",
      "description": "这是一条测试告警，用于验证 OpsGenie 集成"
    }
  }]'
```

### 发送恢复通知

```bash
curl -X POST http://10.101.1.79:9093/api/v2/alerts \
  -H "Content-Type: application/json" \
  -d '[{
    "labels": {
      "alertname": "TestAlert",
      "source": "zmc",
      "severity": "warning",
      "alarm_code": "TEST001",
      "host_name": "test-server"
    },
    "annotations": {
      "summary": "测试告警",
      "description": "这是一条测试告警，用于验证 OpsGenie 集成"
    },
    "endsAt": "2025-01-01T00:00:00Z"
  }]'
```

## 常见问题

### Q1: 告警发送失败

检查 Alertmanager 日志：
```bash
journalctl -u alertmanager -f
# 或
tail -f /var/log/alertmanager.log
```

### Q2: OpsGenie 未收到告警

1. 检查 API Key 是否正确
2. 检查网络是否可达 `api.opsgenie.com`
3. 检查 Team 名称是否存在于 OpsGenie

```bash
# 测试网络连通性
curl -I https://api.opsgenie.com

# 测试 API Key
curl -X GET 'https://api.opsgenie.com/v2/teams' \
  -H 'Authorization: GenieKey 0458859b-8f30-4bb1-a59a-7e95cb440859'
```

### Q3: 告警重复

检查路由配置中的 `group_by` 和 `repeat_interval` 设置。

## 回滚配置

如需回滚到原始配置：

```bash
ssh root@10.101.1.79
cd /usr/local/alertmanager
cp alertmanager.yml.bak.YYYYMMDD alertmanager.yml
kill -HUP $(pgrep alertmanager)
```

---

## 模式 2: 直连 OpsGenie (新增)

### 配置步骤

#### 1. 修改 `.env` 文件

```bash
# 切换到直连模式
INTEGRATION_MODE=opsgenie

# OpsGenie 配置
OPSGENIE_API_URL=https://api.opsgenie.com
OPSGENIE_API_KEY=0458859b-8f30-4bb1-a59a-7e95cb440859
OPSGENIE_DEFAULT_TEAM=YTLC BSS OSS L1
OPSGENIE_DEFAULT_PRIORITY=P3
OPSGENIE_TIMEOUT=30
OPSGENIE_RETRY_COUNT=3
OPSGENIE_RETRY_INTERVAL=1000
```

#### 2. 重启服务

```bash
# Docker 部署
docker-compose restart

# 或直接运行
python -m app.main
```

### 告警字段映射

| ZMC 字段 | OpsGenie 字段 | 说明 |
|----------|---------------|------|
| alertname | message | 告警标题 (限130字符) |
| alarm_inst_id | alias | 唯一标识，用于去重和关闭 (格式: zmc-{id}) |
| description | description | 详细描述 (限15000字符) |
| severity | priority | 优先级映射 (见下表) |
| 所有 labels | details | 作为告警详情存储 |
| alarm_code, source | tags | 告警标签 |

### 优先级映射

| ZMC 级别 | Prometheus Severity | OpsGenie Priority | 说明 |
|----------|---------------------|-------------------|------|
| 1 | critical | P1 | 严重 - 立即响应 |
| 2 | error | P2 | 重要 - 高优先级 |
| 3 | warning | P3 | 次要 - 中优先级 |
| 4 | info | P4 | 警告 - 低优先级 |

### 静默处理差异

OpsGenie 没有 Alertmanager 风格的 Silence API，处理方式如下：

| ZMC 操作 | Alertmanager 模式 | OpsGenie 直连模式 |
|----------|-------------------|-------------------|
| 手工清除 (M) | 创建 Silence 规则 | 调用 Acknowledge API |
| 恢复告警 | 推送带 endsAt 的告警 | 调用 Close API |
| 删除静默 | 调用 DELETE /silences | 调用 Close API |

### 测试 OpsGenie 直连

```bash
# 检查健康状态
curl http://localhost:8080/health

# 手动触发同步
curl -X POST http://localhost:8080/api/v1/sync/trigger

# 查看同步日志
curl http://localhost:8080/api/v1/sync/logs
```

### 验证 API Key

```bash
# 测试 API Key 有效性
curl -X GET 'https://api.opsgenie.com/v2/account' \
  -H 'Authorization: GenieKey YOUR_API_KEY'
```

---

## 参考文档

- [Alertmanager Configuration](https://prometheus.io/docs/alerting/latest/configuration/)
- [OpsGenie Alertmanager Integration](https://support.atlassian.com/opsgenie/docs/integrate-opsgenie-with-prometheus/)
- [OpsGenie API Documentation](https://docs.opsgenie.com/docs/alert-api)
- [OpsGenie Alert API (continued)](https://docs.opsgenie.com/docs/alert-api-continued)
