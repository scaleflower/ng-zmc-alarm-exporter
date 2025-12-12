@echo off
REM ============================================================================
REM ZMC Alarm Exporter - Windows Startup Script
REM
REM Usage:
REM   start.bat <command>
REM
REM Commands:
REM   start         Start the service
REM   stop          Stop the service
REM   restart       Restart the service
REM   status        Show service status
REM   logs          Show recent logs
REM   install       Install dependencies
REM   update        Pull latest code and restart (Direct Run)
REM   update-docker Pull latest code and rebuild Docker
REM   help          Show help message
REM ============================================================================

setlocal enabledelayedexpansion

REM ============================================================================
REM Configuration Variables
REM ============================================================================
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "APP_NAME=zmc-alarm-exporter"
set "VENV_DIR=%SCRIPT_DIR%\venv"
set "LOG_DIR=%SCRIPT_DIR%\logs"
set "LOG_FILE=%LOG_DIR%\%APP_NAME%.log"
set "PID_FILE=%LOG_DIR%\%APP_NAME%.pid"
set "ENV_FILE=%SCRIPT_DIR%\.env"

REM Default server configuration (can be overridden by .env)
set "SERVER_HOST=0.0.0.0"
set "SERVER_PORT=8080"
set "SERVER_WORKERS=1"

REM ============================================================================
REM Load Environment Variables
REM ============================================================================
if exist "%ENV_FILE%" (
    for /f "usebackq tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
        REM Skip comments and empty lines
        set "line=%%A"
        if not "!line:~0,1!"=="#" (
            if not "%%A"=="" set "%%A=%%B"
        )
    )
)

REM ============================================================================
REM Main Entry
REM ============================================================================
if "%~1"=="" goto usage
if /i "%~1"=="start" goto start_service
if /i "%~1"=="stop" goto stop_service
if /i "%~1"=="restart" goto restart_service
if /i "%~1"=="status" goto show_status
if /i "%~1"=="logs" goto show_logs
if /i "%~1"=="install" goto install_deps
if /i "%~1"=="update" goto update_service
if /i "%~1"=="update-docker" goto update_docker
if /i "%~1"=="help" goto usage
if /i "%~1"=="--help" goto usage
if /i "%~1"=="-h" goto usage

echo [ERROR] Unknown command: %~1
goto usage

REM ============================================================================
REM Start Service
REM ============================================================================
:start_service
echo [%date% %time%] [INFO] Starting %APP_NAME%...

REM Check if already running
call :check_running
if "%IS_RUNNING%"=="true" (
    echo [WARN] Service is already running
    goto end
)

REM Create logs directory
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM Check Python virtual environment
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found: %VENV_DIR%
    echo [INFO] Please run 'install.bat' first to setup the environment
    goto error_exit
)

REM Activate virtual environment and start service
cd /d "%SCRIPT_DIR%"

echo [INFO] Starting uvicorn server on %SERVER_HOST%:%SERVER_PORT%...

REM Start in background
start "%APP_NAME%" /b cmd /c ""%VENV_DIR%\Scripts\python.exe" -m uvicorn app.main:app --host %SERVER_HOST% --port %SERVER_PORT% --workers %SERVER_WORKERS% >> "%LOG_FILE%" 2>&1"

REM Wait for startup
timeout /t 3 /nobreak >nul

REM Check if started successfully
call :check_running
if "%IS_RUNNING%"=="true" (
    echo [INFO] Service started successfully
    echo [INFO] Log file: %LOG_FILE%
    echo [INFO] API endpoint: http://%SERVER_HOST%:%SERVER_PORT%
    echo [INFO] Health check: http://%SERVER_HOST%:%SERVER_PORT%/health
) else (
    echo [ERROR] Failed to start service. Check log file: %LOG_FILE%
    goto error_exit
)
goto end

REM ============================================================================
REM Stop Service
REM ============================================================================
:stop_service
echo [%date% %time%] [INFO] Stopping %APP_NAME%...

call :check_running
if "%IS_RUNNING%"=="false" (
    echo [WARN] Service is not running
    goto end
)

REM Find and kill uvicorn processes
for /f "tokens=2" %%P in ('tasklist /fi "WINDOWTITLE eq %APP_NAME%" /fo list ^| findstr "PID:"') do (
    echo [INFO] Killing process PID: %%P
    taskkill /f /pid %%P >nul 2>&1
)

REM Also try to find python processes running uvicorn on our port
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%SERVER_PORT% " ^| findstr "LISTENING"') do (
    taskkill /f /pid %%P >nul 2>&1
)

timeout /t 2 /nobreak >nul

call :check_running
if "%IS_RUNNING%"=="false" (
    echo [INFO] Service stopped
) else (
    echo [WARN] Service may still be running, please check manually
)
goto end

REM ============================================================================
REM Restart Service
REM ============================================================================
:restart_service
echo [%date% %time%] [INFO] Restarting %APP_NAME%...
call :stop_service
timeout /t 2 /nobreak >nul
call :start_service
goto end

REM ============================================================================
REM Show Status
REM ============================================================================
:show_status
call :check_running
if "%IS_RUNNING%"=="true" (
    echo [INFO] Service is running
    echo.
    echo Process details:
    for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%SERVER_PORT% " ^| findstr "LISTENING"') do (
        tasklist /fi "PID eq %%P" /fo table
    )
    echo.
    echo Health check:
    powershell -Command "try { $response = Invoke-WebRequest -Uri 'http://localhost:%SERVER_PORT%/health' -UseBasicParsing -TimeoutSec 5; $response.Content | ConvertFrom-Json | ConvertTo-Json } catch { Write-Host 'Unable to fetch health status' }"
) else (
    echo [INFO] Service is not running
)
goto end

REM ============================================================================
REM Show Logs
REM ============================================================================
:show_logs
set "lines=100"
if not "%~2"=="" set "lines=%~2"

if exist "%LOG_FILE%" (
    echo [INFO] Showing last %lines% lines of %LOG_FILE%
    echo ============================================================
    powershell -Command "Get-Content '%LOG_FILE%' -Tail %lines%"
) else (
    echo [WARN] Log file not found: %LOG_FILE%
)
goto end

REM ============================================================================
REM Install Dependencies
REM ============================================================================
:install_deps
echo [%date% %time%] [INFO] Installing %APP_NAME%...

REM Check Python
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+
    goto error_exit
)

REM Create virtual environment
if not exist "%VENV_DIR%" (
    echo [INFO] Creating virtual environment...
    python -m venv "%VENV_DIR%"
)

REM Activate and install dependencies
echo [INFO] Installing dependencies...
call "%VENV_DIR%\Scripts\activate.bat"
pip install -q -r "%SCRIPT_DIR%\requirements.txt"

REM Create logs directory
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM Copy env example if needed
if not exist "%ENV_FILE%" (
    if exist "%SCRIPT_DIR%\.env.example" (
        copy "%SCRIPT_DIR%\.env.example" "%ENV_FILE%" >nul
        echo [INFO] Created %ENV_FILE% from template. Please edit it with your configuration.
    )
)

echo [INFO] Installation completed!
echo.
echo Next steps:
echo   1. Edit %ENV_FILE% with your Oracle and Alertmanager settings
echo   2. Initialize database: sqlplus zmc/password@db @sql\init_sync_tables.sql
echo   3. Start service: %~nx0 start
goto end

REM ============================================================================
REM Update Service (Direct Run)
REM ============================================================================
:update_service
echo [%date% %time%] [INFO] Updating %APP_NAME%...

cd /d "%SCRIPT_DIR%"

REM Check if git repository
if not exist ".git" (
    echo [ERROR] Not a git repository. Cannot update.
    goto error_exit
)

REM Check for uncommitted changes
git diff-index --quiet HEAD -- 2>nul
if errorlevel 1 (
    echo [WARN] You have uncommitted changes. Please commit or stash them first.
    git status --short
    goto error_exit
)

REM Pull latest code
echo [INFO] Pulling latest code from remote...
git pull origin main
if errorlevel 1 (
    echo [ERROR] Failed to pull latest code
    goto error_exit
)

REM Check if requirements.txt changed
git diff HEAD@{1} --name-only 2>nul | findstr "requirements.txt" >nul 2>&1
if not errorlevel 1 (
    echo [INFO] requirements.txt changed, updating dependencies...
    call :install_deps
)

REM Restart service
echo [INFO] Restarting service...
call :restart_service

echo [INFO] Update completed!
echo [INFO] Run '%~nx0 logs' to check the logs
goto end

REM ============================================================================
REM Update Service (Docker)
REM ============================================================================
:update_docker
echo [%date% %time%] [INFO] Updating %APP_NAME% (Docker mode)...

cd /d "%SCRIPT_DIR%"

REM Check if git repository
if not exist ".git" (
    echo [ERROR] Not a git repository. Cannot update.
    goto error_exit
)

REM Check for docker-compose
where docker-compose >nul 2>&1
if errorlevel 1 (
    docker compose version >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] docker-compose not found. Please install Docker Compose.
        goto error_exit
    )
    set "COMPOSE_CMD=docker compose"
) else (
    set "COMPOSE_CMD=docker-compose"
)

REM Check for uncommitted changes
git diff-index --quiet HEAD -- 2>nul
if errorlevel 1 (
    echo [WARN] You have uncommitted changes. Please commit or stash them first.
    git status --short
    goto error_exit
)

REM Pull latest code
echo [INFO] Pulling latest code from remote...
git pull origin main
if errorlevel 1 (
    echo [ERROR] Failed to pull latest code
    goto error_exit
)

REM Stop containers
echo [INFO] Stopping containers...
%COMPOSE_CMD% down

REM Rebuild containers
echo [INFO] Rebuilding containers...
%COMPOSE_CMD% build
if errorlevel 1 (
    echo [ERROR] Failed to build containers
    goto error_exit
)

REM Start containers
echo [INFO] Starting containers...
%COMPOSE_CMD% up -d

echo [INFO] Update completed!
echo [INFO] Run '%COMPOSE_CMD% logs -f' to check the logs
goto end

REM ============================================================================
REM Check if Service is Running
REM ============================================================================
:check_running
set "IS_RUNNING=false"

REM Check if port is in use
netstat -ano | findstr ":%SERVER_PORT% " | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 set "IS_RUNNING=true"

goto :eof

REM ============================================================================
REM Usage
REM ============================================================================
:usage
echo.
echo Usage: %~nx0 ^<command^> [options]
echo.
echo ZMC Alarm Exporter - Sync ZMC alarms to Prometheus Alertmanager
echo.
echo Commands:
echo     start         Start the service
echo     stop          Stop the service
echo     restart       Restart the service
echo     status        Show service status and health
echo     logs [n]      Show last n lines of log (default: 100)
echo     install       Install dependencies and setup environment
echo     update        Pull latest code and restart service (Direct Run)
echo     update-docker Pull latest code and rebuild Docker containers
echo     help          Show this help message
echo.
echo Examples:
echo     %~nx0 start              # Start the service
echo     %~nx0 stop               # Stop the service
echo     %~nx0 restart            # Restart the service
echo     %~nx0 status             # Check service status
echo     %~nx0 logs 200           # Show last 200 lines of log
echo     %~nx0 update             # Update to latest version (Direct Run)
echo     %~nx0 update-docker      # Update to latest version (Docker)
echo.
echo Environment Variables (set in .env):
echo     SERVER_HOST     Listen address (default: 0.0.0.0)
echo     SERVER_PORT     Listen port (default: 8080)
echo     SERVER_WORKERS  Number of worker processes (default: 1)
echo.
echo Files:
echo     Log file:     %LOG_FILE%
echo     Config file:  %ENV_FILE%
echo.
goto end

REM ============================================================================
REM Exit Handlers
REM ============================================================================
:error_exit
endlocal
exit /b 1

:end
endlocal
exit /b 0
