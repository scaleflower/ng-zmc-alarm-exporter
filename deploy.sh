#!/bin/bash
#
# ZMC Alarm Exporter 一键部署脚本
#
# 用法: ./deploy.sh [选项]
#
# 选项:
#   -b, --build-only    仅构建镜像，不部署
#   -d, --deploy-only   仅部署（使用已有镜像）
#   -h, --help          显示帮助信息
#

set -e

# ==================== 配置区域 ====================
# 生产服务器信息
PROD_HOST="192.168.123.239"
PROD_PORT="51017"
PROD_USER="root"
PROD_PASS='-|edhG/e0='

# 镜像信息
IMAGE_NAME="zmc-alarm-exporter"
IMAGE_TAG="latest"

# 部署路径
DEPLOY_PATH="/zmc/zmc-alarm-exporter"

# 临时文件路径
TMP_DIR="/tmp/zmc-deploy"
TAR_FILE="${TMP_DIR}/${IMAGE_NAME}.tar.gz"

# ==================== 颜色定义 ====================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ==================== 辅助函数 ====================
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

show_help() {
    cat << EOF
ZMC Alarm Exporter 一键部署脚本

用法: $0 [选项]

选项:
  -b, --build-only    仅构建镜像，不部署
  -d, --deploy-only   仅部署（使用已有镜像文件）
  -h, --help          显示帮助信息

示例:
  $0              # 完整流程：构建 + 部署
  $0 -b           # 仅构建镜像
  $0 -d           # 仅部署（需先构建）

EOF
}

check_dependencies() {
    log_info "检查依赖..."

    if ! command -v docker &> /dev/null; then
        log_error "Docker 未安装"
        exit 1
    fi

    if ! command -v sshpass &> /dev/null; then
        log_error "sshpass 未安装，请运行: brew install sshpass 或 brew install hudochenkov/sshpass/sshpass"
        exit 1
    fi

    log_success "依赖检查通过"
}

build_image() {
    log_info "开始构建 Docker 镜像 (linux/amd64)..."

    # 获取脚本所在目录
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    cd "$SCRIPT_DIR"

    # 构建镜像
    docker buildx build --platform linux/amd64 -t ${IMAGE_NAME}:${IMAGE_TAG} --load .

    log_success "镜像构建完成"

    # 显示镜像信息
    docker images ${IMAGE_NAME}:${IMAGE_TAG}
}

export_image() {
    log_info "导出镜像..."

    mkdir -p ${TMP_DIR}
    docker save ${IMAGE_NAME}:${IMAGE_TAG} | gzip > ${TAR_FILE}

    local size=$(ls -lh ${TAR_FILE} | awk '{print $5}')
    log_success "镜像导出完成: ${TAR_FILE} (${size})"
}

transfer_image() {
    log_info "传输镜像到生产服务器..."

    sshpass -p "${PROD_PASS}" scp -o StrictHostKeyChecking=no -P ${PROD_PORT} \
        ${TAR_FILE} ${PROD_USER}@${PROD_HOST}:/root/

    log_success "镜像传输完成"
}

deploy_remote() {
    log_info "在生产服务器上部署..."

    sshpass -p "${PROD_PASS}" ssh -o StrictHostKeyChecking=no -p ${PROD_PORT} \
        ${PROD_USER}@${PROD_HOST} << 'REMOTE_SCRIPT'

set -e

IMAGE_NAME="zmc-alarm-exporter"
IMAGE_TAG="latest"
CONTAINER_NAME="zmc-alarm-exporter"
DEPLOY_PATH="/zmc/zmc-alarm-exporter"

echo "==> 停止旧容器..."
docker stop ${CONTAINER_NAME} 2>/dev/null || true
docker rm ${CONTAINER_NAME} 2>/dev/null || true

echo "==> 删除旧镜像..."
docker rmi ${IMAGE_NAME}:${IMAGE_TAG} 2>/dev/null || true

echo "==> 加载新镜像..."
docker load < /root/${IMAGE_NAME}.tar.gz

echo "==> 启动新容器..."
docker run -d \
    --name ${CONTAINER_NAME} \
    --restart unless-stopped \
    -p 8080:8080 \
    --env-file ${DEPLOY_PATH}/.env \
    ${IMAGE_NAME}:${IMAGE_TAG}

echo "==> 等待服务启动..."
sleep 5

echo "==> 检查容器状态..."
docker ps -f name=${CONTAINER_NAME} --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo "==> 查看启动日志..."
docker logs --tail 15 ${CONTAINER_NAME}

echo "==> 清理临时文件..."
rm -f /root/${IMAGE_NAME}.tar.gz

REMOTE_SCRIPT

    log_success "部署完成"
}

# ==================== 主流程 ====================
main() {
    local build_only=false
    local deploy_only=false

    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            -b|--build-only)
                build_only=true
                shift
                ;;
            -d|--deploy-only)
                deploy_only=true
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                log_error "未知选项: $1"
                show_help
                exit 1
                ;;
        esac
    done

    echo ""
    echo "========================================"
    echo "  ZMC Alarm Exporter 部署脚本"
    echo "========================================"
    echo ""

    local start_time=$(date +%s)

    check_dependencies

    if [ "$deploy_only" = false ]; then
        build_image
        export_image
    fi

    if [ "$build_only" = false ]; then
        if [ ! -f "${TAR_FILE}" ]; then
            log_error "镜像文件不存在: ${TAR_FILE}"
            log_error "请先运行 $0 -b 构建镜像"
            exit 1
        fi

        transfer_image
        deploy_remote
    fi

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    echo ""
    echo "========================================"
    log_success "全部完成! 耗时: ${duration}秒"
    echo "========================================"
    echo ""

    if [ "$build_only" = false ]; then
        echo "常用命令:"
        echo "  查看日志: ssh -p ${PROD_PORT} ${PROD_USER}@${PROD_HOST} 'docker logs -f ${IMAGE_NAME}'"
        echo "  重启服务: ssh -p ${PROD_PORT} ${PROD_USER}@${PROD_HOST} 'docker restart ${IMAGE_NAME}'"
        echo ""
    fi
}

main "$@"
