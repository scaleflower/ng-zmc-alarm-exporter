# ZMC Alarm Exporter

将 ZMC (Z-Smart Management Center) 告警同步到 Prometheus Alertmanager，实现与 OpsGenie 的集成。

## 功能特性

- **告警同步**: 从 Oracle 数据库实时抽取 ZMC 告警并推送到 Alertmanager
- **状态跟踪**: 跟踪告警生命周期（产生、恢复、屏蔽）
- **心跳保活**: 定期重新推送活跃告警，防止 Alertmanager 自动解除
- **静默管理**: 支持通过 Alertmanager Silence API 处理屏蔽的告警
- **级别过滤**: 可配置只同步特定级别的告警
- **完整日志**: 记录所有同步操作供审计和排查
- **Prometheus 指标**: 导出服务运行指标
- **REST API**: 提供管理和监控接口

## 架构

```
┌─────────────────┐     ┌─────────────────────┐     ┌─────────────────┐
│   Oracle DB     │────>│  ZMC Alarm Exporter │────>│  Alertmanager   │
│ (NM_ALARM_EVENT)│     │                     │     │                 │
└─────────────────┘     └─────────────────────┘     └────────┬────────┘
                                                             │
                                                             v
                                                    ┌─────────────────┐
                                                    │    OpsGenie     │
                                                    └─────────────────┘
```

## 快速开始

### 1. 环境要求

- Python 3.10+
- Oracle Database (ZMC 数据库)
- Prometheus Alertmanager
- Docker (可选)

### 2. 安装

```bash
# 克隆代码
cd ng_monitor/zmc-alarm-exporter

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 3. 配置

```bash
# 复制配置模板
cp .env.example .env

# 编辑配置
vim .env
```

主要配置项：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `ZMC_ORACLE_HOST` | Oracle 数据库地址 | localhost |
| `ZMC_ORACLE_PORT` | Oracle 端口 | 1521 |
| `ZMC_ORACLE_SERVICE_NAME` | Oracle 服务名 | ORCL |
| `ZMC_ORACLE_USERNAME` | 数据库用户名 | zmc |
| `ZMC_ORACLE_PASSWORD` | 数据库密码 | - |
| `ALERTMANAGER_URL` | Alertmanager 地址 | http://localhost:9093 |
| `SYNC_SCAN_INTERVAL` | 扫描间隔（秒） | 60 |
| `SYNC_ALARM_LEVELS` | 同步的告警级别 | 1,2,3,4 |

### 4. 初始化数据库

在 ZMC Oracle 数据库中执行初始化脚本：

```bash
# 使用 SQLPlus 执行
sqlplus zmc/smart@rb @sql/init_sync_tables.sql
```

### 5. 运行

```bash
# 开发模式
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

# 生产模式
uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 1
```

### 6. Docker 部署

```bash
# 构建镜像
docker build -t zmc-alarm-exporter .

# 使用 docker-compose 启动
docker-compose up -d
```

## API 接口

### 健康检查

```bash
# 完整健康检查
GET /health

# 存活探针 (Kubernetes)
GET /health/live

# 就绪探针 (Kubernetes)
GET /health/ready
```

### 同步管理

```bash
# 获取同步状态
GET /api/v1/sync/status

# 手动触发同步
POST /api/v1/sync/trigger

# 获取已同步告警
GET /api/v1/sync/alarms?status=FIRING&limit=100

# 获取同步日志
GET /api/v1/sync/logs?operation=PUSH_FIRING&limit=100

# 获取统计信息
GET /api/v1/sync/statistics
```

### 管理接口

```bash
# 获取配置
GET /api/v1/admin/config

# 更新配置
PUT /api/v1/admin/config/{key}

# Alertmanager 状态
GET /api/v1/admin/alertmanager/status

# 服务控制
POST /api/v1/admin/service/control
# body: {"action": "start|stop|restart"}
```

### Prometheus 指标

```bash
# Prometheus 格式
GET /metrics

# JSON 格式
GET /metrics/json
```

## 告警级别映射

| ZMC 级别 | 说明 | Prometheus Severity |
|----------|------|---------------------|
| 1 | 严重 | critical |
| 2 | 重要 | error |
| 3 | 次要 | warning |
| 4 | 警告 | info |

## 告警状态映射

| ZMC 状态 | 说明 | 同步状态 |
|----------|------|----------|
| U | 未确认 | FIRING |
| A | 自动恢复 | RESOLVED |
| M | 手工清除 | SILENCED |
| C | 已确认 | RESOLVED |

## 目录结构

```
zmc-alarm-exporter/
├── app/
│   ├── api/                 # API 路由
│   │   ├── health.py        # 健康检查
│   │   ├── metrics.py       # Prometheus 指标
│   │   ├── sync.py          # 同步管理
│   │   └── admin.py         # 管理接口
│   ├── models/              # 数据模型
│   │   ├── alarm.py         # ZMC 告警模型
│   │   └── prometheus.py    # Prometheus 告警模型
│   ├── services/            # 业务服务
│   │   ├── oracle_client.py # Oracle 客户端
│   │   ├── alarm_extractor.py    # 告警抽取
│   │   ├── alarm_transformer.py  # 告警转换
│   │   ├── alertmanager_client.py # Alertmanager 客户端
│   │   └── sync_service.py  # 同步服务
│   ├── config.py            # 配置管理
│   └── main.py              # 应用入口
├── sql/
│   ├── init_sync_tables.sql # 数据库初始化
│   └── queries.sql          # SQL 查询
├── alertmanager/            # Alertmanager 配置
├── prometheus/              # Prometheus 配置
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## 开发

### 运行测试

```bash
pytest tests/ -v
```

### 代码检查

```bash
# 类型检查
mypy app/

# 代码风格
flake8 app/
black app/
```

## 故障排查

### 常见问题

1. **数据库连接失败**
   - 检查 Oracle 连接参数
   - 确认防火墙规则
   - 验证用户权限

2. **Alertmanager 推送失败**
   - 检查 Alertmanager 地址
   - 查看 Alertmanager 日志
   - 验证网络连通性

3. **告警未同步**
   - 检查告警级别过滤配置
   - 查看同步日志表
   - 确认数据库查询权限

### 日志查看

```bash
# Docker 日志
docker logs -f zmc-alarm-exporter

# 数据库同步日志
SELECT * FROM NM_ALARM_SYNC_LOG
ORDER BY CREATE_TIME DESC
FETCH FIRST 100 ROWS ONLY;
```

## License

MIT License
