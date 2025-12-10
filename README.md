# ZMC Alarm Exporter

将 ZMC (Z-Smart Management Center) 告警同步到 Prometheus Alertmanager，实现与 OpsGenie 等告警平台的集成。

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
┌─────────────────┐     ┌─────────────────────┐     ┌─────────────────────────────┐
│   Oracle DB     │────>│  ZMC Alarm Exporter │────>│  Prometheus 主机            │
│ (NM_ALARM_EVENT)│     │  (本服务)           │     │  - Alertmanager (:9093)     │
└─────────────────┘     └─────────────────────┘     │  - Prometheus (:9090)       │
                                 │                  └──────────────┬──────────────┘
                                 │ /metrics                        │
                                 v                                 v
                        ┌─────────────────┐              ┌─────────────────┐
                        │   Prometheus    │              │  OpsGenie/      │
                        │   (抓取指标)    │              │  Webhook/Email  │
                        └─────────────────┘              └─────────────────┘
```

**说明**: 本服务只负责将 ZMC 告警推送到外部 Alertmanager，Alertmanager 和 Prometheus 需要由运维团队独立部署。

## 快速开始

### 1. 环境要求

- Python 3.10+
- Oracle Database (ZMC 数据库)
- **外部 Prometheus Alertmanager**（需预先部署）

### 2. 一键安装

```bash
# 克隆代码
git clone https://github.com/scaleflower/ng-zmc-alarm-exporter.git
cd ng-zmc-alarm-exporter

# 运行安装脚本
./install.sh
```

安装脚本会自动：
- 检查并安装 Python 3.10+
- 创建虚拟环境并安装依赖
- 交互式配置数据库和 Alertmanager
- 初始化数据库表结构
- 启动服务

### 3. 手动安装

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置
cp .env.example .env
vim .env

# 初始化数据库
sqlplus zmc/password@host:port/service @sql/init_sync_tables.sql

# 启动
./bin/start.sh start
```

### 4. 配置说明

主要配置项（在 `.env` 中修改）：

| 配置项 | 说明 | 示例 |
|--------|------|------|
| `ZMC_ORACLE_HOST` | Oracle 数据库地址 | 10.101.1.42 |
| `ZMC_ORACLE_PORT` | Oracle 端口 | 1522 |
| `ZMC_ORACLE_SERVICE_NAME` | Oracle 服务名 | rb |
| `ZMC_ORACLE_USERNAME` | 数据库用户名 | zmc |
| `ZMC_ORACLE_PASSWORD` | 数据库密码 | smart |
| `ALERTMANAGER_URL` | **外部 Alertmanager 地址** | http://192.168.1.100:9093 |
| `SYNC_SCAN_INTERVAL` | 扫描间隔（秒） | 60 |
| `SYNC_ALARM_LEVELS` | 同步的告警级别 | 1,2,3,4 |

### 5. Prometheus 集成

在 Prometheus 配置文件中添加抓取任务：

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'zmc-alarm-exporter'
    scrape_interval: 30s
    static_configs:
      - targets: ['exporter-host:8080']
    metrics_path: '/metrics'
```

### 6. Docker 部署

```bash
# 编辑配置
cp .env.example .env
vim .env  # 配置 ALERTMANAGER_URL 指向外部 Alertmanager

# 构建并启动
docker-compose up -d

# 查看日志
docker-compose logs -f
```

## 服务管理

```bash
# 启动
./bin/start.sh start

# 停止
./bin/start.sh stop

# 重启
./bin/start.sh restart

# 状态
./bin/start.sh status

# 日志
./bin/start.sh logs-f
```

## API 接口

### 健康检查

```bash
GET /health           # 完整健康检查
GET /health/live      # 存活探针
GET /health/ready     # 就绪探针
```

### 同步管理

```bash
GET  /api/v1/sync/status       # 获取同步状态
POST /api/v1/sync/trigger      # 手动触发同步
GET  /api/v1/sync/alarms       # 获取已同步告警
GET  /api/v1/sync/statistics   # 获取统计信息
```

### Prometheus 指标

```bash
GET /metrics          # Prometheus 格式
```

### API 文档

启动服务后访问: `http://localhost:8080/docs`

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
├── app/                    # 应用代码
│   ├── api/                # API 路由
│   ├── models/             # 数据模型
│   ├── services/           # 业务服务
│   ├── config.py           # 配置管理
│   └── main.py             # 应用入口
├── bin/
│   └── start.sh            # 启动脚本
├── sql/
│   └── init_sync_tables.sql # 数据库初始化
├── docs/
│   └── DEPLOYMENT_GUIDE.md # 部署指南
├── install.sh              # 一键安装脚本
├── docker-compose.yml      # Docker 编排
├── Dockerfile
├── requirements.txt
└── .env.example            # 配置模板
```

## 故障排查

### 常见问题

1. **DPY-3015 密码验证器错误**
   - 原因: Oracle 数据库使用旧版密码加密
   - 解决: 安装 Oracle Instant Client 或使用 sqlplus 初始化数据库

2. **Alertmanager 推送失败**
   - 检查 `ALERTMANAGER_URL` 配置
   - 确认网络连通性: `curl http://alertmanager-host:9093/-/healthy`
   - 检查防火墙规则

3. **告警未同步**
   - 检查告警级别过滤配置 `SYNC_ALARM_LEVELS`
   - 查看同步状态: `curl http://localhost:8080/api/v1/sync/status`
   - 手动触发同步: `curl -X POST http://localhost:8080/api/v1/sync/trigger`

### 日志查看

```bash
# 应用日志
./bin/start.sh logs-f

# Docker 日志
docker-compose logs -f

# 数据库同步日志
SELECT * FROM NM_ALARM_SYNC_LOG ORDER BY CREATE_TIME DESC FETCH FIRST 100 ROWS ONLY;
```

## License

MIT License
