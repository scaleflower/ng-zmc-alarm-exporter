@echo off
REM ============================================================================
REM ZMC Alarm Exporter - Windows Installation Script
REM
REM Features:
REM   - Check and install Python virtual environment
REM   - Install Python dependencies
REM   - Generate configuration file
REM   - Initialize Oracle database (optional)
REM   - Start service
REM
REM Usage:
REM   install.bat [options]
REM
REM Options:
REM   --skip-db       Skip database initialization
REM   --skip-deps     Skip dependency installation
REM   --uninstall     Uninstall service
REM   -y, --yes       Auto confirm all prompts
REM   -h, --help      Show help message
REM ============================================================================

setlocal enabledelayedexpansion

REM ============================================================================
REM Global Variables
REM ============================================================================
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "APP_NAME=zmc-alarm-exporter"
set "VENV_DIR=%SCRIPT_DIR%\venv"
set "LOG_DIR=%SCRIPT_DIR%\logs"
set "ENV_FILE=%SCRIPT_DIR%\.env"
set "ENV_EXAMPLE=%SCRIPT_DIR%\.env.example"
set "REQUIREMENTS_FILE=%SCRIPT_DIR%\requirements.txt"
set "SQL_INIT_FILE=%SCRIPT_DIR%\sql\init_sync_tables.sql"

REM Installation options
set "SKIP_DB=false"
set "SKIP_DEPS=false"
set "UNINSTALL=false"
set "AUTO_YES=false"

REM Python minimum version
set "PYTHON_MIN_VERSION=3.10"

REM ============================================================================
REM Parse Command Line Arguments
REM ============================================================================
:parse_args
if "%~1"=="" goto main
if /i "%~1"=="--skip-db" (
    set "SKIP_DB=true"
    shift
    goto parse_args
)
if /i "%~1"=="--skip-deps" (
    set "SKIP_DEPS=true"
    shift
    goto parse_args
)
if /i "%~1"=="--uninstall" (
    set "UNINSTALL=true"
    shift
    goto parse_args
)
if /i "%~1"=="-y" (
    set "AUTO_YES=true"
    shift
    goto parse_args
)
if /i "%~1"=="--yes" (
    set "AUTO_YES=true"
    shift
    goto parse_args
)
if /i "%~1"=="-h" goto show_help
if /i "%~1"=="--help" goto show_help

echo [ERROR] Unknown option: %~1
goto show_help

REM ============================================================================
REM Main Entry
REM ============================================================================
:main
echo.
echo =====================================================
echo    ZMC Alarm Exporter - Windows Installation
echo    Version: 1.0.0
echo =====================================================
echo.

cd /d "%SCRIPT_DIR%"

REM Uninstall mode
if "%UNINSTALL%"=="true" (
    call :uninstall
    goto end
)

REM Standard installation flow

REM 1. Check Python
call :check_python
if errorlevel 1 goto error_exit

REM 2. Setup Python environment
if "%SKIP_DEPS%"=="false" (
    call :setup_python_env
    if errorlevel 1 goto error_exit
)

REM 3. Setup configuration
call :setup_config

REM 4. Database initialization
if "%SKIP_DB%"=="false" (
    call :init_database
)

REM 5. Start service
call :confirm "Start service now?"
if "%CONFIRM_RESULT%"=="yes" (
    call :start_service
    timeout /t 2 /nobreak >nul
    call :verify_installation
)

REM Show summary
call :show_summary

goto end

REM ============================================================================
REM Functions
REM ============================================================================

:log_info
echo [INFO] %~1
goto :eof

:log_warn
echo [WARN] %~1
goto :eof

:log_error
echo [ERROR] %~1
goto :eof

:log_success
echo [OK] %~1
goto :eof

:log_step
echo.
echo ==^> %~1
goto :eof

REM ============================================================================
REM Confirm Prompt
REM ============================================================================
:confirm
set "CONFIRM_RESULT=no"
if "%AUTO_YES%"=="true" (
    set "CONFIRM_RESULT=yes"
    goto :eof
)
set /p "user_input=%~1 [y/N]: "
if /i "%user_input%"=="y" set "CONFIRM_RESULT=yes"
if /i "%user_input%"=="yes" set "CONFIRM_RESULT=yes"
goto :eof

REM ============================================================================
REM Check Python Version
REM ============================================================================
:check_python
call :log_step "Checking Python version..."

set "PYTHON_CMD="

REM Try different Python commands
for %%P in (python3 python py) do (
    where %%P >nul 2>&1
    if not errorlevel 1 (
        for /f "tokens=*" %%V in ('%%P -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2^>nul') do (
            set "PY_VERSION=%%V"
        )
        if defined PY_VERSION (
            for /f "tokens=1,2 delims=." %%A in ("!PY_VERSION!") do (
                set "PY_MAJOR=%%A"
                set "PY_MINOR=%%B"
            )
            if !PY_MAJOR! geq 3 (
                if !PY_MINOR! geq 10 (
                    set "PYTHON_CMD=%%P"
                    goto :python_found
                )
            )
        )
    )
)

REM Python not found
call :log_error "Python 3.10+ not found!"
echo.
echo Please install Python 3.10 or higher:
echo   1. Download from https://www.python.org/downloads/
echo   2. During installation, check "Add Python to PATH"
echo   3. Re-run this script
echo.
exit /b 1

:python_found
for /f "tokens=*" %%V in ('!PYTHON_CMD! --version 2^>^&1') do set "PY_FULL_VERSION=%%V"
call :log_success "Found Python: !PY_FULL_VERSION! (!PYTHON_CMD!)"
exit /b 0

REM ============================================================================
REM Setup Python Virtual Environment
REM ============================================================================
:setup_python_env
call :log_step "Setting up Python virtual environment..."

REM Create virtual environment
if not exist "%VENV_DIR%" (
    call :log_info "Creating virtual environment: %VENV_DIR%"
    %PYTHON_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        call :log_error "Failed to create virtual environment"
        exit /b 1
    )
) else (
    call :log_info "Virtual environment already exists: %VENV_DIR%"
)

REM Activate virtual environment
if exist "%VENV_DIR%\Scripts\activate.bat" (
    call "%VENV_DIR%\Scripts\activate.bat"
) else (
    call :log_error "Virtual environment activation script not found"
    exit /b 1
)

REM Upgrade pip
call :log_info "Upgrading pip..."
"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip -q
if errorlevel 1 (
    call :log_warn "Failed to upgrade pip, continuing..."
)

REM Install dependencies
if exist "%REQUIREMENTS_FILE%" (
    call :log_info "Installing Python dependencies..."
    "%VENV_DIR%\Scripts\pip.exe" install -r "%REQUIREMENTS_FILE%"
    if errorlevel 1 (
        call :log_error "Failed to install Python dependencies"
        exit /b 1
    )
    call :log_success "Python dependencies installed"
) else (
    call :log_warn "requirements.txt not found"
)

REM Show installed packages
call :log_info "Installed main packages:"
"%VENV_DIR%\Scripts\pip.exe" list | findstr /i "fastapi uvicorn oracledb httpx prometheus"

exit /b 0

REM ============================================================================
REM Setup Configuration
REM ============================================================================
:setup_config
call :log_step "Setting up configuration..."

REM Create logs directory
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM Check existing config
if exist "%ENV_FILE%" (
    call :log_info "Found existing configuration: %ENV_FILE%"
    call :confirm "Reconfigure? (will backup existing)"
    if not "!CONFIRM_RESULT!"=="yes" (
        call :log_info "Skipping configuration, using existing file"
        goto :eof
    )
    REM Backup existing config
    for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set "datetime=%%I"
    set "backup_file=%ENV_FILE%.backup.!datetime:~0,8!_!datetime:~8,6!"
    copy "%ENV_FILE%" "!backup_file!" >nul
    call :log_info "Backed up to: !backup_file!"
)

REM Copy template or create default
if exist "%ENV_EXAMPLE%" (
    copy "%ENV_EXAMPLE%" "%ENV_FILE%" >nul
) else (
    call :create_default_env
)

REM Interactive configuration
call :configure_interactively

call :log_success "Configuration saved: %ENV_FILE%"
goto :eof

REM ============================================================================
REM Create Default Environment Configuration
REM ============================================================================
:create_default_env
(
echo # ZMC Alarm Exporter Environment Configuration
echo # Auto-generated by install.bat
echo.
echo # ========== Application Config ==========
echo DEBUG=false
echo.
echo # ========== Oracle Database Config ==========
echo ZMC_ORACLE_HOST=localhost
echo ZMC_ORACLE_PORT=1521
echo ZMC_ORACLE_SERVICE_NAME=ORCL
echo ZMC_ORACLE_USERNAME=zmc
echo ZMC_ORACLE_PASSWORD=password
echo ZMC_ORACLE_POOL_MIN=2
echo ZMC_ORACLE_POOL_MAX=10
echo ZMC_ORACLE_TIMEOUT=30
echo.
echo # ========== Alertmanager Config ==========
echo ALERTMANAGER_URL=http://localhost:9093
echo ALERTMANAGER_API_VERSION=v2
echo ALERTMANAGER_AUTH_ENABLED=false
echo ALERTMANAGER_TIMEOUT=30
echo ALERTMANAGER_RETRY_COUNT=3
echo ALERTMANAGER_RETRY_INTERVAL=1000
echo.
echo # ========== Sync Service Config ==========
echo SYNC_ENABLED=true
echo SYNC_SCAN_INTERVAL=60
echo SYNC_HEARTBEAT_ENABLED=false
echo SYNC_HEARTBEAT_INTERVAL=120
echo SYNC_BATCH_SIZE=100
echo SYNC_SYNC_ON_STARTUP=true
echo SYNC_HISTORY_HOURS=24
echo SYNC_ALARM_LEVELS=1,2,3,4
echo.
echo # ========== Logging Config ==========
echo LOG_LEVEL=INFO
echo LOG_FORMAT=json
echo.
echo # ========== Server Config ==========
echo SERVER_HOST=0.0.0.0
echo SERVER_PORT=8080
echo SERVER_WORKERS=1
) > "%ENV_FILE%"
goto :eof

REM ============================================================================
REM Interactive Configuration
REM ============================================================================
:configure_interactively
echo.
call :log_info "Please configure the following parameters (press Enter for default):"
echo.

REM Oracle configuration
echo === Oracle Database Configuration ===

set /p "oracle_host=Oracle Host [10.101.1.42]: "
if "!oracle_host!"=="" set "oracle_host=10.101.1.42"

set /p "oracle_port=Oracle Port [1522]: "
if "!oracle_port!"=="" set "oracle_port=1522"

set /p "oracle_service=Oracle Service Name [rb]: "
if "!oracle_service!"=="" set "oracle_service=rb"

set /p "oracle_user=Oracle Username [zmc]: "
if "!oracle_user!"=="" set "oracle_user=zmc"

set /p "oracle_pass=Oracle Password [smart]: "
if "!oracle_pass!"=="" set "oracle_pass=smart"

REM Alertmanager configuration
echo.
echo === Alertmanager Configuration ===

set /p "am_url=Alertmanager URL [http://localhost:9093]: "
if "!am_url!"=="" set "am_url=http://localhost:9093"

REM Server configuration
echo.
echo === Server Configuration ===

set /p "server_port=Server Port [8080]: "
if "!server_port!"=="" set "server_port=8080"

REM Update configuration file using PowerShell for reliable replacement
powershell -Command "(Get-Content '%ENV_FILE%') -replace '^ZMC_ORACLE_HOST=.*', 'ZMC_ORACLE_HOST=!oracle_host!' | Set-Content '%ENV_FILE%'"
powershell -Command "(Get-Content '%ENV_FILE%') -replace '^ZMC_ORACLE_PORT=.*', 'ZMC_ORACLE_PORT=!oracle_port!' | Set-Content '%ENV_FILE%'"
powershell -Command "(Get-Content '%ENV_FILE%') -replace '^ZMC_ORACLE_SERVICE_NAME=.*', 'ZMC_ORACLE_SERVICE_NAME=!oracle_service!' | Set-Content '%ENV_FILE%'"
powershell -Command "(Get-Content '%ENV_FILE%') -replace '^ZMC_ORACLE_USERNAME=.*', 'ZMC_ORACLE_USERNAME=!oracle_user!' | Set-Content '%ENV_FILE%'"
powershell -Command "(Get-Content '%ENV_FILE%') -replace '^ZMC_ORACLE_PASSWORD=.*', 'ZMC_ORACLE_PASSWORD=!oracle_pass!' | Set-Content '%ENV_FILE%'"
powershell -Command "(Get-Content '%ENV_FILE%') -replace '^ALERTMANAGER_URL=.*', 'ALERTMANAGER_URL=!am_url!' | Set-Content '%ENV_FILE%'"
powershell -Command "(Get-Content '%ENV_FILE%') -replace '^SERVER_PORT=.*', 'SERVER_PORT=!server_port!' | Set-Content '%ENV_FILE%'"

echo.
call :log_info "Configuration saved to %ENV_FILE%"
goto :eof

REM ============================================================================
REM Initialize Database
REM ============================================================================
:init_database
call :log_step "Initializing database..."

if not exist "%SQL_INIT_FILE%" (
    call :log_error "Database initialization script not found: %SQL_INIT_FILE%"
    exit /b 1
)

REM Load environment variables
if exist "%ENV_FILE%" (
    for /f "usebackq tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
        set "%%A=%%B"
    )
)

if not defined ZMC_ORACLE_HOST set "ZMC_ORACLE_HOST=localhost"
if not defined ZMC_ORACLE_PORT set "ZMC_ORACLE_PORT=1521"
if not defined ZMC_ORACLE_SERVICE_NAME set "ZMC_ORACLE_SERVICE_NAME=ORCL"
if not defined ZMC_ORACLE_USERNAME set "ZMC_ORACLE_USERNAME=zmc"
if not defined ZMC_ORACLE_PASSWORD set "ZMC_ORACLE_PASSWORD=password"

call :log_info "Database connection info:"
echo   Host: %ZMC_ORACLE_HOST%:%ZMC_ORACLE_PORT%
echo   Service: %ZMC_ORACLE_SERVICE_NAME%
echo   User: %ZMC_ORACLE_USERNAME%
echo.

REM Check if sqlplus is available
where sqlplus >nul 2>&1
if not errorlevel 1 (
    call :confirm "Execute database initialization? (will create new tables)"
    if "!CONFIRM_RESULT!"=="yes" (
        call :log_info "Using sqlplus to initialize database..."
        echo EXIT; | type "%SQL_INIT_FILE%" - | sqlplus -S "%ZMC_ORACLE_USERNAME%/%ZMC_ORACLE_PASSWORD%@%ZMC_ORACLE_HOST%:%ZMC_ORACLE_PORT%/%ZMC_ORACLE_SERVICE_NAME%"
        call :log_success "Database initialization completed"
    ) else (
        call :log_info "Skipping database initialization"
    )
) else if exist "%VENV_DIR%\Scripts\python.exe" (
    REM Use Python oracledb
    call :confirm "Execute database initialization using Python? (will create new tables)"
    if "!CONFIRM_RESULT!"=="yes" (
        call :log_info "Using Python oracledb to initialize database..."
        "%VENV_DIR%\Scripts\python.exe" -c "
import oracledb
import sys

try:
    dsn = '%ZMC_ORACLE_HOST%:%ZMC_ORACLE_PORT%/%ZMC_ORACLE_SERVICE_NAME%'
    print(f'Connecting to: {dsn}')

    conn = oracledb.connect(
        user='%ZMC_ORACLE_USERNAME%',
        password='%ZMC_ORACLE_PASSWORD%',
        dsn=dsn
    )

    cursor = conn.cursor()

    with open('%SQL_INIT_FILE%', 'r') as f:
        sql_content = f.read()

    # Split and execute SQL statements
    statements = []
    current_stmt = ''

    for line in sql_content.split('\n'):
        stripped = line.strip()
        current_stmt += line + '\n'

        if stripped.endswith(';'):
            statements.append(current_stmt.rstrip(';\n'))
            current_stmt = ''

    success_count = 0
    error_count = 0
    skip_count = 0

    for stmt in statements:
        stmt = stmt.strip()
        if not stmt or stmt.startswith('--'):
            continue
        if stmt.upper().startswith('COMMENT') or stmt.upper() == 'COMMIT':
            continue

        try:
            cursor.execute(stmt)
            success_count += 1
        except oracledb.DatabaseError as e:
            error_obj, = e.args
            if error_obj.code in [955, 2261, 2264, 1430, 1408, 942, 1418]:
                skip_count += 1
            else:
                print(f'  [Error] {error_obj.message}')
                error_count += 1

    conn.commit()
    cursor.close()
    conn.close()

    print(f'\nCompleted: {success_count} success, {skip_count} skipped (already exists), {error_count} errors')

except Exception as e:
    print(f'Database connection failed: {e}')
    sys.exit(1)
"
        if errorlevel 1 (
            call :log_error "Database initialization failed"
        ) else (
            call :log_success "Database initialization completed"
        )
    ) else (
        call :log_info "Skipping database initialization"
    )
) else (
    call :log_warn "Neither sqlplus nor Python environment available"
    call :log_info "Please manually execute the following SQL script:"
    echo.
    echo   sqlplus %ZMC_ORACLE_USERNAME%/%ZMC_ORACLE_PASSWORD%@%ZMC_ORACLE_HOST%:%ZMC_ORACLE_PORT%/%ZMC_ORACLE_SERVICE_NAME% @%SQL_INIT_FILE%
    echo.
)

goto :eof

REM ============================================================================
REM Start Service
REM ============================================================================
:start_service
call :log_step "Starting service..."

REM Check if start.bat exists
if exist "%SCRIPT_DIR%\start.bat" (
    call "%SCRIPT_DIR%\start.bat" start
    goto :eof
)

REM Direct start
if exist "%VENV_DIR%\Scripts\activate.bat" (
    call "%VENV_DIR%\Scripts\activate.bat"
)

cd /d "%SCRIPT_DIR%"

REM Load environment variables
if exist "%ENV_FILE%" (
    for /f "usebackq tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
        set "%%A=%%B"
    )
)

if not defined SERVER_HOST set "SERVER_HOST=0.0.0.0"
if not defined SERVER_PORT set "SERVER_PORT=8080"

call :log_info "Starting uvicorn server on %SERVER_HOST%:%SERVER_PORT%..."

start "ZMC Alarm Exporter" /b "%VENV_DIR%\Scripts\python.exe" -m uvicorn app.main:app --host %SERVER_HOST% --port %SERVER_PORT%

timeout /t 3 /nobreak >nul

call :log_success "Service started"
call :log_info "API endpoint: http://%SERVER_HOST%:%SERVER_PORT%"
call :log_info "Health check: http://%SERVER_HOST%:%SERVER_PORT%/health"

goto :eof

REM ============================================================================
REM Verify Installation
REM ============================================================================
:verify_installation
call :log_step "Verifying installation..."

if not defined SERVER_PORT set "SERVER_PORT=8080"

set "max_attempts=10"
set "attempt=0"

call :log_info "Waiting for service to start..."

:verify_loop
if %attempt% geq %max_attempts% goto verify_failed

powershell -Command "try { $response = Invoke-WebRequest -Uri 'http://localhost:%SERVER_PORT%/health' -UseBasicParsing -TimeoutSec 2; exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto verify_success

set /a "attempt+=1"
timeout /t 1 /nobreak >nul
goto verify_loop

:verify_success
call :log_success "Service health check passed"
echo.
powershell -Command "Invoke-WebRequest -Uri 'http://localhost:%SERVER_PORT%/health' -UseBasicParsing | Select-Object -ExpandProperty Content"
echo.
goto :eof

:verify_failed
call :log_warn "Cannot connect to service, please check logs"
goto :eof

REM ============================================================================
REM Uninstall
REM ============================================================================
:uninstall
call :log_step "Uninstalling %APP_NAME%..."

call :confirm "Confirm uninstall? This will stop service and delete virtual environment"
if not "!CONFIRM_RESULT!"=="yes" goto :eof

REM Stop service
if exist "%SCRIPT_DIR%\start.bat" (
    call "%SCRIPT_DIR%\start.bat" stop 2>nul
)

REM Kill any running Python processes for this app
taskkill /f /im python.exe /fi "WINDOWTITLE eq ZMC Alarm Exporter" >nul 2>&1

REM Delete virtual environment
if exist "%VENV_DIR%" (
    call :confirm "Delete virtual environment?"
    if "!CONFIRM_RESULT!"=="yes" (
        rmdir /s /q "%VENV_DIR%"
        call :log_info "Deleted virtual environment"
    )
)

REM Delete logs
if exist "%LOG_DIR%" (
    call :confirm "Delete logs directory?"
    if "!CONFIRM_RESULT!"=="yes" (
        rmdir /s /q "%LOG_DIR%"
        call :log_info "Deleted logs directory"
    )
)

call :log_success "Uninstall completed"
goto :eof

REM ============================================================================
REM Show Help
REM ============================================================================
:show_help
echo.
echo ZMC Alarm Exporter - Windows Installation Script
echo.
echo Usage:
echo     install.bat [options]
echo.
echo Options:
echo     --skip-db       Skip database initialization
echo     --skip-deps     Skip dependency installation
echo     --uninstall     Uninstall service
echo     -y, --yes       Auto confirm all prompts
echo     -h, --help      Show this help message
echo.
echo Examples:
echo     install.bat                 # Full installation (interactive)
echo     install.bat -y              # Full installation (auto confirm)
echo     install.bat --skip-db       # Install but skip database initialization
echo     install.bat --uninstall     # Uninstall service
echo.
echo Installation Flow:
echo     1. Check Python 3.10+
echo     2. Create virtual environment and install dependencies
echo     3. Configure environment variables (.env)
echo     4. Initialize Oracle database (optional)
echo     5. Start service and verify
echo.
goto end

REM ============================================================================
REM Show Summary
REM ============================================================================
:show_summary
echo.
echo =====================================================
echo          Installation Complete!
echo =====================================================
echo.
echo Service Info:
echo   API URL:        http://localhost:%SERVER_PORT%
echo   Health Check:   http://localhost:%SERVER_PORT%/health
echo   API Docs:       http://localhost:%SERVER_PORT%/docs
echo   Metrics:        http://localhost:%SERVER_PORT%/metrics
echo.
echo Common Commands:
echo   Start service:  start.bat start
echo   Stop service:   start.bat stop
echo   Check status:   start.bat status
echo   View logs:      start.bat logs
echo.
echo Configuration Files:
echo   Environment:    %ENV_FILE%
echo   Logs:           %LOG_DIR%
echo.
echo Important Notes:
echo   1. Configure ALERTMANAGER_URL in .env to point to external Alertmanager
echo   2. Ensure Oracle database is accessible
echo   3. Ensure this service can access Alertmanager (network/firewall)
echo.
goto :eof

REM ============================================================================
REM Exit Handlers
REM ============================================================================
:error_exit
echo.
call :log_error "Installation failed!"
exit /b 1

:end
endlocal
exit /b 0
