#!/bin/bash
#
# ZMC Alarm Exporter - 一键安装脚本
#
# 功能：
#   - 检查和安装系统依赖
#   - 创建 Python 虚拟环境并安装依赖
#   - 初始化 Oracle 数据库表结构
#   - 生成配置文件
#   - 启动服务
#
# 用法：
#   ./install.sh [选项]
#
# 选项：
#   --skip-db       跳过数据库初始化
#   --skip-deps     跳过依赖安装
#   --docker        使用 Docker 部署
#   --uninstall     卸载服务
#   -y, --yes       自动确认所有提示
#   -h, --help      显示帮助信息
#

set -e

# ============================================================================
# 颜色定义
# ============================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ============================================================================
# 全局变量
# ============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="zmc-alarm-exporter"
VENV_DIR="${SCRIPT_DIR}/venv"
LOG_DIR="${SCRIPT_DIR}/logs"
ENV_FILE="${SCRIPT_DIR}/.env"
ENV_EXAMPLE="${SCRIPT_DIR}/.env.example"
REQUIREMENTS_FILE="${SCRIPT_DIR}/requirements.txt"
SQL_INIT_FILE="${SCRIPT_DIR}/sql/init_sync_tables.sql"
SERVICE_FILE="${SCRIPT_DIR}/bin/zmc-alarm-exporter.service"
SYSTEMD_DIR="/etc/systemd/system"

# 安装选项
SKIP_DB=false
SKIP_DEPS=false
USE_DOCKER=false
UNINSTALL=false
AUTO_YES=false

# Python 最低版本要求
PYTHON_MIN_VERSION="3.10"

# ============================================================================
# 日志函数
# ============================================================================
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

log_step() {
    echo -e "\n${BLUE}==>${NC} ${CYAN}$1${NC}"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

# ============================================================================
# 工具函数
# ============================================================================

# 确认提示
confirm() {
    if [ "$AUTO_YES" = true ]; then
        return 0
    fi

    local prompt="${1:-确认继续?}"
    echo -en "${YELLOW}$prompt [y/N]: ${NC}"
    read -r response
    case "$response" in
        [yY][eE][sS]|[yY])
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

# 检查命令是否存在
check_command() {
    if command -v "$1" &> /dev/null; then
        return 0
    else
        return 1
    fi
}

# 检测操作系统
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if [ -f /etc/os-release ]; then
            . /etc/os-release
            echo "$ID"
        else
            echo "linux"
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    else
        echo "unknown"
    fi
}

# 检测包管理器
detect_package_manager() {
    local os=$(detect_os)
    case "$os" in
        ubuntu|debian)
            echo "apt"
            ;;
        centos|rhel|fedora)
            if check_command dnf; then
                echo "dnf"
            else
                echo "yum"
            fi
            ;;
        macos)
            echo "brew"
            ;;
        *)
            echo "unknown"
            ;;
    esac
}

# ============================================================================
# 依赖检查和安装
# ============================================================================

# 查找可用的 Python 命令 (仅返回命令路径，不输出日志)
find_python_cmd() {
    local python_cmd=""

    # 检查可用的 Python 命令
    for cmd in python3.12 python3.11 python3.10 python3 python; do
        if check_command "$cmd"; then
            local version=$($cmd -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)
            if [ -n "$version" ]; then
                local major=$(echo "$version" | cut -d. -f1)
                local minor=$(echo "$version" | cut -d. -f2)
                if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
                    echo "$cmd"
                    return 0
                fi
            fi
        fi
    done

    return 1
}

# 检查 Python 版本
check_python_version() {
    log_step "检查 Python 版本..."

    local python_cmd
    python_cmd=$(find_python_cmd)

    if [ -z "$python_cmd" ]; then
        log_error "未找到 Python 3.10+ 版本"
        log_info "请先安装 Python 3.10 或更高版本："

        local os=$(detect_os)
        case "$os" in
            ubuntu|debian)
                echo "  sudo apt update && sudo apt install python3.10 python3.10-venv python3-pip"
                ;;
            centos|rhel)
                echo "  sudo yum install python310 python310-pip"
                ;;
            macos)
                echo "  brew install python@3.10"
                ;;
            *)
                echo "  请访问 https://www.python.org/downloads/ 下载安装"
                ;;
        esac
        return 1
    fi

    local version=$($python_cmd --version 2>&1)
    log_success "找到 Python: $version ($python_cmd)"

    # 将结果保存到全局变量而不是 echo
    PYTHON_CMD="$python_cmd"
    return 0
}

# 安装系统依赖
install_system_deps() {
    log_step "检查系统依赖..."

    local os=$(detect_os)
    local pkg_mgr=$(detect_package_manager)
    local missing_deps=()

    # 检查必要的命令
    local required_commands=("curl" "git")
    for cmd in "${required_commands[@]}"; do
        if ! check_command "$cmd"; then
            missing_deps+=("$cmd")
        fi
    done

    if [ ${#missing_deps[@]} -eq 0 ]; then
        log_success "所有系统依赖已满足"
        return 0
    fi

    log_warn "缺少以下系统依赖: ${missing_deps[*]}"

    if ! confirm "是否自动安装缺少的依赖?"; then
        log_error "请手动安装依赖后重试"
        return 1
    fi

    case "$pkg_mgr" in
        apt)
            sudo apt update
            sudo apt install -y "${missing_deps[@]}"
            ;;
        yum)
            sudo yum install -y "${missing_deps[@]}"
            ;;
        dnf)
            sudo dnf install -y "${missing_deps[@]}"
            ;;
        brew)
            brew install "${missing_deps[@]}"
            ;;
        *)
            log_error "无法识别的包管理器，请手动安装: ${missing_deps[*]}"
            return 1
            ;;
    esac

    log_success "系统依赖安装完成"
}

# ============================================================================
# Python 环境设置
# ============================================================================

setup_python_env() {
    log_step "设置 Python 虚拟环境..."

    # 检查 Python 版本，结果保存在全局变量 PYTHON_CMD
    check_python_version
    if [ $? -ne 0 ] || [ -z "$PYTHON_CMD" ]; then
        return 1
    fi

    local python_cmd="$PYTHON_CMD"

    # 创建虚拟环境
    if [ ! -d "$VENV_DIR" ]; then
        log_info "创建虚拟环境: $VENV_DIR"
        "$python_cmd" -m venv "$VENV_DIR"
        if [ $? -ne 0 ]; then
            log_error "创建虚拟环境失败"
            return 1
        fi
    else
        log_info "虚拟环境已存在: $VENV_DIR"
    fi

    # 激活虚拟环境
    if [ -f "${VENV_DIR}/bin/activate" ]; then
        source "${VENV_DIR}/bin/activate"
    else
        log_error "虚拟环境激活脚本不存在: ${VENV_DIR}/bin/activate"
        return 1
    fi

    # 升级 pip
    log_info "升级 pip..."
    "${VENV_DIR}/bin/pip" install --upgrade pip -q

    # 安装依赖
    if [ -f "$REQUIREMENTS_FILE" ]; then
        log_info "安装 Python 依赖包..."
        "${VENV_DIR}/bin/pip" install -r "$REQUIREMENTS_FILE" -q
        log_success "Python 依赖安装完成"
    else
        log_warn "未找到 requirements.txt 文件"
    fi

    # 显示已安装的主要包
    log_info "已安装的主要包:"
    "${VENV_DIR}/bin/pip" list | grep -E "^(fastapi|uvicorn|oracledb|httpx|prometheus)" || true
}

# ============================================================================
# 配置文件设置
# ============================================================================

setup_config() {
    log_step "配置环境变量..."

    # 创建日志目录
    mkdir -p "$LOG_DIR"

    # 检查是否已有配置文件
    if [ -f "$ENV_FILE" ]; then
        log_info "发现已有配置文件: $ENV_FILE"
        if ! confirm "是否重新配置? (会备份现有配置)"; then
            log_info "跳过配置，使用现有配置文件"
            return 0
        fi
        # 备份现有配置
        local backup_file="${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
        cp "$ENV_FILE" "$backup_file"
        log_info "已备份配置到: $backup_file"
    fi

    # 复制模板
    if [ -f "$ENV_EXAMPLE" ]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
    else
        log_warn "未找到 .env.example，创建默认配置..."
        create_default_env
    fi

    # 交互式配置
    configure_interactively

    log_success "配置文件已创建: $ENV_FILE"
}

# 创建默认环境配置
create_default_env() {
    cat > "$ENV_FILE" << 'EOF'
# ZMC Alarm Exporter 环境变量配置
# 自动生成于 $(date)

# ========== 应用配置 ==========
DEBUG=false

# ========== Oracle 数据库配置 ==========
ZMC_ORACLE_HOST=localhost
ZMC_ORACLE_PORT=1521
ZMC_ORACLE_SERVICE_NAME=ORCL
ZMC_ORACLE_USERNAME=zmc
ZMC_ORACLE_PASSWORD=password
ZMC_ORACLE_POOL_MIN=2
ZMC_ORACLE_POOL_MAX=10
ZMC_ORACLE_TIMEOUT=30

# ========== Alertmanager 配置 ==========
ALERTMANAGER_URL=http://localhost:9093
ALERTMANAGER_API_VERSION=v2
ALERTMANAGER_AUTH_ENABLED=false
ALERTMANAGER_TIMEOUT=30
ALERTMANAGER_RETRY_COUNT=3
ALERTMANAGER_RETRY_INTERVAL=1000

# ========== 同步服务配置 ==========
SYNC_ENABLED=true
SYNC_SCAN_INTERVAL=60
SYNC_HEARTBEAT_INTERVAL=120
SYNC_BATCH_SIZE=100
SYNC_SYNC_ON_STARTUP=true
SYNC_HISTORY_HOURS=24
SYNC_ALARM_LEVELS=1,2,3,4

# ========== 日志配置 ==========
LOG_LEVEL=INFO
LOG_FORMAT=json

# ========== 服务器配置 ==========
SERVER_HOST=0.0.0.0
SERVER_PORT=8080
SERVER_WORKERS=1
EOF
}

# 交互式配置
configure_interactively() {
    echo ""
    log_info "请配置以下关键参数 (回车使用默认值):"
    echo ""

    # Oracle 配置
    echo -e "${CYAN}=== Oracle 数据库配置 ===${NC}"

    read -p "Oracle 主机地址 [10.101.1.42]: " oracle_host
    oracle_host=${oracle_host:-10.101.1.42}

    read -p "Oracle 端口 [1522]: " oracle_port
    oracle_port=${oracle_port:-1522}

    read -p "Oracle 服务名 [rb]: " oracle_service
    oracle_service=${oracle_service:-rb}

    read -p "Oracle 用户名 [zmc]: " oracle_user
    oracle_user=${oracle_user:-zmc}

    read -sp "Oracle 密码 [smart]: " oracle_pass
    oracle_pass=${oracle_pass:-smart}
    echo ""

    # Alertmanager 配置
    echo ""
    echo -e "${CYAN}=== Alertmanager 配置 ===${NC}"

    read -p "Alertmanager URL [http://localhost:9093]: " am_url
    am_url=${am_url:-http://localhost:9093}

    # 服务配置
    echo ""
    echo -e "${CYAN}=== 服务配置 ===${NC}"

    read -p "服务监听端口 [8080]: " server_port
    server_port=${server_port:-8080}

    # 更新配置文件
    sed -i.tmp "s|^ZMC_ORACLE_HOST=.*|ZMC_ORACLE_HOST=$oracle_host|" "$ENV_FILE"
    sed -i.tmp "s|^ZMC_ORACLE_PORT=.*|ZMC_ORACLE_PORT=$oracle_port|" "$ENV_FILE"
    sed -i.tmp "s|^ZMC_ORACLE_SERVICE_NAME=.*|ZMC_ORACLE_SERVICE_NAME=$oracle_service|" "$ENV_FILE"
    sed -i.tmp "s|^ZMC_ORACLE_USERNAME=.*|ZMC_ORACLE_USERNAME=$oracle_user|" "$ENV_FILE"
    sed -i.tmp "s|^ZMC_ORACLE_PASSWORD=.*|ZMC_ORACLE_PASSWORD=$oracle_pass|" "$ENV_FILE"
    sed -i.tmp "s|^ALERTMANAGER_URL=.*|ALERTMANAGER_URL=$am_url|" "$ENV_FILE"
    sed -i.tmp "s|^SERVER_PORT=.*|SERVER_PORT=$server_port|" "$ENV_FILE"

    # 清理临时文件
    rm -f "${ENV_FILE}.tmp"

    echo ""
    log_info "配置已保存到 $ENV_FILE"
}

# ============================================================================
# 数据库初始化
# ============================================================================

init_database() {
    log_step "初始化数据库..."

    if [ ! -f "$SQL_INIT_FILE" ]; then
        log_error "未找到数据库初始化脚本: $SQL_INIT_FILE"
        return 1
    fi

    # 加载环境变量
    if [ -f "$ENV_FILE" ]; then
        set -a
        source "$ENV_FILE"
        set +a
    fi

    local oracle_host="${ZMC_ORACLE_HOST:-localhost}"
    local oracle_port="${ZMC_ORACLE_PORT:-1521}"
    local oracle_service="${ZMC_ORACLE_SERVICE_NAME:-ORCL}"
    local oracle_user="${ZMC_ORACLE_USERNAME:-zmc}"
    local oracle_pass="${ZMC_ORACLE_PASSWORD:-password}"

    log_info "数据库连接信息:"
    echo "  主机: $oracle_host:$oracle_port"
    echo "  服务: $oracle_service"
    echo "  用户: $oracle_user"
    echo ""

    # 检查是否安装了 sqlplus
    if check_command sqlplus; then
        log_info "使用 sqlplus 初始化数据库..."

        if ! confirm "确认执行数据库初始化? (将创建新表和配置)"; then
            log_info "跳过数据库初始化"
            return 0
        fi

        # 执行 SQL 脚本
        local conn_string="${oracle_user}/${oracle_pass}@${oracle_host}:${oracle_port}/${oracle_service}"

        echo "EXIT;" | cat "$SQL_INIT_FILE" - | sqlplus -S "$conn_string" 2>&1 | while read line; do
            if echo "$line" | grep -qi "error"; then
                log_error "$line"
            elif echo "$line" | grep -qi "created"; then
                log_success "$line"
            elif [ -n "$line" ]; then
                echo "  $line"
            fi
        done

        log_success "数据库初始化完成"

    elif check_command python3 || check_command python; then
        # 使用 Python 执行
        log_info "使用 Python oracledb 初始化数据库..."

        if [ -d "$VENV_DIR" ]; then
            source "${VENV_DIR}/bin/activate"
        fi

        python3 << PYEOF
import oracledb
import sys

try:
    dsn = f"${oracle_host}:${oracle_port}/${oracle_service}"
    print(f"连接到: {dsn}")

    conn = oracledb.connect(
        user="${oracle_user}",
        password="${oracle_pass}",
        dsn=dsn
    )

    cursor = conn.cursor()

    # 读取并执行 SQL 文件
    with open("${SQL_INIT_FILE}", "r") as f:
        sql_content = f.read()

    # 分割 SQL 语句（按分号分割，但要处理存储过程）
    statements = []
    current_stmt = ""
    in_procedure = False

    for line in sql_content.split('\n'):
        stripped = line.strip()

        # 检测存储过程开始
        if stripped.upper().startswith('CREATE OR REPLACE PROCEDURE'):
            in_procedure = True

        current_stmt += line + '\n'

        # 存储过程以 / 结束
        if in_procedure and stripped == '/':
            statements.append(current_stmt.rstrip('/\n'))
            current_stmt = ""
            in_procedure = False
        # 普通语句以 ; 结束
        elif not in_procedure and stripped.endswith(';'):
            statements.append(current_stmt.rstrip(';\n'))
            current_stmt = ""

    success_count = 0
    error_count = 0

    for stmt in statements:
        stmt = stmt.strip()
        if not stmt or stmt.startswith('--'):
            continue

        # 跳过 COMMENT 和 COMMIT 语句（简化处理）
        if stmt.upper().startswith('COMMENT') or stmt.upper() == 'COMMIT':
            continue

        try:
            cursor.execute(stmt)
            success_count += 1
        except oracledb.DatabaseError as e:
            error_obj, = e.args
            # 忽略"对象已存在"错误
            if error_obj.code in [955, 2261, 2264, 1430, 1408]:
                print(f"  [跳过] 对象已存在")
            else:
                print(f"  [错误] {error_obj.message}")
                error_count += 1

    conn.commit()
    cursor.close()
    conn.close()

    print(f"\n执行完成: {success_count} 成功, {error_count} 错误")

except Exception as e:
    print(f"数据库连接失败: {e}")
    sys.exit(1)
PYEOF

        if [ $? -eq 0 ]; then
            log_success "数据库初始化完成"
        else
            log_error "数据库初始化失败"
            return 1
        fi
    else
        log_warn "未找到 sqlplus 或 Python，无法自动初始化数据库"
        log_info "请手动执行以下命令初始化数据库:"
        echo ""
        echo "  sqlplus ${oracle_user}/${oracle_pass}@${oracle_host}:${oracle_port}/${oracle_service} @${SQL_INIT_FILE}"
        echo ""

        if ! confirm "是否已手动完成数据库初始化?"; then
            return 1
        fi
    fi
}

# ============================================================================
# 服务管理
# ============================================================================

install_systemd_service() {
    log_step "安装 Systemd 服务..."

    if [[ "$OSTYPE" == "darwin"* ]]; then
        log_warn "macOS 不支持 Systemd，跳过服务安装"
        log_info "请使用 ./bin/start.sh start 启动服务"
        return 0
    fi

    if [ ! -f "$SERVICE_FILE" ]; then
        log_info "创建 Systemd 服务文件..."
        create_systemd_service
    fi

    if ! confirm "是否安装为 Systemd 服务? (需要 sudo 权限)"; then
        log_info "跳过 Systemd 服务安装"
        return 0
    fi

    # 复制服务文件
    sudo cp "$SERVICE_FILE" "${SYSTEMD_DIR}/${APP_NAME}.service"

    # 重新加载 systemd
    sudo systemctl daemon-reload

    # 启用服务
    sudo systemctl enable "$APP_NAME"

    log_success "Systemd 服务安装完成"
    log_info "使用以下命令管理服务:"
    echo "  sudo systemctl start $APP_NAME    # 启动"
    echo "  sudo systemctl stop $APP_NAME     # 停止"
    echo "  sudo systemctl restart $APP_NAME  # 重启"
    echo "  sudo systemctl status $APP_NAME   # 状态"
}

create_systemd_service() {
    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=ZMC Alarm Exporter Service
Documentation=https://github.com/your-org/zmc-alarm-exporter
After=network.target oracle.service

[Service]
Type=simple
User=$(whoami)
Group=$(id -gn)
WorkingDirectory=${SCRIPT_DIR}
Environment="PATH=${VENV_DIR}/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=${ENV_FILE}
ExecStart=${VENV_DIR}/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
ExecReload=/bin/kill -HUP \$MAINPID
Restart=on-failure
RestartSec=10
StandardOutput=append:${LOG_DIR}/${APP_NAME}.log
StandardError=append:${LOG_DIR}/${APP_NAME}.log

# 安全配置
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=${LOG_DIR}

[Install]
WantedBy=multi-user.target
EOF
}

# ============================================================================
# Docker 部署
# ============================================================================

deploy_with_docker() {
    log_step "Docker 部署..."

    if ! check_command docker; then
        log_error "未找到 Docker，请先安装 Docker"
        log_info "安装指南: https://docs.docker.com/get-docker/"
        return 1
    fi

    if ! check_command docker-compose && ! docker compose version &>/dev/null; then
        log_error "未找到 docker-compose，请先安装"
        return 1
    fi

    # 设置配置文件
    if [ ! -f "$ENV_FILE" ]; then
        setup_config
    fi

    # 构建镜像
    log_info "构建 Docker 镜像..."
    docker build -t "$APP_NAME:latest" "$SCRIPT_DIR"

    # 启动服务
    log_info "启动 Docker Compose 服务..."
    cd "$SCRIPT_DIR"

    if docker compose version &>/dev/null; then
        docker compose up -d
    else
        docker-compose up -d
    fi

    log_success "Docker 部署完成"
    log_info "查看服务状态: docker compose ps"
    log_info "查看日志: docker compose logs -f"
}

# ============================================================================
# 启动服务
# ============================================================================

start_service() {
    log_step "启动服务..."

    local start_script="${SCRIPT_DIR}/bin/start.sh"

    if [ -f "$start_script" ]; then
        chmod +x "$start_script"
        "$start_script" start
    else
        # 直接启动
        if [ -d "$VENV_DIR" ]; then
            source "${VENV_DIR}/bin/activate"
        fi

        cd "$SCRIPT_DIR"

        # 加载环境变量
        if [ -f "$ENV_FILE" ]; then
            set -a
            source "$ENV_FILE"
            set +a
        fi

        log_info "启动 uvicorn 服务..."
        nohup python -m uvicorn app.main:app \
            --host "${SERVER_HOST:-0.0.0.0}" \
            --port "${SERVER_PORT:-8080}" \
            >> "${LOG_DIR}/${APP_NAME}.log" 2>&1 &

        local pid=$!
        echo $pid > "${LOG_DIR}/${APP_NAME}.pid"

        sleep 2

        if kill -0 $pid 2>/dev/null; then
            log_success "服务启动成功 (PID: $pid)"
        else
            log_error "服务启动失败，请检查日志: ${LOG_DIR}/${APP_NAME}.log"
            return 1
        fi
    fi
}

# ============================================================================
# 验证安装
# ============================================================================

verify_installation() {
    log_step "验证安装..."

    local port="${SERVER_PORT:-8080}"
    local max_attempts=10
    local attempt=0

    log_info "等待服务启动..."

    while [ $attempt -lt $max_attempts ]; do
        if curl -s "http://localhost:${port}/health" > /dev/null 2>&1; then
            log_success "服务健康检查通过"

            # 显示健康状态
            echo ""
            curl -s "http://localhost:${port}/health" | python3 -m json.tool 2>/dev/null || \
            curl -s "http://localhost:${port}/health"
            echo ""

            return 0
        fi

        attempt=$((attempt + 1))
        sleep 1
    done

    log_warn "无法连接到服务，请检查日志"
    return 1
}

# ============================================================================
# 卸载
# ============================================================================

uninstall() {
    log_step "卸载 ${APP_NAME}..."

    if ! confirm "确认卸载? 这将停止服务并删除虚拟环境"; then
        return 0
    fi

    # 停止服务
    local start_script="${SCRIPT_DIR}/bin/start.sh"
    if [ -f "$start_script" ]; then
        "$start_script" stop 2>/dev/null || true
    fi

    # 停止 systemd 服务
    if [[ "$OSTYPE" != "darwin"* ]] && systemctl is-active "$APP_NAME" &>/dev/null; then
        sudo systemctl stop "$APP_NAME"
        sudo systemctl disable "$APP_NAME"
        sudo rm -f "${SYSTEMD_DIR}/${APP_NAME}.service"
        sudo systemctl daemon-reload
    fi

    # 停止 Docker
    if check_command docker-compose || docker compose version &>/dev/null; then
        cd "$SCRIPT_DIR"
        docker compose down 2>/dev/null || docker-compose down 2>/dev/null || true
    fi

    # 删除虚拟环境
    if [ -d "$VENV_DIR" ] && confirm "删除虚拟环境?"; then
        rm -rf "$VENV_DIR"
        log_info "已删除虚拟环境"
    fi

    # 删除日志
    if [ -d "$LOG_DIR" ] && confirm "删除日志目录?"; then
        rm -rf "$LOG_DIR"
        log_info "已删除日志目录"
    fi

    log_success "卸载完成"
}

# ============================================================================
# 显示帮助
# ============================================================================

show_help() {
    cat << EOF
${CYAN}ZMC Alarm Exporter - 一键安装脚本${NC}

${YELLOW}用法:${NC}
    $0 [选项]

${YELLOW}选项:${NC}
    --skip-db       跳过数据库初始化
    --skip-deps     跳过系统依赖检查和安装
    --docker        使用 Docker 部署 (而非本地 Python)
    --uninstall     卸载服务
    -y, --yes       自动确认所有提示
    -h, --help      显示此帮助信息

${YELLOW}示例:${NC}
    $0                    # 完整安装 (交互式)
    $0 -y                 # 完整安装 (自动确认)
    $0 --skip-db          # 安装但跳过数据库初始化
    $0 --docker           # 使用 Docker 部署
    $0 --uninstall        # 卸载服务

${YELLOW}安装流程:${NC}
    1. 检查系统依赖 (curl, git)
    2. 检查/安装 Python 3.10+
    3. 创建虚拟环境并安装依赖
    4. 配置环境变量 (.env)
    5. 初始化 Oracle 数据库
    6. 启动服务并验证

${YELLOW}配置文件:${NC}
    .env                环境变量配置
    .env.example        配置模板

${YELLOW}日志文件:${NC}
    logs/${APP_NAME}.log

${YELLOW}管理命令:${NC}
    ./bin/start.sh start     启动服务
    ./bin/start.sh stop      停止服务
    ./bin/start.sh restart   重启服务
    ./bin/start.sh status    查看状态
    ./bin/start.sh logs      查看日志

EOF
}

# ============================================================================
# 显示安装摘要
# ============================================================================

show_summary() {
    echo ""
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}       安装完成！${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""
    echo -e "${CYAN}服务信息:${NC}"
    echo "  API 地址:     http://localhost:${SERVER_PORT:-8080}"
    echo "  健康检查:     http://localhost:${SERVER_PORT:-8080}/health"
    echo "  API 文档:     http://localhost:${SERVER_PORT:-8080}/docs"
    echo "  指标端点:     http://localhost:${SERVER_PORT:-8080}/metrics"
    echo ""
    echo -e "${CYAN}常用命令:${NC}"
    echo "  启动服务:     ./bin/start.sh start"
    echo "  停止服务:     ./bin/start.sh stop"
    echo "  查看状态:     ./bin/start.sh status"
    echo "  查看日志:     ./bin/start.sh logs-f"
    echo ""
    echo -e "${CYAN}配置文件:${NC}"
    echo "  环境配置:     ${ENV_FILE}"
    echo "  日志目录:     ${LOG_DIR}"
    echo ""
    echo -e "${YELLOW}注意事项:${NC}"
    echo "  1. 请确保 Oracle 数据库可访问"
    echo "  2. 请确保 Alertmanager 服务已启动"
    echo "  3. 生产环境请配置防火墙和 HTTPS"
    echo ""
}

# ============================================================================
# 主入口
# ============================================================================

main() {
    echo ""
    echo -e "${CYAN}╔════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║   ZMC Alarm Exporter - 安装程序            ║${NC}"
    echo -e "${CYAN}║   版本: 1.0.0                              ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════╝${NC}"
    echo ""

    # 解析命令行参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            --skip-db)
                SKIP_DB=true
                shift
                ;;
            --skip-deps)
                SKIP_DEPS=true
                shift
                ;;
            --docker)
                USE_DOCKER=true
                shift
                ;;
            --uninstall)
                UNINSTALL=true
                shift
                ;;
            -y|--yes)
                AUTO_YES=true
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

    # 切换到脚本目录
    cd "$SCRIPT_DIR"

    # 卸载模式
    if [ "$UNINSTALL" = true ]; then
        uninstall
        exit 0
    fi

    # Docker 部署模式
    if [ "$USE_DOCKER" = true ]; then
        setup_config
        deploy_with_docker
        exit 0
    fi

    # 标准安装流程

    # 1. 系统依赖
    if [ "$SKIP_DEPS" = false ]; then
        install_system_deps || exit 1
    fi

    # 2. Python 环境
    setup_python_env || exit 1

    # 3. 配置文件
    setup_config

    # 4. 数据库初始化
    if [ "$SKIP_DB" = false ]; then
        init_database
    fi

    # 5. 启动服务
    if confirm "是否立即启动服务?"; then
        start_service
        sleep 2
        verify_installation
    fi

    # 6. 可选：安装 Systemd 服务
    if [[ "$OSTYPE" != "darwin"* ]]; then
        install_systemd_service
    fi

    # 显示摘要
    show_summary
}

# 运行主函数
main "$@"
