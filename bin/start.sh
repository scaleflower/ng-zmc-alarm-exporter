#!/bin/bash
#
# ZMC Alarm Exporter - 启动脚本
# 支持 Linux 和 macOS
#

set -e

# ============================================================================
# 配置变量
# ============================================================================

# 脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 项目根目录
APP_HOME="$(dirname "$SCRIPT_DIR")"
# 应用名称
APP_NAME="zmc-alarm-exporter"
# PID 文件
PID_FILE="${APP_HOME}/logs/${APP_NAME}.pid"
# 日志目录
LOG_DIR="${APP_HOME}/logs"
# 日志文件
LOG_FILE="${LOG_DIR}/${APP_NAME}.log"
# 环境变量文件
ENV_FILE="${APP_HOME}/.env"
# Python 虚拟环境
VENV_DIR="${APP_HOME}/venv"

# 服务配置（可通过环境变量覆盖）
HOST="${SERVER_HOST:-0.0.0.0}"
PORT="${SERVER_PORT:-8080}"
WORKERS="${SERVER_WORKERS:-1}"

# ============================================================================
# 辅助函数
# ============================================================================

log_info() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $1"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $1" >&2
}

log_warn() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [WARN] $1"
}

# 检查命令是否存在
check_command() {
    if ! command -v "$1" &> /dev/null; then
        log_error "Command '$1' not found. Please install it first."
        return 1
    fi
}

# 检查 Python 版本
check_python() {
    local python_cmd=""

    # 优先使用虚拟环境中的 Python
    if [ -f "${VENV_DIR}/bin/python" ]; then
        python_cmd="${VENV_DIR}/bin/python"
    elif command -v python3 &> /dev/null; then
        python_cmd="python3"
    elif command -v python &> /dev/null; then
        python_cmd="python"
    else
        log_error "Python not found. Please install Python 3.10+."
        return 1
    fi

    # 检查版本
    local version=$($python_cmd -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    local major=$(echo $version | cut -d. -f1)
    local minor=$(echo $version | cut -d. -f2)

    if [ "$major" -lt 3 ] || ([ "$major" -eq 3 ] && [ "$minor" -lt 10 ]); then
        log_error "Python 3.10+ required, but found $version"
        return 1
    fi

    echo "$python_cmd"
}

# 获取进程 PID
get_pid() {
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
            return 0
        fi
    fi
    return 1
}

# 检查服务是否运行
is_running() {
    get_pid > /dev/null 2>&1
}

# ============================================================================
# 主要功能
# ============================================================================

# 初始化环境
init_env() {
    # 创建日志目录
    mkdir -p "$LOG_DIR"

    # 加载环境变量
    if [ -f "$ENV_FILE" ]; then
        log_info "Loading environment from $ENV_FILE"
        set -a
        source "$ENV_FILE"
        set +a
    else
        log_warn "Environment file not found: $ENV_FILE"
        log_warn "Using default configuration. Copy .env.example to .env for custom settings."
    fi

    # 设置 Oracle 环境 (用于 thick 模式，解决 DPY-3015 错误)
    # 按优先级搜索 Oracle 安装目录
    local oracle_home_paths=(
        "${ORACLE_HOME}"
        "/soft/oracle"
        "/u01/app/oracle/product/19.0.0/dbhome_1"
        "/u01/app/oracle/product/12.2.0/dbhome_1"
        "/opt/oracle/instantclient_19_19"
        "/opt/oracle/instantclient"
    )

    for oracle_path in "${oracle_home_paths[@]}"; do
        if [ -n "$oracle_path" ] && [ -f "$oracle_path/lib/libclntsh.so" ]; then
            export ORACLE_HOME="$oracle_path"
            export LD_LIBRARY_PATH="${oracle_path}/lib:${LD_LIBRARY_PATH}"
            # 设置 NLS_LANG 以避免字符集问题
            export NLS_LANG="${NLS_LANG:-AMERICAN_AMERICA.AL32UTF8}"
            log_info "Oracle environment configured: ORACLE_HOME=$oracle_path"
            break
        fi
    done

    # 如果配置了自定义客户端库路径，也添加到 LD_LIBRARY_PATH
    if [ -n "${ZMC_ORACLE_CLIENT_LIB_DIR}" ] && [ -d "${ZMC_ORACLE_CLIENT_LIB_DIR}" ]; then
        export LD_LIBRARY_PATH="${ZMC_ORACLE_CLIENT_LIB_DIR}:${LD_LIBRARY_PATH}"
        log_info "Custom Oracle client library added: ${ZMC_ORACLE_CLIENT_LIB_DIR}"
    fi
}

# 创建虚拟环境
setup_venv() {
    if [ ! -d "$VENV_DIR" ]; then
        log_info "Creating virtual environment..."
        python3 -m venv "$VENV_DIR"
    fi

    log_info "Activating virtual environment..."
    source "${VENV_DIR}/bin/activate"

    # 安装依赖
    if [ -f "${APP_HOME}/requirements.txt" ]; then
        log_info "Installing dependencies..."
        pip install -q -r "${APP_HOME}/requirements.txt"
    fi
}

# 启动服务
start() {
    if is_running; then
        log_warn "Service is already running (PID: $(get_pid))"
        return 0
    fi

    log_info "Starting $APP_NAME..."

    # 初始化环境
    init_env

    # 获取 Python 命令
    local python_cmd=$(check_python)
    if [ $? -ne 0 ]; then
        return 1
    fi

    # 切换到应用目录
    cd "$APP_HOME"

    # 激活虚拟环境（如果存在）
    if [ -f "${VENV_DIR}/bin/activate" ]; then
        source "${VENV_DIR}/bin/activate"
    fi

    # 启动服务
    log_info "Starting uvicorn server on ${HOST}:${PORT}..."

    nohup $python_cmd -m uvicorn app.main:app \
        --host "$HOST" \
        --port "$PORT" \
        --workers "$WORKERS" \
        >> "$LOG_FILE" 2>&1 &

    local pid=$!
    echo $pid > "$PID_FILE"

    # 等待启动
    sleep 2

    if is_running; then
        log_info "Service started successfully (PID: $pid)"
        log_info "Log file: $LOG_FILE"
        log_info "API endpoint: http://${HOST}:${PORT}"
        log_info "Health check: http://${HOST}:${PORT}/health"
    else
        log_error "Failed to start service. Check log file: $LOG_FILE"
        return 1
    fi
}

# 停止服务
stop() {
    if ! is_running; then
        log_warn "Service is not running"
        rm -f "$PID_FILE"
        return 0
    fi

    local pid=$(get_pid)
    log_info "Stopping $APP_NAME (PID: $pid)..."

    # 发送 TERM 信号
    kill -TERM "$pid" 2>/dev/null

    # 等待进程结束
    local count=0
    while kill -0 "$pid" 2>/dev/null && [ $count -lt 30 ]; do
        sleep 1
        count=$((count + 1))
    done

    # 如果进程仍在运行，强制终止
    if kill -0 "$pid" 2>/dev/null; then
        log_warn "Process did not stop gracefully, sending KILL signal..."
        kill -KILL "$pid" 2>/dev/null
        sleep 1
    fi

    rm -f "$PID_FILE"
    log_info "Service stopped"
}

# 重启服务
restart() {
    log_info "Restarting $APP_NAME..."
    stop
    sleep 2
    start
}

# 查看状态
status() {
    if is_running; then
        local pid=$(get_pid)
        log_info "Service is running (PID: $pid)"

        # 显示进程信息
        if command -v ps &> /dev/null; then
            echo ""
            echo "Process details:"
            ps -p "$pid" -o pid,ppid,user,%cpu,%mem,etime,command 2>/dev/null || true
        fi

        # 尝试获取健康状态
        echo ""
        echo "Health check:"
        if command -v curl &> /dev/null; then
            curl -s "http://${HOST}:${PORT}/health" 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "Unable to fetch health status"
        else
            echo "curl not available, skipping health check"
        fi

        return 0
    else
        log_info "Service is not running"
        return 1
    fi
}

# 查看日志
logs() {
    local lines="${1:-100}"

    if [ -f "$LOG_FILE" ]; then
        log_info "Showing last $lines lines of $LOG_FILE"
        tail -n "$lines" "$LOG_FILE"
    else
        log_warn "Log file not found: $LOG_FILE"
    fi
}

# 实时查看日志
logs_follow() {
    if [ -f "$LOG_FILE" ]; then
        log_info "Following log file: $LOG_FILE (Ctrl+C to exit)"
        tail -f "$LOG_FILE"
    else
        log_warn "Log file not found: $LOG_FILE"
    fi
}

# 安装服务
install() {
    log_info "Installing $APP_NAME..."

    # 检查 Python
    check_python || return 1

    # 创建虚拟环境并安装依赖
    setup_venv

    # 创建必要目录
    mkdir -p "$LOG_DIR"

    # 复制环境变量模板
    if [ ! -f "$ENV_FILE" ] && [ -f "${APP_HOME}/.env.example" ]; then
        cp "${APP_HOME}/.env.example" "$ENV_FILE"
        log_info "Created $ENV_FILE from template. Please edit it with your configuration."
    fi

    log_info "Installation completed!"
    log_info ""
    log_info "Next steps:"
    log_info "  1. Edit $ENV_FILE with your Oracle and Alertmanager settings"
    log_info "  2. Initialize database: sqlplus zmc/password@db @sql/init_sync_tables.sql"
    log_info "  3. Start service: $0 start"
}

# 显示帮助
usage() {
    cat << EOF
Usage: $0 <command> [options]

ZMC Alarm Exporter - Sync ZMC alarms to Prometheus Alertmanager

Commands:
    start       Start the service
    stop        Stop the service
    restart     Restart the service
    status      Show service status and health
    logs [n]    Show last n lines of log (default: 100)
    logs-f      Follow log output in real-time
    install     Install dependencies and setup environment
    help        Show this help message

Examples:
    $0 start              # Start the service
    $0 stop               # Stop the service
    $0 restart            # Restart the service
    $0 status             # Check service status
    $0 logs 200           # Show last 200 lines of log
    $0 logs-f             # Follow log output

Environment Variables:
    SERVER_HOST     Listen address (default: 0.0.0.0)
    SERVER_PORT     Listen port (default: 8080)
    SERVER_WORKERS  Number of worker processes (default: 1)

Files:
    PID file:     $PID_FILE
    Log file:     $LOG_FILE
    Config file:  $ENV_FILE

EOF
}

# ============================================================================
# 主入口
# ============================================================================

case "${1:-}" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    status)
        status
        ;;
    logs)
        logs "${2:-100}"
        ;;
    logs-f|follow)
        logs_follow
        ;;
    install)
        install
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        usage
        exit 1
        ;;
esac
