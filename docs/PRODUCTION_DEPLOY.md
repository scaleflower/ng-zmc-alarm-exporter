# ZMC Alarm Exporter 生产环境部署文档

## 1. 概述

ZMC Alarm Exporter 是一个将 ZMC 告警同步到 Prometheus Alertmanager 的服务。本文档描述如何在**离线环境**下使用 Docker 部署该服务。

### 1.1 部署架构

```
┌─────────────────────────────────────────────────────────────┐
│                    生产服务器 (10.25.179.28)                 │
│                                                             │
│  ┌─────────────────┐    ┌─────────────────────────────────┐│
│  │  Docker 容器    │    │         宿主机服务               ││
│  │                 │    │                                 ││
│  │ zmc-alarm-      │───►│  Oracle DB    (1521)           ││
│  │ exporter:8080   │    │  Alertmanager (9093)           ││
│  │                 │    │                                 ││
│  └─────────────────┘    └─────────────────────────────────┘│
│           │                                                 │
│           ▼                                                 │
│  /zmc/zmc-alarm-exporter/.env (配置文件)                    │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 服务信息

| 项目 | 值 |
|------|-----|
| 服务名称 | zmc-alarm-exporter |
| 服务端口 | 8080 |
| 部署路径 | /zmc/zmc-alarm-exporter |
| Docker 镜像 | zmc-alarm-exporter:latest |

---

## 2. 离线部署步骤

### 2.1 准备工作 (有网络环境)

在有网络的开发机器上准备以下文件：

```bash
# 1. 构建 amd64 架构镜像 (Mac/ARM 需指定平台)
docker buildx build --platform linux/amd64 -t zmc-alarm-exporter:latest --load .

# 2. 导出镜像
docker save zmc-alarm-exporter:latest | gzip > zmc-alarm-exporter.tar.gz

# 3. 下载 Docker 离线安装包 (适用于 RHEL/Oracle Linux 8)
curl -L -o docker-27.5.0.tgz https://download.docker.com/linux/static/stable/x86_64/docker-27.5.0.tgz
```

### 2.2 传输文件到生产环境

将以下文件传输到生产服务器：

```
zmc-alarm-exporter.tar.gz   # Docker 镜像 (~103MB)
docker-27.5.0.tgz           # Docker 安装包 (~73MB)
.env                        # 配置文件
```

### 2.3 安装 Docker (如未安装)

```bash
# 解压并安装 Docker
tar xzf docker-27.5.0.tgz
cp docker/* /usr/bin/

# 创建 systemd 服务文件
cat > /etc/systemd/system/docker.service << 'EOF'
[Unit]
Description=Docker Application Container Engine
After=network-online.target

[Service]
Type=notify
ExecStart=/usr/bin/dockerd
Restart=always
LimitNOFILE=infinity

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/containerd.service << 'EOF'
[Unit]
Description=containerd container runtime
After=network.target

[Service]
ExecStart=/usr/bin/containerd
Type=notify
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# 启动 Docker
systemctl daemon-reload
systemctl enable containerd docker
systemctl start containerd docker

# 验证安装
docker --version
```

### 2.4 部署服务

```bash
# 1. 创建部署目录
mkdir -p /zmc/zmc-alarm-exporter

# 2. 复制配置文件
cp .env /zmc/zmc-alarm-exporter/.env

# 3. 加载 Docker 镜像
docker load < zmc-alarm-exporter.tar.gz

# 4. 启动服务
docker run -d \
    --name zmc-alarm-exporter \
    --restart unless-stopped \
    -p 8080:8080 \
    --env-file /zmc/zmc-alarm-exporter/.env \
    zmc-alarm-exporter:latest

# 5. 验证服务
docker logs zmc-alarm-exporter
curl http://localhost:8080/health/live
```

---

## 3. 配置说明

配置文件路径: `/zmc/zmc-alarm-exporter/.env`

### 3.1 Oracle 数据库配置

```bash
# ZMC Oracle 数据库连接信息
ZMC_ORACLE_HOST=10.25.179.28        # 数据库主机 (使用宿主机真实IP，勿用127.0.0.1)
ZMC_ORACLE_PORT=1521                # 数据库端口
ZMC_ORACLE_SERVICE_NAME=zmc         # 服务名
ZMC_ORACLE_USERNAME=zmc             # 用户名
ZMC_ORACLE_PASSWORD=Jsmart.868      # 密码
ZMC_ORACLE_POOL_MIN=2               # 连接池最小连接数
ZMC_ORACLE_POOL_MAX=10              # 连接池最大连接数
ZMC_ORACLE_TIMEOUT=30               # 连接超时(秒)
```

### 3.2 Alertmanager 配置

```bash
ALERTMANAGER_URL=http://10.25.179.28:9093   # Alertmanager 地址 (使用宿主机真实IP)
ALERTMANAGER_API_VERSION=v2
ALERTMANAGER_TIMEOUT=30
ALERTMANAGER_RETRY_COUNT=3
```

### 3.3 同步配置

```bash
SYNC_INTERVAL=60                    # 同步间隔(秒)
SYNC_BATCH_SIZE=100                 # 每批处理告警数
SYNC_HISTORY_HOURS=24               # 历史告警查询范围(小时)
```

### 3.4 重要说明

> ⚠️ **Docker 网络注意事项**
>
> Docker 容器内的 `127.0.0.1` 指向容器自身，而非宿主机。
> 连接宿主机服务时，必须使用宿主机的**真实 IP 地址**。

---

## 4. 运维命令

### 4.1 服务管理

```bash
# 查看服务状态
docker ps -f name=zmc-alarm-exporter

# 查看实时日志
docker logs -f zmc-alarm-exporter

# 查看最近 100 行日志
docker logs --tail 100 zmc-alarm-exporter

# 重启服务 (配置不变)
docker restart zmc-alarm-exporter

# 停止服务
docker stop zmc-alarm-exporter

# 启动已停止的服务
docker start zmc-alarm-exporter
```

### 4.2 修改配置后重启

```bash
# 1. 编辑配置文件
vi /zmc/zmc-alarm-exporter/.env

# 2. 删除旧容器并重新创建
docker stop zmc-alarm-exporter
docker rm zmc-alarm-exporter

docker run -d \
    --name zmc-alarm-exporter \
    --restart unless-stopped \
    -p 8080:8080 \
    --env-file /zmc/zmc-alarm-exporter/.env \
    zmc-alarm-exporter:latest
```

### 4.3 健康检查

```bash
# 存活检查
curl http://localhost:8080/health/live

# 就绪检查
curl http://localhost:8080/health/ready

# 查看 Prometheus 指标
curl http://localhost:8080/metrics
```

### 4.4 镜像更新

```bash
# 1. 传输新镜像到服务器
scp zmc-alarm-exporter.tar.gz root@server:/root/

# 2. 在服务器上执行
docker stop zmc-alarm-exporter
docker rm zmc-alarm-exporter
docker rmi zmc-alarm-exporter:latest

docker load < zmc-alarm-exporter.tar.gz

docker run -d \
    --name zmc-alarm-exporter \
    --restart unless-stopped \
    -p 8080:8080 \
    --env-file /zmc/zmc-alarm-exporter/.env \
    zmc-alarm-exporter:latest
```

---

## 5. 故障排查

### 5.1 数据库连接失败

**错误信息**: `DPY-6005: cannot connect to database... timed out`

**排查步骤**:

```bash
# 1. 检查数据库端口连通性
nc -zv 10.25.179.28 1521 -w 5

# 2. 检查配置文件中的数据库地址
grep ZMC_ORACLE /zmc/zmc-alarm-exporter/.env

# 3. 确认使用的是宿主机真实 IP，而非 127.0.0.1
```

### 5.2 Alertmanager 推送失败

**错误信息**: `Request timeout`

**排查步骤**:

```bash
# 1. 检查 Alertmanager 端口连通性
nc -zv 10.25.179.28 9093 -w 5

# 2. 检查 Alertmanager 是否运行
curl http://10.25.179.28:9093/api/v2/status

# 3. 检查配置文件中的地址
grep ALERTMANAGER_URL /zmc/zmc-alarm-exporter/.env
```

### 5.3 容器无法启动

```bash
# 查看容器日志
docker logs zmc-alarm-exporter

# 查看容器详细信息
docker inspect zmc-alarm-exporter

# 检查端口占用
ss -tlnp | grep 8080
```

### 5.4 镜像架构不匹配

**错误信息**: `exec format error`

**原因**: 镜像架构 (arm64) 与服务器架构 (amd64) 不匹配

**解决方案**: 在开发机上使用 `--platform linux/amd64` 重新构建镜像

```bash
docker buildx build --platform linux/amd64 -t zmc-alarm-exporter:latest --load .
```

---

## 6. 日志说明

### 6.1 正常启动日志

```json
{"level": "INFO", "message": "Starting ZMC Alarm Exporter v1.0.0"}
{"level": "INFO", "message": "Initializing Oracle connection pool: 10.25.179.28:1521/zmc"}
{"level": "INFO", "message": "Oracle connection pool initialized successfully"}
{"level": "INFO", "message": "Extracted 74 new alarms"}
{"level": "INFO", "message": "Successfully pushed 74 alerts (duration: 33ms)"}
{"level": "INFO", "message": "Uvicorn running on http://0.0.0.0:8080"}
```

### 6.2 日志级别

可在 `.env` 中配置:

```bash
LOG_LEVEL=INFO    # DEBUG, INFO, WARNING, ERROR
LOG_FORMAT=json   # json 或 text
```

---

## 7. 附录

### 7.1 完整 .env 配置示例

```bash
# ========== 应用配置 ==========
APP_NAME=ZMC Alarm Exporter
APP_VERSION=1.0.0
APP_ENV=production

# ========== Oracle 数据库配置 ==========
ZMC_ORACLE_HOST=10.25.179.28
ZMC_ORACLE_PORT=1521
ZMC_ORACLE_SERVICE_NAME=zmc
ZMC_ORACLE_USERNAME=zmc
ZMC_ORACLE_PASSWORD=Jsmart.868
ZMC_ORACLE_POOL_MIN=2
ZMC_ORACLE_POOL_MAX=10
ZMC_ORACLE_TIMEOUT=30

# ========== Alertmanager 配置 ==========
ALERTMANAGER_URL=http://10.25.179.28:9093
ALERTMANAGER_API_VERSION=v2
ALERTMANAGER_AUTH_ENABLED=false
ALERTMANAGER_TIMEOUT=30
ALERTMANAGER_RETRY_COUNT=3
ALERTMANAGER_RETRY_INTERVAL=1000

# ========== 同步配置 ==========
SYNC_INTERVAL=60
SYNC_BATCH_SIZE=100
SYNC_HISTORY_HOURS=24
SYNC_ENABLED=true

# ========== 日志配置 ==========
LOG_LEVEL=INFO
LOG_FORMAT=json
```

### 7.2 服务器信息

| 项目 | 值 |
|------|-----|
| 操作系统 | Oracle Linux 8.10 |
| Docker 版本 | 27.5.0 |
| 部署日期 | 2025-12-16 |
| 部署路径 | /zmc/zmc-alarm-exporter |

---

*文档更新日期: 2025-12-16*
