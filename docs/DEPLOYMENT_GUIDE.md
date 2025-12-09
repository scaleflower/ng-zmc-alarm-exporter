# ZMC Alarm Exporter 部署指南

## 目录

1. [项目概述](#1-项目概述)
2. [系统架构](#2-系统架构)
3. [环境要求](#3-环境要求)
4. [安装部署](#4-安装部署)
5. [配置说明](#5-配置说明)
6. [数据库初始化](#6-数据库初始化)
7. [API 接口文档](#7-api-接口文档)
8. [运维管理](#8-运维管理)
9. [故障排查](#9-故障排查)
10. [附录](#10-附录)

---

## 1. 项目概述

### 1.1 背景

ZMC (Z-Smart Management Center) 是企业内部的网络管理和监控平台，告警数据存储在 Oracle 数据库的 `NM_ALARM_EVENT` 表中。为了与 OpsGenie 等现代运维平台集成，需要将 ZMC 告警转换为 Prometheus 格式。

### 1.2 解决方案

本项目实现了一个中间服务，负责：
- 从 Oracle 数据库抽取 ZMC 告警
- 转换为 Prometheus Alertmanager 格式
- 推送到 Alertmanager
- 由 Alertmanager 转发到 OpsGenie

### 1.3 核心功能

| 功能 | 说明 |
|------|------|
| 告警同步 | 实时检测新告警并推送到 Alertmanager |
| 状态跟踪 | 跟踪告警恢复、清除、屏蔽等状态变更 |
| 心跳保活 | 定期重推活跃告警，防止自动解除 |
| 静默管理 | 使用 Silence API 处理屏蔽的告警 |
| 级别过滤 | 可配置只同步特定级别的告警 |
| 操作日志 | 完整记录所有同步操作 |
| Prometheus 指标 | 导出服务运行指标 |
| REST API | 提供管理和监控接口 |

---

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           ZMC 系统                                       │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    Oracle Database                               │   │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────┐  │   │
│  │  │ NM_ALARM_EVENT   │  │ NM_ALARM_CODE_LIB│  │ DEVICE        │  │   │
│  │  │ (告警事件表)      │  │ (告警代码库)      │  │ (设备表)       │  │   │
│  │  └──────────────────┘  └──────────────────┘  └───────────────┘  │   │
│  │                                                                  │   │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────┐  │   │
│  │  │NM_ALARM_SYNC_    │  │NM_ALARM_SYNC_    │  │NM_ALARM_SYNC_ │  │   │
│  │  │STATUS (同步状态) │  │LOG (同步日志)     │  │CONFIG (配置)   │  │   │
│  │  └──────────────────┘  └──────────────────┘  └───────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ 抽取告警
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      ZMC Alarm Exporter                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │ Oracle      │  │ Alarm       │  │ Alarm       │  │Alertmanager │    │
│  │ Client      │─>│ Extractor   │─>│ Transformer │─>│ Client      │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
│         │                                                    │          │
│         │              ┌─────────────────┐                  │          │
│         │              │   Sync Service  │                  │          │
│         └──────────────│  (主控服务)      │──────────────────┘          │
│                        └─────────────────┘                              │
│                               │                                         │
│                        ┌──────┴──────┐                                 │
│                        │  FastAPI    │                                 │
│                        │  (HTTP API) │                                 │
│                        └─────────────┘                                 │
│                         :8080                                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ 推送告警 (HTTP POST)
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Prometheus Alertmanager                             │
│                            :9093                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  - 告警聚合                                                      │   │
│  │  - 路由分发                                                      │   │
│  │  - 抑制规则                                                      │   │
│  │  - 静默管理                                                      │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ 转发告警 (OpsGenie API)
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           OpsGenie                                       │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  - 告警管理                                                      │   │
│  │  - 值班调度                                                      │   │
│  │  - 通知分发 (邮件/短信/电话/App)                                  │   │
│  │  - 升级策略                                                      │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流程

```
1. 告警产生流程 (新告警)
   NM_ALARM_EVENT (状态: U - 未确认)
   → Exporter 检测到新告警
   → 转换为 Prometheus 格式
   → 推送 FIRING 告警到 Alertmanager
   → Alertmanager 路由到 OpsGenie
   → OpsGenie 创建告警并通知
   → 记录同步状态 (FIRING)

2. 告警自动恢复流程 (问题解决)
   NM_ALARM_EVENT (状态变更: U → A)
   → Exporter 检测到状态变更
   → 推送 RESOLVED 告警到 Alertmanager
   → Alertmanager 转发到 OpsGenie
   → OpsGenie 自动关闭告警
   → 更新同步状态 (RESOLVED)

3. 告警确认流程 (运维确认)
   NM_ALARM_EVENT (状态变更: U → C)
   → Exporter 检测到状态变更
   → 推送 RESOLVED 告警到 Alertmanager
   → Alertmanager 转发到 OpsGenie
   → OpsGenie 自动关闭告警
   → 更新同步状态 (RESOLVED)

4. 告警手工清除/屏蔽流程 (运维手动处理)
   NM_ALARM_EVENT (状态变更: U → M)
   → Exporter 检测到手工清除
   → 步骤1: 推送 RESOLVED 告警 → OpsGenie 关闭当前告警
   → 步骤2: 创建 Alertmanager Silence → 防止告警重新触发
   → 更新同步状态 (SILENCED)

   注意: 两步操作确保:
   - OpsGenie 中已存在的告警被关闭
   - 如果告警再次产生(未真正恢复)，会被 Silence 拦截，不会通知

5. 心跳保活流程
   定时任务 (每 heartbeat_interval 秒)
   → 查询状态为 FIRING 的告警
   → 重新推送到 Alertmanager
   → 防止 Alertmanager 因超时自动解除告警
```

### 2.3 状态同步对照表

| ZMC 状态变更 | 含义 | Exporter 操作 | Alertmanager | OpsGenie |
|-------------|------|---------------|--------------|----------|
| 新建 (U) | 新告警产生 | 推送 FIRING | 创建告警 | 创建告警+通知 |
| U → A | 自动恢复 | 推送 RESOLVED | 关闭告警 | 关闭告警 |
| U → C | 运维确认 | 推送 RESOLVED | 关闭告警 | 关闭告警 |
| U → M | 手工清除 | RESOLVED + Silence | 关闭+静默 | 关闭告警 |

### 2.4 模块说明

| 模块 | 文件 | 职责 |
|------|------|------|
| 配置管理 | `app/config.py` | 加载和管理所有配置项 |
| 数据模型 | `app/models/` | 定义数据结构 |
| Oracle 客户端 | `app/services/oracle_client.py` | 数据库连接和查询 |
| 告警抽取器 | `app/services/alarm_extractor.py` | 从数据库抽取告警 |
| 告警转换器 | `app/services/alarm_transformer.py` | 格式转换和过滤 |
| Alertmanager 客户端 | `app/services/alertmanager_client.py` | 与 Alertmanager 交互 |
| 同步服务 | `app/services/sync_service.py` | 核心同步逻辑 |
| API 路由 | `app/api/` | HTTP 接口 |

---

## 3. 环境要求

### 3.1 软件要求

| 组件 | 版本要求 | 说明 |
|------|----------|------|
| Python | 3.10+ | 推荐 3.11 |
| Oracle Database | 11g+ | ZMC 数据库 |
| Oracle Instant Client | 19c+ | Python oracledb 驱动依赖 |
| Prometheus Alertmanager | 0.24+ | 推荐 0.26 |
| Docker | 20.10+ | 可选，用于容器化部署 |
| Docker Compose | 2.0+ | 可选 |

### 3.2 硬件要求

| 资源 | 最小配置 | 推荐配置 |
|------|----------|----------|
| CPU | 1 核 | 2 核 |
| 内存 | 512 MB | 1 GB |
| 磁盘 | 1 GB | 5 GB |

### 3.3 网络要求

| 源 | 目标 | 端口 | 协议 | 说明 |
|----|------|------|------|------|
| Exporter | Oracle DB | 1521/1522 | TCP | 数据库连接 |
| Exporter | Alertmanager | 9093 | HTTP | 推送告警 |
| Prometheus | Exporter | 8080 | HTTP | 抓取指标 |
| 管理客户端 | Exporter | 8080 | HTTP | API 访问 |

---

## 4. 安装部署

### 4.1 方式一：本地部署

#### 4.1.1 安装 Oracle Instant Client

```bash
# macOS (使用 Homebrew)
brew tap InstantClientTap/instantclient
brew install instantclient-basic

# Linux (以 Oracle Linux/RHEL 为例)
yum install oracle-instantclient19.8-basic

# 设置环境变量
export LD_LIBRARY_PATH=/usr/lib/oracle/19.8/client64/lib:$LD_LIBRARY_PATH
```

#### 4.1.2 创建 Python 环境

```bash
# 进入项目目录
cd /path/to/zmc-alarm-exporter

# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate  # Linux/macOS
# 或
venv\Scripts\activate     # Windows

# 安装依赖
pip install -r requirements.txt
```

#### 4.1.3 配置环境变量

```bash
# 复制配置模板
cp .env.example .env

# 编辑配置文件
vim .env
```

#### 4.1.4 启动服务

```bash
# 开发模式（支持热重载）
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

# 生产模式
uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 1

# 使用 gunicorn（推荐生产环境）
gunicorn app.main:app -w 1 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8080
```

### 4.2 方式二：Docker 部署

#### 4.2.1 构建镜像

```bash
# 构建镜像
docker build -t zmc-alarm-exporter:latest .

# 查看镜像
docker images | grep zmc-alarm-exporter
```

#### 4.2.2 运行容器

```bash
# 使用 docker run
docker run -d \
  --name zmc-alarm-exporter \
  -p 8080:8080 \
  -e ZMC_ORACLE_HOST=10.101.1.42 \
  -e ZMC_ORACLE_PORT=1522 \
  -e ZMC_ORACLE_SERVICE_NAME=rb \
  -e ZMC_ORACLE_USERNAME=zmc \
  -e ZMC_ORACLE_PASSWORD=smart \
  -e ALERTMANAGER_URL=http://alertmanager:9093 \
  zmc-alarm-exporter:latest
```

#### 4.2.3 使用 Docker Compose

```bash
# 创建 .env 文件
cp .env.example .env
vim .env

# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f zmc-alarm-exporter

# 停止服务
docker-compose down
```

### 4.3 方式三：Kubernetes 部署

#### 4.3.1 创建 ConfigMap

```yaml
# configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: zmc-alarm-exporter-config
data:
  SYNC_SCAN_INTERVAL: "60"
  SYNC_ALARM_LEVELS: "1,2,3,4"
  LOG_LEVEL: "INFO"
  LOG_FORMAT: "json"
```

#### 4.3.2 创建 Secret

```yaml
# secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: zmc-alarm-exporter-secret
type: Opaque
stringData:
  ZMC_ORACLE_PASSWORD: "smart"
  OPSGENIE_API_KEY: "your-api-key"
```

#### 4.3.3 创建 Deployment

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: zmc-alarm-exporter
spec:
  replicas: 1
  selector:
    matchLabels:
      app: zmc-alarm-exporter
  template:
    metadata:
      labels:
        app: zmc-alarm-exporter
    spec:
      containers:
      - name: exporter
        image: zmc-alarm-exporter:latest
        ports:
        - containerPort: 8080
        env:
        - name: ZMC_ORACLE_HOST
          value: "10.101.1.42"
        - name: ZMC_ORACLE_PORT
          value: "1522"
        - name: ZMC_ORACLE_SERVICE_NAME
          value: "rb"
        - name: ZMC_ORACLE_USERNAME
          value: "zmc"
        - name: ZMC_ORACLE_PASSWORD
          valueFrom:
            secretKeyRef:
              name: zmc-alarm-exporter-secret
              key: ZMC_ORACLE_PASSWORD
        - name: ALERTMANAGER_URL
          value: "http://alertmanager:9093"
        envFrom:
        - configMapRef:
            name: zmc-alarm-exporter-config
        livenessProbe:
          httpGet:
            path: /health/live
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 10
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
```

#### 4.3.4 创建 Service

```yaml
# service.yaml
apiVersion: v1
kind: Service
metadata:
  name: zmc-alarm-exporter
spec:
  selector:
    app: zmc-alarm-exporter
  ports:
  - port: 8080
    targetPort: 8080
```

---

## 5. 配置说明

### 5.1 配置文件结构

所有配置通过环境变量加载，支持 `.env` 文件。

### 5.2 Oracle 数据库配置

| 环境变量 | 说明 | 默认值 | 示例 |
|----------|------|--------|------|
| `ZMC_ORACLE_HOST` | 数据库主机地址 | localhost | 10.101.1.42 |
| `ZMC_ORACLE_PORT` | 数据库端口 | 1521 | 1522 |
| `ZMC_ORACLE_SERVICE_NAME` | Oracle 服务名 | ORCL | rb |
| `ZMC_ORACLE_USERNAME` | 用户名 | zmc | zmc |
| `ZMC_ORACLE_PASSWORD` | 密码 | - | smart |
| `ZMC_ORACLE_POOL_MIN` | 连接池最小连接数 | 2 | 2 |
| `ZMC_ORACLE_POOL_MAX` | 连接池最大连接数 | 10 | 10 |
| `ZMC_ORACLE_TIMEOUT` | 连接超时（秒） | 30 | 30 |

### 5.3 Alertmanager 配置

| 环境变量 | 说明 | 默认值 | 示例 |
|----------|------|--------|------|
| `ALERTMANAGER_URL` | Alertmanager 地址 | http://localhost:9093 | http://alertmanager:9093 |
| `ALERTMANAGER_API_VERSION` | API 版本 | v2 | v2 |
| `ALERTMANAGER_AUTH_ENABLED` | 是否启用认证 | false | true |
| `ALERTMANAGER_USERNAME` | Basic Auth 用户名 | - | admin |
| `ALERTMANAGER_PASSWORD` | Basic Auth 密码 | - | password |
| `ALERTMANAGER_TIMEOUT` | 请求超时（秒） | 30 | 30 |
| `ALERTMANAGER_RETRY_COUNT` | 重试次数 | 3 | 3 |
| `ALERTMANAGER_RETRY_INTERVAL` | 重试间隔（毫秒） | 1000 | 1000 |

### 5.4 同步服务配置

| 环境变量 | 说明 | 默认值 | 示例 |
|----------|------|--------|------|
| `SYNC_ENABLED` | 是否启用同步服务 | true | true |
| `SYNC_SCAN_INTERVAL` | 扫描间隔（秒） | 60 | 60 |
| `SYNC_HEARTBEAT_INTERVAL` | 心跳间隔（秒） | 120 | 120 |
| `SYNC_BATCH_SIZE` | 批处理大小 | 100 | 100 |
| `SYNC_SYNC_ON_STARTUP` | 启动时同步历史告警 | true | true |
| `SYNC_HISTORY_HOURS` | 历史回溯时长（小时） | 24 | 24 |
| `SYNC_ALARM_LEVELS` | 同步的 ZMC 告警级别 | 1,2,3,4 | 1,2 |
| `SYNC_SEVERITY_FILTER` | Prometheus severity 过滤 | - | critical,error |

### 5.5 告警级别过滤

#### 5.5.1 ZMC 告警级别

| 级别 | 说明 | 映射 Severity |
|------|------|---------------|
| 1 | 严重 | critical |
| 2 | 重要 | error |
| 3 | 次要 | warning |
| 4 | 警告 | info |

#### 5.5.2 配置示例

```bash
# 只同步严重和重要告警
SYNC_ALARM_LEVELS=1,2

# 同步所有级别
SYNC_ALARM_LEVELS=1,2,3,4

# 只同步映射后为 critical 或 error 的告警
SYNC_SEVERITY_FILTER=critical,error
```

### 5.6 静默策略配置

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `SILENCE_USE_SILENCE_API` | 使用 Silence API 处理屏蔽 | true |
| `SILENCE_DEFAULT_DURATION_HOURS` | 默认静默时长（小时） | 24 |
| `SILENCE_AUTO_REMOVE_ON_CLEAR` | 告警清除时自动移除静默 | true |
| `SILENCE_COMMENT_TEMPLATE` | 静默注释模板 | Silenced by ZMC at {time}. Operator: {operator} |

### 5.7 告警级别映射配置

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `SEVERITY_LEVEL_0` | 级别 0 (未定义) 映射 | warning |
| `SEVERITY_LEVEL_1` | 级别 1 (严重) 映射 | critical |
| `SEVERITY_LEVEL_2` | 级别 2 (重要) 映射 | error |
| `SEVERITY_LEVEL_3` | 级别 3 (次要) 映射 | warning |
| `SEVERITY_LEVEL_4` | 级别 4 (警告) 映射 | info |

### 5.8 静态标签配置

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `LABEL_SOURCE` | 告警来源标识 | zmc |
| `LABEL_CLUSTER` | 集群名称 | - |
| `LABEL_DATACENTER` | 数据中心 | - |

### 5.9 日志配置

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `LOG_LEVEL` | 日志级别 | INFO |
| `LOG_FORMAT` | 日志格式 (json/text) | json |
| `LOG_RETENTION_DAYS` | 日志保留天数 | 30 |

---

## 6. 数据库初始化

### 6.1 辅助表说明

本项目创建 4 个辅助表，不修改原有 ZMC 表结构：

| 表名 | 说明 |
|------|------|
| `NM_ALARM_SYNC_CONFIG` | 配置表，存储运行时配置 |
| `NM_ALARM_SYNC_STATUS` | 同步状态表，跟踪每个告警的同步状态 |
| `NM_ALARM_SYNC_LOG` | 同步日志表，记录所有同步操作 |
| `NM_ALARM_LABEL_MAPPING` | 标签映射表，字段到标签的映射规则 |

### 6.2 执行初始化脚本

```bash
# 使用 SQLPlus
sqlplus zmc/smart@//10.101.1.42:1522/rb @sql/init_sync_tables.sql

# 或使用 SQL Developer 执行脚本内容
```

### 6.3 表结构详情

#### 6.3.1 NM_ALARM_SYNC_CONFIG

```sql
CREATE TABLE NM_ALARM_SYNC_CONFIG (
    CONFIG_ID      NUMBER PRIMARY KEY,          -- 配置ID
    CONFIG_KEY     VARCHAR2(100) NOT NULL,      -- 配置键名
    CONFIG_VALUE   VARCHAR2(1000),              -- 配置值
    CONFIG_GROUP   VARCHAR2(50),                -- 配置分组
    DESCRIPTION    VARCHAR2(500),               -- 配置描述
    IS_ACTIVE      NUMBER(1) DEFAULT 1,         -- 是否启用
    CREATE_TIME    DATE DEFAULT SYSDATE,        -- 创建时间
    UPDATE_TIME    DATE                         -- 更新时间
);
```

#### 6.3.2 NM_ALARM_SYNC_STATUS

```sql
CREATE TABLE NM_ALARM_SYNC_STATUS (
    SYNC_ID         NUMBER PRIMARY KEY,         -- 同步记录ID
    EVENT_INST_ID   NUMBER NOT NULL,            -- 关联告警事件ID
    ALARM_INST_ID   NUMBER,                     -- 关联告警实例ID
    SYNC_STATUS     VARCHAR2(20) NOT NULL,      -- 同步状态
    ZMC_ALARM_STATE VARCHAR2(10),               -- ZMC原始告警状态
    SILENCE_ID      VARCHAR2(100),              -- Alertmanager静默ID
    LAST_PUSH_TIME  DATE,                       -- 最后推送时间
    ERROR_COUNT     NUMBER DEFAULT 0,           -- 错误计数
    LAST_ERROR      VARCHAR2(1000),             -- 最后错误信息
    CREATE_TIME     DATE DEFAULT SYSDATE,       -- 创建时间
    UPDATE_TIME     DATE                        -- 更新时间
);
```

#### 6.3.3 NM_ALARM_SYNC_LOG

```sql
CREATE TABLE NM_ALARM_SYNC_LOG (
    LOG_ID          NUMBER PRIMARY KEY,         -- 日志ID
    OPERATION       VARCHAR2(50) NOT NULL,      -- 操作类型
    EVENT_INST_ID   NUMBER,                     -- 关联告警事件ID
    SYNC_BATCH_ID   VARCHAR2(50),               -- 同步批次ID
    OLD_STATUS      VARCHAR2(20),               -- 变更前状态
    NEW_STATUS      VARCHAR2(20),               -- 变更后状态
    REQUEST_URL     VARCHAR2(500),              -- 请求URL
    REQUEST_METHOD  VARCHAR2(10),               -- 请求方法
    RESPONSE_CODE   NUMBER,                     -- 响应状态码
    DURATION_MS     NUMBER,                     -- 请求耗时(毫秒)
    ERROR_MESSAGE   VARCHAR2(2000),             -- 错误信息
    CREATE_TIME     DATE DEFAULT SYSDATE        -- 创建时间
);
```

### 6.4 验证初始化

```sql
-- 检查表是否创建成功
SELECT table_name FROM user_tables
WHERE table_name LIKE 'NM_ALARM_SYNC%';

-- 检查初始配置
SELECT config_key, config_value, config_group
FROM nm_alarm_sync_config
WHERE is_active = 1;

-- 检查序列
SELECT sequence_name FROM user_sequences
WHERE sequence_name LIKE 'NM_ALARM_SYNC%';
```

---

## 7. API 接口文档

### 7.1 接口概览

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 应用信息 |
| `/health` | GET | 完整健康检查 |
| `/health/live` | GET | 存活探针 |
| `/health/ready` | GET | 就绪探针 |
| `/metrics` | GET | Prometheus 指标 |
| `/api/v1/sync/status` | GET | 同步状态 |
| `/api/v1/sync/trigger` | POST | 手动触发同步 |
| `/api/v1/sync/alarms` | GET | 已同步告警列表 |
| `/api/v1/sync/logs` | GET | 同步日志 |
| `/api/v1/sync/statistics` | GET | 同步统计 |
| `/api/v1/admin/config` | GET | 获取配置 |
| `/api/v1/admin/config/{key}` | PUT | 更新配置 |
| `/api/v1/admin/alertmanager/status` | GET | Alertmanager 状态 |
| `/api/v1/admin/service/control` | POST | 服务控制 |

### 7.2 健康检查

#### GET /health

完整健康检查，检查所有依赖组件。

**响应示例:**

```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "version": "1.0.0",
  "components": {
    "oracle": {
      "status": "healthy",
      "message": "Connected"
    },
    "alertmanager": {
      "status": "healthy",
      "message": "Connected"
    },
    "sync_service": {
      "status": "healthy",
      "message": "Running"
    }
  }
}
```

#### GET /health/live

Kubernetes 存活探针。

**响应示例:**

```json
{
  "status": "alive",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

#### GET /health/ready

Kubernetes 就绪探针。

**响应示例:**

```json
{
  "ready": true,
  "timestamp": "2024-01-15T10:30:00Z",
  "checks": {
    "oracle": "ok",
    "sync_service": "ok"
  }
}
```

### 7.3 同步管理

#### GET /api/v1/sync/status

获取同步服务状态。

**响应示例:**

```json
{
  "running": true,
  "enabled": true,
  "scan_interval": 60,
  "alarm_levels": "1,2,3,4",
  "severity_filter": null
}
```

#### POST /api/v1/sync/trigger

手动触发一次完整同步。

**响应示例:**

```json
{
  "batch_id": "20240115103000_a1b2c3d4",
  "new_alarms": {
    "extracted": 10,
    "filtered": 2,
    "pushed": 8,
    "errors": 0
  },
  "status_changes": {
    "detected": 3,
    "resolved": 2,
    "silenced": 1,
    "errors": 0
  },
  "heartbeat": {
    "heartbeat_count": 15,
    "errors": 0
  },
  "silences_cleanup": {
    "removed": 1,
    "errors": 0
  }
}
```

#### GET /api/v1/sync/alarms

获取已同步告警列表。

**参数:**

| 参数 | 类型 | 说明 |
|------|------|------|
| status | string | 过滤状态: FIRING, RESOLVED, SILENCED |
| limit | int | 返回数量限制 (默认 100) |
| offset | int | 分页偏移 (默认 0) |

**响应示例:**

```json
[
  {
    "event_inst_id": 12345,
    "alarm_inst_id": 67890,
    "sync_status": "FIRING",
    "zmc_alarm_state": "U",
    "silence_id": null,
    "last_push_time": "2024-01-15T10:30:00Z",
    "error_count": 0
  }
]
```

#### GET /api/v1/sync/logs

获取同步日志。

**参数:**

| 参数 | 类型 | 说明 |
|------|------|------|
| operation | string | 过滤操作类型 |
| event_id | int | 过滤事件ID |
| limit | int | 返回数量限制 |
| offset | int | 分页偏移 |

**响应示例:**

```json
[
  {
    "log_id": 1001,
    "operation": "PUSH_FIRING",
    "event_inst_id": 12345,
    "sync_batch_id": "20240115103000_a1b2c3d4",
    "old_status": null,
    "new_status": "FIRING",
    "response_code": 200,
    "error_message": null,
    "create_time": "2024-01-15T10:30:00Z"
  }
]
```

#### GET /api/v1/sync/statistics

获取同步统计信息。

**响应示例:**

```json
{
  "total_synced": 1000,
  "firing": 50,
  "resolved": 940,
  "silenced": 10,
  "errors": 5,
  "last_24h_operations": 200
}
```

### 7.4 管理接口

#### GET /api/v1/admin/config

获取配置列表。

**参数:**

| 参数 | 类型 | 说明 |
|------|------|------|
| group | string | 过滤配置分组 |

**响应示例:**

```json
[
  {
    "config_key": "SCAN_INTERVAL",
    "config_value": "60",
    "config_group": "SYNC",
    "description": "扫描间隔(秒)"
  }
]
```

#### PUT /api/v1/admin/config/{key}

更新配置项。

**请求体:**

```json
{
  "config_value": "30"
}
```

**响应示例:**

```json
{
  "success": true,
  "config_key": "SCAN_INTERVAL",
  "config_value": "30",
  "message": "Configuration updated. Restart may be required for some settings."
}
```

#### GET /api/v1/admin/alertmanager/status

获取 Alertmanager 状态信息。

**响应示例:**

```json
{
  "url": "http://alertmanager:9093",
  "healthy": true,
  "version": "0.26.0",
  "cluster_status": "ready",
  "active_alerts": 50,
  "active_silences": 5
}
```

#### POST /api/v1/admin/service/control

控制同步服务。

**请求体:**

```json
{
  "action": "restart"  // start, stop, restart
}
```

**响应示例:**

```json
{
  "success": true,
  "action": "restart",
  "message": "Sync service restarted"
}
```

### 7.5 Prometheus 指标

#### GET /metrics

返回 Prometheus 格式的指标。

**主要指标:**

| 指标名 | 类型 | 说明 |
|--------|------|------|
| `zmc_sync_total` | Counter | 同步操作总数 |
| `zmc_alarms_processed_total` | Counter | 处理告警总数 |
| `zmc_active_alarms` | Gauge | 当前活跃告警数 |
| `zmc_sync_duration_seconds` | Histogram | 同步操作耗时 |
| `zmc_db_query_duration_seconds` | Histogram | 数据库查询耗时 |
| `zmc_alertmanager_request_duration_seconds` | Histogram | Alertmanager 请求耗时 |
| `zmc_errors_total` | Counter | 错误总数 |
| `zmc_last_sync_timestamp_seconds` | Gauge | 最后同步时间戳 |
| `zmc_sync_service_up` | Gauge | 同步服务状态 |

---

## 8. 运维管理

### 8.1 日常运维

#### 8.1.1 查看服务状态

```bash
# 健康检查
curl http://localhost:8080/health

# 同步状态
curl http://localhost:8080/api/v1/sync/status

# 统计信息
curl http://localhost:8080/api/v1/sync/statistics
```

#### 8.1.2 手动触发同步

```bash
curl -X POST http://localhost:8080/api/v1/sync/trigger
```

#### 8.1.3 服务控制

```bash
# 停止同步服务
curl -X POST http://localhost:8080/api/v1/admin/service/control \
  -H "Content-Type: application/json" \
  -d '{"action": "stop"}'

# 启动同步服务
curl -X POST http://localhost:8080/api/v1/admin/service/control \
  -H "Content-Type: application/json" \
  -d '{"action": "start"}'

# 重启同步服务
curl -X POST http://localhost:8080/api/v1/admin/service/control \
  -H "Content-Type: application/json" \
  -d '{"action": "restart"}'
```

### 8.2 日志管理

#### 8.2.1 查看应用日志

```bash
# Docker 日志
docker logs -f zmc-alarm-exporter

# 或者
docker-compose logs -f zmc-alarm-exporter
```

#### 8.2.2 查看数据库同步日志

```sql
-- 最近 100 条日志
SELECT * FROM NM_ALARM_SYNC_LOG
ORDER BY CREATE_TIME DESC
FETCH FIRST 100 ROWS ONLY;

-- 错误日志
SELECT * FROM NM_ALARM_SYNC_LOG
WHERE ERROR_MESSAGE IS NOT NULL
ORDER BY CREATE_TIME DESC;

-- 按操作类型统计
SELECT OPERATION, COUNT(*) as cnt
FROM NM_ALARM_SYNC_LOG
WHERE CREATE_TIME >= SYSDATE - 1
GROUP BY OPERATION;
```

#### 8.2.3 清理旧日志

```bash
# 通过 API 清理
curl -X POST "http://localhost:8080/api/v1/admin/cleanup/old-logs?days=30"

# 或直接 SQL
DELETE FROM NM_ALARM_SYNC_LOG WHERE CREATE_TIME < SYSDATE - 30;
COMMIT;
```

### 8.3 监控告警

#### 8.3.1 Prometheus 告警规则

```yaml
# prometheus/rules/zmc-exporter.yml
groups:
- name: zmc-alarm-exporter
  rules:
  # 同步服务停止
  - alert: ZMCSyncServiceDown
    expr: zmc_sync_service_up == 0
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "ZMC Sync Service is down"
      description: "The ZMC alarm sync service has been down for more than 5 minutes."

  # 同步错误率过高
  - alert: ZMCSyncErrorRateHigh
    expr: rate(zmc_errors_total[5m]) > 0.1
    for: 10m
    labels:
      severity: warning
    annotations:
      summary: "High error rate in ZMC sync"
      description: "Error rate is {{ $value }} errors/second."

  # 同步延迟过高
  - alert: ZMCSyncLatencyHigh
    expr: histogram_quantile(0.95, rate(zmc_sync_duration_seconds_bucket[5m])) > 30
    for: 15m
    labels:
      severity: warning
    annotations:
      summary: "High sync latency"
      description: "95th percentile sync latency is {{ $value }}s."

  # 长时间未同步
  - alert: ZMCSyncStale
    expr: time() - zmc_last_sync_timestamp_seconds > 300
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "No sync activity"
      description: "No successful sync in the last 5 minutes."
```

### 8.4 备份与恢复

#### 8.4.1 备份配置

```bash
# 导出配置
sqlplus zmc/smart@rb <<EOF
SET PAGESIZE 0 FEEDBACK OFF VERIFY OFF HEADING OFF ECHO OFF
SPOOL config_backup.sql
SELECT 'INSERT INTO NM_ALARM_SYNC_CONFIG VALUES (' ||
       CONFIG_ID || ',' ||
       '''' || CONFIG_KEY || ''',' ||
       '''' || CONFIG_VALUE || ''',' ||
       '''' || CONFIG_GROUP || ''',' ||
       '''' || DESCRIPTION || ''',' ||
       IS_ACTIVE || ',' ||
       'SYSDATE,SYSDATE);'
FROM NM_ALARM_SYNC_CONFIG;
SPOOL OFF
EXIT
EOF
```

#### 8.4.2 恢复配置

```bash
sqlplus zmc/smart@rb @config_backup.sql
```

---

## 9. 故障排查

### 9.1 常见问题

#### 9.1.1 数据库连接失败

**现象:** 健康检查显示 Oracle 状态为 unhealthy

**排查步骤:**

```bash
# 1. 检查网络连通性
telnet 10.101.1.42 1522

# 2. 检查连接参数
echo $ZMC_ORACLE_HOST
echo $ZMC_ORACLE_PORT
echo $ZMC_ORACLE_SERVICE_NAME

# 3. 测试连接
sqlplus zmc/smart@//10.101.1.42:1522/rb

# 4. 检查数据库监听器
lsnrctl status
```

**解决方案:**
- 确认防火墙规则允许访问
- 验证连接参数正确
- 检查数据库用户权限

#### 9.1.2 Alertmanager 推送失败

**现象:** 同步日志显示推送错误

**排查步骤:**

```bash
# 1. 检查 Alertmanager 状态
curl http://alertmanager:9093/-/healthy

# 2. 检查网络连通性
curl http://alertmanager:9093/api/v2/status

# 3. 查看 Alertmanager 日志
docker logs alertmanager

# 4. 手动测试推送
curl -X POST http://alertmanager:9093/api/v2/alerts \
  -H "Content-Type: application/json" \
  -d '[{"labels":{"alertname":"test","severity":"info"},"annotations":{"summary":"Test alert"}}]'
```

**解决方案:**
- 确认 Alertmanager 地址正确
- 检查网络连通性
- 验证 Alertmanager 配置

#### 9.1.3 告警未同步

**现象:** ZMC 产生告警但未推送到 Alertmanager

**排查步骤:**

```sql
-- 1. 检查原始告警
SELECT * FROM NM_ALARM_EVENT
WHERE CREATE_DATE >= SYSDATE - 1/24
ORDER BY CREATE_DATE DESC;

-- 2. 检查同步状态
SELECT * FROM NM_ALARM_SYNC_STATUS
WHERE EVENT_INST_ID = :event_id;

-- 3. 检查同步日志
SELECT * FROM NM_ALARM_SYNC_LOG
WHERE EVENT_INST_ID = :event_id
ORDER BY CREATE_TIME DESC;

-- 4. 检查级别过滤
SELECT ALARM_LEVEL FROM NM_ALARM_EVENT
WHERE EVENT_INST_ID = :event_id;
```

**解决方案:**
- 检查告警级别是否在允许范围内
- 查看同步日志中的错误信息
- 手动触发同步测试

#### 9.1.4 内存占用过高

**现象:** 容器内存持续增长

**排查步骤:**

```bash
# 1. 查看内存使用
docker stats zmc-alarm-exporter

# 2. 检查连接池
curl http://localhost:8080/api/v1/admin/database/status

# 3. 检查未关闭的连接
SELECT * FROM v$session WHERE username = 'ZMC';
```

**解决方案:**
- 调整连接池大小
- 检查是否有内存泄漏
- 增加容器内存限制

### 9.2 日志分析

#### 9.2.1 关键日志模式

```bash
# 同步成功
grep "Successfully pushed" /var/log/exporter.log

# 同步失败
grep "Push failed" /var/log/exporter.log

# 连接错误
grep "Connection error" /var/log/exporter.log

# 超时
grep "timeout" /var/log/exporter.log
```

#### 9.2.2 性能分析

```sql
-- 同步耗时分析
SELECT
    TRUNC(CREATE_TIME, 'HH24') as hour,
    AVG(DURATION_MS) as avg_duration,
    MAX(DURATION_MS) as max_duration,
    COUNT(*) as operations
FROM NM_ALARM_SYNC_LOG
WHERE CREATE_TIME >= SYSDATE - 1
GROUP BY TRUNC(CREATE_TIME, 'HH24')
ORDER BY hour;

-- 错误率分析
SELECT
    TRUNC(CREATE_TIME, 'HH24') as hour,
    SUM(CASE WHEN ERROR_MESSAGE IS NOT NULL THEN 1 ELSE 0 END) as errors,
    COUNT(*) as total,
    ROUND(SUM(CASE WHEN ERROR_MESSAGE IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*) * 100, 2) as error_rate
FROM NM_ALARM_SYNC_LOG
WHERE CREATE_TIME >= SYSDATE - 1
GROUP BY TRUNC(CREATE_TIME, 'HH24')
ORDER BY hour;
```

---

## 10. 附录

### 10.1 ZMC 告警状态说明

| 状态码 | 说明 | 触发条件 |
|--------|------|----------|
| U | 未确认 | 新产生的告警 |
| A | 自动恢复 | 系统检测到故障恢复 |
| M | 手工清除 | 运维人员手动清除/屏蔽 |
| C | 已确认 | 运维人员确认告警 |

### 10.2 Prometheus 告警格式

```json
{
  "labels": {
    "alertname": "CPU_Usage_High",
    "instance": "192.168.1.100",
    "severity": "critical",
    "event_id": "12345",
    "alarm_code": "1001",
    "source": "zmc"
  },
  "annotations": {
    "summary": "CPU 使用率过高",
    "description": "主机 192.168.1.100 CPU 使用率超过 90%",
    "runbook": "检查进程占用，必要时重启服务"
  },
  "startsAt": "2024-01-15T10:30:00Z",
  "endsAt": null,
  "generatorURL": null
}
```

### 10.3 OpsGenie 集成配置

在 Alertmanager 配置中添加 OpsGenie 接收器：

```yaml
receivers:
- name: 'opsgenie-receiver'
  opsgenie_configs:
  - api_key: 'your-opsgenie-api-key'
    api_url: 'https://api.opsgenie.com/'
    message: '{{ .GroupLabels.alertname }}: {{ .CommonAnnotations.summary }}'
    priority: '{{ if eq .GroupLabels.severity "critical" }}P1{{ else if eq .GroupLabels.severity "error" }}P2{{ else }}P3{{ end }}'
    tags: 'zmc,{{ .GroupLabels.severity }}'
```

### 10.4 项目文件清单

```
zmc-alarm-exporter/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI 应用入口
│   ├── config.py                  # 配置管理
│   ├── api/
│   │   ├── __init__.py
│   │   ├── health.py              # 健康检查 API
│   │   ├── metrics.py             # Prometheus 指标 API
│   │   ├── sync.py                # 同步管理 API
│   │   └── admin.py               # 管理 API
│   ├── models/
│   │   ├── __init__.py
│   │   ├── alarm.py               # ZMC 告警模型
│   │   └── prometheus.py          # Prometheus 告警模型
│   └── services/
│       ├── __init__.py
│       ├── oracle_client.py       # Oracle 数据库客户端
│       ├── alarm_extractor.py     # 告警抽取服务
│       ├── alarm_transformer.py   # 告警转换服务
│       ├── alertmanager_client.py # Alertmanager 客户端
│       └── sync_service.py        # 同步服务
├── sql/
│   ├── init_sync_tables.sql       # 数据库初始化脚本
│   └── queries.sql                # SQL 查询语句
├── alertmanager/
│   └── alertmanager.yml           # Alertmanager 配置
├── prometheus/
│   └── prometheus.yml             # Prometheus 配置
├── docs/
│   └── DEPLOYMENT_GUIDE.md        # 部署指南（本文档）
├── Dockerfile                     # Docker 构建文件
├── docker-compose.yml             # Docker Compose 配置
├── requirements.txt               # Python 依赖
├── .env.example                   # 环境变量模板
├── .gitignore                     # Git 忽略规则
└── README.md                      # 项目说明
```

### 10.5 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| 1.0.0 | 2024-01-15 | 初始版本 |

---

*文档版本: 1.0.0*
*最后更新: 2024-01-15*
