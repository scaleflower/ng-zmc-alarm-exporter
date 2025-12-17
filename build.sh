#!/bin/bash
#
# ZMC Alarm Exporter 构建脚本
#
# 功能:
#   1. 自动递增版本号 (patch 版本)
#   2. 构建 Docker 镜像
#   3. 可选: 导出镜像到文件
#
# 用法:
#   ./build.sh              # 递增版本并构建
#   ./build.sh --no-bump    # 不递增版本，仅构建
#   ./build.sh --export     # 构建并导出镜像到 /tmp
#   ./build.sh --major      # 递增主版本号 (x.0.0)
#   ./build.sh --minor      # 递增次版本号 (x.y.0)
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VERSION_FILE="$SCRIPT_DIR/VERSION"
IMAGE_NAME="zmc-alarm-exporter"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 读取当前版本
get_version() {
    if [[ -f "$VERSION_FILE" ]]; then
        cat "$VERSION_FILE" | tr -d '\n'
    else
        echo "0.0.0"
    fi
}

# 递增版本号
bump_version() {
    local version="$1"
    local bump_type="$2"

    IFS='.' read -r major minor patch <<< "$version"

    case "$bump_type" in
        major)
            major=$((major + 1))
            minor=0
            patch=0
            ;;
        minor)
            minor=$((minor + 1))
            patch=0
            ;;
        patch|*)
            patch=$((patch + 1))
            ;;
    esac

    echo "${major}.${minor}.${patch}"
}

# 保存版本号
save_version() {
    echo "$1" > "$VERSION_FILE"
    log_info "Version updated to $1"
}

# 构建镜像
build_image() {
    local version="$1"

    log_info "Building Docker image: ${IMAGE_NAME}:${version}"

    docker build \
        --platform linux/amd64 \
        -t "${IMAGE_NAME}:${version}" \
        -t "${IMAGE_NAME}:latest" \
        "$SCRIPT_DIR"

    log_info "Build complete: ${IMAGE_NAME}:${version}"
}

# 导出镜像
export_image() {
    local version="$1"
    local output_file="/tmp/${IMAGE_NAME}-${version}.tar.gz"

    log_info "Exporting image to ${output_file}"

    docker save "${IMAGE_NAME}:${version}" | gzip > "$output_file"

    local size=$(ls -lh "$output_file" | awk '{print $5}')
    log_info "Export complete: ${output_file} (${size})"

    echo "$output_file"
}

# 主函数
main() {
    local bump_type="patch"
    local do_bump=true
    local do_export=false

    # 解析参数
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --no-bump)
                do_bump=false
                shift
                ;;
            --export)
                do_export=true
                shift
                ;;
            --major)
                bump_type="major"
                shift
                ;;
            --minor)
                bump_type="minor"
                shift
                ;;
            --patch)
                bump_type="patch"
                shift
                ;;
            -h|--help)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --no-bump    Don't increment version"
                echo "  --export     Export image to /tmp after build"
                echo "  --major      Increment major version (x.0.0)"
                echo "  --minor      Increment minor version (x.y.0)"
                echo "  --patch      Increment patch version (default)"
                echo "  -h, --help   Show this help"
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done

    # 获取当前版本
    local current_version=$(get_version)
    log_info "Current version: ${current_version}"

    # 递增版本号
    local new_version="$current_version"
    if [[ "$do_bump" == true ]]; then
        new_version=$(bump_version "$current_version" "$bump_type")
        save_version "$new_version"
    fi

    # 构建镜像
    build_image "$new_version"

    # 导出镜像
    if [[ "$do_export" == true ]]; then
        export_image "$new_version"
    fi

    echo ""
    log_info "=== Build Summary ==="
    echo "  Version: ${new_version}"
    echo "  Image:   ${IMAGE_NAME}:${new_version}"
    echo "  Latest:  ${IMAGE_NAME}:latest"

    if [[ "$do_export" == true ]]; then
        echo "  Export:  /tmp/${IMAGE_NAME}-${new_version}.tar.gz"
    fi
}

main "$@"
