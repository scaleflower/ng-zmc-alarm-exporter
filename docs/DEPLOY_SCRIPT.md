# ZMC Alarm Exporter 一键部署脚本使用指南

## 1. 概述

`deploy.sh` 是一个自动化部署脚本，用于将 ZMC Alarm Exporter 应用快速部署到生产环境。脚本自动完成以下工作：

1. 构建 Docker 镜像（linux/amd64 架构）
2. 导出并压缩镜像
3. 传输镜像到生产服务器
4. 在生产服务器上完成部署

**适用场景**：
- 日常代码更新后的快速部署
- 紧急 Bug 修复后的快速发布
- 配置变更后的重新部署

---

## 2. 前置条件

### 2.1 本地环境要求

| 组件 | 要求 | 检查命令 |
|------|------|----------|
| Docker | 已安装并运行 | `docker --version` |
| Docker Buildx | 支持跨平台构建 | `docker buildx version` |
| sshpass | SSH 密码认证工具 | `sshpass -V` |

### 2.2 安装缺失依赖

```bash
# macOS 安装 sshpass
brew install hudochenkov/sshpass/sshpass

# 或者
brew install esolitos/ipa/sshpass
```

### 2.3 生产环境要求

- Docker 已安装并运行
- 部署目录已创建：`/zmc/zmc-alarm-exporter`
- 配置文件已就位：`/zmc/zmc-alarm-exporter/.env`

---

## 3. 使用方法

### 3.1 基本用法

```bash
# 进入项目目录
cd /path/to/zmc-alarm-exporter

# 完整部署（构建 + 部署）
./deploy.sh

# 查看帮助
./deploy.sh -h
```

### 3.2 命令选项

| 选项 | 长选项 | 说明 |
|------|--------|------|
| `-b` | `--build-only` | 仅构建镜像，不部署到生产环境 |
| `-d` | `--deploy-only` | 仅部署，使用已构建的镜像文件 |
| `-h` | `--help` | 显示帮助信息 |

### 3.3 使用示例

```bash
# 示例 1：完整流程（最常用）
./deploy.sh

# 示例 2：只构建镜像，稍后部署
./deploy.sh -b

# 示例 3：使用已构建的镜像进行部署
./deploy.sh -d

# 示例 4：分步执行（适合网络不稳定的情况）
./deploy.sh -b          # 先构建
./deploy.sh -d          # 再部署
```

---

## 4. 配置说明

### 4.1 脚本配置

脚本顶部的配置区域可根据实际情况修改：

```bash
# ==================== 配置区域 ====================
# 生产服务器信息
PROD_HOST="192.168.123.239"      # 生产服务器 IP
PROD_PORT="51017"                 # SSH 端口
PROD_USER="root"                  # SSH 用户名
PROD_PASS='-|edhG/e0='           # SSH 密码

# 镜像信息
IMAGE_NAME="zmc-alarm-exporter"   # 镜像名称
IMAGE_TAG="latest"                # 镜像标签

# 部署路径
DEPLOY_PATH="/zmc/zmc-alarm-exporter"  # 配置文件所在目录

# 临时文件路径
TMP_DIR="/tmp/zmc-deploy"         # 本地临时目录
```

### 4.2 修改配置示例

如果需要部署到不同的服务器，修改以下配置：

```bash
# 修改为新服务器信息
PROD_HOST="192.168.1.100"
PROD_PORT="22"
PROD_USER="deploy"
PROD_PASS='your_password'
```

---

## 5. 工作流程

### 5.1 完整流程图

```
┌─────────────────────────────────────────────────────────────────┐
│                         本地开发机                               │
│                                                                 │
│  [1] 检查依赖 ──► [2] 构建镜像 ──► [3] 导出镜像 ──► [4] 传输镜像  │
│      docker         buildx          gzip             scp        │
│      sshpass        amd64           ~103MB                      │
└─────────────────────────────────────────────────────────────────┘
                                                        │
                                                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                        生产服务器                                │
│                                                                 │
│  [5] 停止旧容器 ──► [6] 删除旧镜像 ──► [7] 加载新镜像 ──► [8] 启动 │
│      docker stop      docker rmi       docker load    docker run│
│      docker rm                                                  │
│                                                                 │
│  [9] 验证服务 ──► [10] 清理临时文件                               │
│      docker ps        rm tar.gz                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 各步骤详解

| 步骤 | 操作 | 说明 |
|------|------|------|
| 1 | 检查依赖 | 确认 docker 和 sshpass 已安装 |
| 2 | 构建镜像 | 使用 buildx 构建 linux/amd64 架构镜像 |
| 3 | 导出镜像 | `docker save` + `gzip` 压缩 |
| 4 | 传输镜像 | SCP 传输到生产服务器 /root/ |
| 5 | 停止旧容器 | `docker stop` + `docker rm` |
| 6 | 删除旧镜像 | `docker rmi` 释放磁盘空间 |
| 7 | 加载新镜像 | `docker load` 从 tar.gz 加载 |
| 8 | 启动容器 | `docker run` 使用 .env 配置启动 |
| 9 | 验证服务 | 显示容器状态和启动日志 |
| 10 | 清理文件 | 删除服务器上的临时镜像文件 |

### 5.3 执行时间参考

| 步骤 | 耗时 |
|------|------|
| 构建镜像（有缓存） | ~5 秒 |
| 构建镜像（无缓存） | ~60 秒 |
| 导出镜像 | ~10 秒 |
| 传输镜像 (~103MB) | ~60-120 秒 |
| 远程部署 | ~15 秒 |
| **总计** | **2-3 分钟** |

---

## 6. 输出说明

### 6.1 正常输出示例

```
========================================
  ZMC Alarm Exporter 部署脚本
========================================

[INFO] 检查依赖...
[SUCCESS] 依赖检查通过
[INFO] 开始构建 Docker 镜像 (linux/amd64)...
[SUCCESS] 镜像构建完成
REPOSITORY           TAG       IMAGE ID       CREATED         SIZE
zmc-alarm-exporter   latest    f820c1de3509   2 minutes ago   109MB
[INFO] 导出镜像...
[SUCCESS] 镜像导出完成: /tmp/zmc-deploy/zmc-alarm-exporter.tar.gz (103M)
[INFO] 传输镜像到生产服务器...
[SUCCESS] 镜像传输完成
[INFO] 在生产服务器上部署...
==> 停止旧容器...
==> 删除旧镜像...
==> 加载新镜像...
Loaded image: zmc-alarm-exporter:latest
==> 启动新容器...
==> 检查容器状态...
NAMES                STATUS         PORTS
zmc-alarm-exporter   Up 5 seconds   0.0.0.0:8080->8080/tcp
==> 查看启动日志...
{"level": "INFO", "message": "Starting ZMC Alarm Exporter v1.0.0"}
...
[SUCCESS] 部署完成

========================================
[SUCCESS] 全部完成! 耗时: 149秒
========================================
```

### 6.2 输出颜色说明

| 颜色 | 前缀 | 含义 |
|------|------|------|
| 蓝色 | `[INFO]` | 正在执行的操作 |
| 绿色 | `[SUCCESS]` | 操作成功完成 |
| 黄色 | `[WARN]` | 警告信息 |
| 红色 | `[ERROR]` | 错误信息 |

---

## 7. 故障排查

### 7.1 常见错误及解决方案

#### 错误 1：Docker 未安装

```
[ERROR] Docker 未安装
```

**解决方案**：安装 Docker Desktop 或 Docker Engine

#### 错误 2：sshpass 未安装

```
[ERROR] sshpass 未安装，请运行: brew install sshpass
```

**解决方案**：
```bash
# macOS
brew install hudochenkov/sshpass/sshpass

# Ubuntu/Debian
apt-get install sshpass

# CentOS/RHEL
yum install sshpass
```

#### 错误 3：SSH 连接失败

```
ssh: connect to host 192.168.123.239 port 51017: Connection refused
```

**解决方案**：
1. 检查服务器 IP 和端口是否正确
2. 检查服务器 SSH 服务是否运行
3. 检查防火墙设置

#### 错误 4：镜像文件不存在

```
[ERROR] 镜像文件不存在: /tmp/zmc-deploy/zmc-alarm-exporter.tar.gz
[ERROR] 请先运行 ./deploy.sh -b 构建镜像
```

**解决方案**：先执行 `./deploy.sh -b` 构建镜像

#### 错误 5：磁盘空间不足

```
no space left on device
```

**解决方案**：
```bash
# 本地清理
docker system prune -a

# 服务器清理
ssh -p 51017 root@192.168.123.239 'docker system prune -a'
```

### 7.2 手动部署步骤

如果脚本执行失败，可以手动执行各步骤：

```bash
# 1. 本地构建
docker buildx build --platform linux/amd64 -t zmc-alarm-exporter:latest --load .

# 2. 本地导出
docker save zmc-alarm-exporter:latest | gzip > /tmp/zmc-alarm-exporter.tar.gz

# 3. 传输到服务器
scp -P 51017 /tmp/zmc-alarm-exporter.tar.gz root@192.168.123.239:/root/

# 4. 登录服务器
ssh -p 51017 root@192.168.123.239

# 5. 在服务器上执行
docker stop zmc-alarm-exporter
docker rm zmc-alarm-exporter
docker rmi zmc-alarm-exporter:latest
docker load < /root/zmc-alarm-exporter.tar.gz
docker run -d --name zmc-alarm-exporter --restart unless-stopped \
    -p 8080:8080 --env-file /zmc/zmc-alarm-exporter/.env \
    zmc-alarm-exporter:latest
```

---

## 8. 最佳实践

### 8.1 部署前检查清单

- [ ] 代码已提交到 Git
- [ ] 本地测试通过
- [ ] 确认生产环境 .env 配置正确
- [ ] 确认生产服务器网络可达

### 8.2 部署后验证

```bash
# 检查服务状态
ssh -p 51017 root@192.168.123.239 'docker ps -f name=zmc-alarm-exporter'

# 查看实时日志
ssh -p 51017 root@192.168.123.239 'docker logs -f zmc-alarm-exporter'

# 健康检查
ssh -p 51017 root@192.168.123.239 'curl -s http://localhost:8080/health/live'
```

### 8.3 回滚方案

如果新版本有问题，可以使用备份镜像回滚：

```bash
# 1. 在部署前先备份当前镜像（可选）
ssh -p 51017 root@192.168.123.239 \
    'docker save zmc-alarm-exporter:latest | gzip > /zmc/backup/zmc-alarm-exporter-backup.tar.gz'

# 2. 回滚时加载备份镜像
ssh -p 51017 root@192.168.123.239 << 'EOF'
docker stop zmc-alarm-exporter
docker rm zmc-alarm-exporter
docker rmi zmc-alarm-exporter:latest
docker load < /zmc/backup/zmc-alarm-exporter-backup.tar.gz
docker run -d --name zmc-alarm-exporter --restart unless-stopped \
    -p 8080:8080 --env-file /zmc/zmc-alarm-exporter/.env \
    zmc-alarm-exporter:latest
EOF
```

---

## 9. 安全注意事项

### 9.1 密码安全

脚本中包含明文密码，请注意：

1. **不要**将脚本上传到公开仓库
2. 考虑使用 SSH 密钥认证替代密码
3. 可以使用环境变量传递密码：

```bash
# 使用环境变量
export PROD_PASS='your_password'

# 修改脚本读取环境变量
PROD_PASS="${PROD_PASS:-default_password}"
```

### 9.2 使用 SSH 密钥认证（推荐）

```bash
# 1. 生成密钥（如果没有）
ssh-keygen -t ed25519

# 2. 复制公钥到服务器
ssh-copy-id -p 51017 root@192.168.123.239

# 3. 修改脚本，移除 sshpass
# 将 sshpass -p "${PROD_PASS}" ssh ... 改为 ssh ...
```

---

## 10. 附录

### 10.1 相关文件

| 文件 | 说明 |
|------|------|
| `deploy.sh` | 一键部署脚本 |
| `Dockerfile` | Docker 镜像构建文件 |
| `.env` | 应用配置文件（不含在仓库中） |
| `docs/PRODUCTION_DEPLOY.md` | 生产环境部署文档 |

### 10.2 相关命令速查

```bash
# 查看日志
ssh -p 51017 root@192.168.123.239 'docker logs -f zmc-alarm-exporter'

# 重启服务
ssh -p 51017 root@192.168.123.239 'docker restart zmc-alarm-exporter'

# 进入容器
ssh -p 51017 root@192.168.123.239 'docker exec -it zmc-alarm-exporter /bin/bash'

# 查看资源使用
ssh -p 51017 root@192.168.123.239 'docker stats zmc-alarm-exporter --no-stream'
```

---

*文档更新日期: 2025-12-16*
