# ZMC Alarm Exporter Installation Guide

Multi-platform installation guide for ZMC Alarm Exporter - a service that syncs ZMC alarms to Prometheus Alertmanager.

## Table of Contents

- [System Requirements](#system-requirements)
- [Quick Start](#quick-start)
- [Installation by Platform](#installation-by-platform)
  - [Linux](#linux)
  - [macOS](#macos)
  - [Windows](#windows)
- [Docker Deployment](#docker-deployment)
- [Configuration](#configuration)
- [Service Management](#service-management)
- [Database Initialization](#database-initialization)
- [Verification](#verification)
- [Troubleshooting](#troubleshooting)

---

## System Requirements

### Minimum Requirements

| Component | Requirement |
|-----------|-------------|
| Python | 3.10 or higher |
| Memory | 512 MB RAM |
| Disk | 500 MB free space |
| Network | Access to Oracle DB and Alertmanager |

### Dependencies

- Oracle Database (ZMC database)
- Prometheus Alertmanager
- Oracle Instant Client (optional, for thick mode)

---

## Quick Start

### One-Line Installation

**Linux/macOS:**
```bash
git clone https://github.com/scaleflower/ng-zmc-alarm-exporter.git
cd ng-zmc-alarm-exporter
./install.sh
```

**Windows:**
```cmd
git clone https://github.com/scaleflower/ng-zmc-alarm-exporter.git
cd ng-zmc-alarm-exporter
install.bat
```

**Docker:**
```bash
docker run -d \
  --name zmc-alarm-exporter \
  -p 8080:8080 \
  -e ZMC_ORACLE_HOST=your-oracle-host \
  -e ZMC_ORACLE_PORT=1521 \
  -e ZMC_ORACLE_SERVICE_NAME=ORCL \
  -e ZMC_ORACLE_USERNAME=zmc \
  -e ZMC_ORACLE_PASSWORD=your-password \
  -e ALERTMANAGER_URL=http://your-alertmanager:9093 \
  kourenicz/zmc-alarm-exporter:latest
```

---

## Installation by Platform

### Linux

#### Prerequisites

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git curl

# CentOS/RHEL/Rocky
sudo yum install -y python3 python3-pip git curl
# or
sudo dnf install -y python3 python3-pip git curl
```

#### Installation Steps

1. **Clone the repository:**
   ```bash
   git clone https://github.com/scaleflower/ng-zmc-alarm-exporter.git
   cd ng-zmc-alarm-exporter
   ```

2. **Run the installer:**
   ```bash
   chmod +x install.sh
   ./install.sh
   ```

   The installer will:
   - Check Python version
   - Create virtual environment
   - Install dependencies
   - Configure environment variables interactively
   - Initialize database (optional)
   - Start the service

3. **Or manual installation:**
   ```bash
   # Create virtual environment
   python3 -m venv venv
   source venv/bin/activate

   # Install dependencies
   pip install -r requirements.txt

   # Copy and edit configuration
   cp .env.example .env
   nano .env

   # Start service
   ./start.sh start
   ```

#### Systemd Service (Optional)

```bash
# Copy service file
sudo cp bin/zmc-alarm-exporter.service /etc/systemd/system/

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable zmc-alarm-exporter
sudo systemctl start zmc-alarm-exporter

# Check status
sudo systemctl status zmc-alarm-exporter
```

---

### macOS

#### Prerequisites

```bash
# Install Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python
brew install python@3.11
```

#### Installation Steps

1. **Clone the repository:**
   ```bash
   git clone https://github.com/scaleflower/ng-zmc-alarm-exporter.git
   cd ng-zmc-alarm-exporter
   ```

2. **Run the installer:**
   ```bash
   chmod +x install.sh
   ./install.sh
   ```

3. **Or manual installation:**
   ```bash
   # Create virtual environment
   python3 -m venv venv
   source venv/bin/activate

   # Install dependencies
   pip install -r requirements.txt

   # Copy and edit configuration
   cp .env.example .env
   open -e .env

   # Start service
   ./start.sh start
   ```

#### LaunchAgent Service (Optional)

Create `~/Library/LaunchAgents/com.zmc.alarm-exporter.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.zmc.alarm-exporter</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/ng-zmc-alarm-exporter/start.sh</string>
        <string>start</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>/path/to/ng-zmc-alarm-exporter</string>
</dict>
</plist>
```

Load the service:
```bash
launchctl load ~/Library/LaunchAgents/com.zmc.alarm-exporter.plist
```

---

### Windows

#### Prerequisites

1. **Install Python 3.10+:**
   - Download from [python.org](https://www.python.org/downloads/)
   - **Important:** Check "Add Python to PATH" during installation

2. **Install Git (Optional):**
   - Download from [git-scm.com](https://git-scm.com/download/win)

#### Installation Steps

1. **Download or clone the repository:**
   ```cmd
   git clone https://github.com/scaleflower/ng-zmc-alarm-exporter.git
   cd ng-zmc-alarm-exporter
   ```

   Or download and extract from GitHub releases.

2. **Run the installer:**
   ```cmd
   install.bat
   ```

   The installer will:
   - Check Python version
   - Create virtual environment
   - Install dependencies
   - Configure environment variables interactively
   - Initialize database (optional)
   - Start the service

3. **Or manual installation:**
   ```cmd
   REM Create virtual environment
   python -m venv venv
   venv\Scripts\activate

   REM Install dependencies
   pip install -r requirements.txt

   REM Copy and edit configuration
   copy .env.example .env
   notepad .env

   REM Start service
   start.bat start
   ```

#### Windows Service (Optional)

Using [NSSM](https://nssm.cc/) (Non-Sucking Service Manager):

```cmd
REM Download nssm from https://nssm.cc/download
nssm install ZMCAlarmExporter "C:\path\to\ng-zmc-alarm-exporter\venv\Scripts\python.exe"
nssm set ZMCAlarmExporter AppParameters "-m uvicorn app.main:app --host 0.0.0.0 --port 8080"
nssm set ZMCAlarmExporter AppDirectory "C:\path\to\ng-zmc-alarm-exporter"
nssm set ZMCAlarmExporter AppEnvironmentExtra "PATH=C:\path\to\ng-zmc-alarm-exporter\venv\Scripts"
nssm start ZMCAlarmExporter
```

---

## Docker Deployment

### Using Pre-built Image

```bash
# Pull image
docker pull kourenicz/zmc-alarm-exporter:latest

# Run with environment variables
docker run -d \
  --name zmc-alarm-exporter \
  -p 8080:8080 \
  -e ZMC_ORACLE_HOST=10.101.1.42 \
  -e ZMC_ORACLE_PORT=1522 \
  -e ZMC_ORACLE_SERVICE_NAME=rb \
  -e ZMC_ORACLE_USERNAME=zmc \
  -e ZMC_ORACLE_PASSWORD=smart \
  -e ALERTMANAGER_URL=http://10.101.1.79:9093 \
  -e SYNC_ENABLED=true \
  -e SYNC_SCAN_INTERVAL=60 \
  kourenicz/zmc-alarm-exporter:latest

# Or use .env file
docker run -d \
  --name zmc-alarm-exporter \
  -p 8080:8080 \
  --env-file .env \
  kourenicz/zmc-alarm-exporter:latest
```

### Using Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  zmc-alarm-exporter:
    image: kourenicz/zmc-alarm-exporter:latest
    container_name: zmc-alarm-exporter
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      # Oracle Database
      ZMC_ORACLE_HOST: 10.101.1.42
      ZMC_ORACLE_PORT: 1522
      ZMC_ORACLE_SERVICE_NAME: rb
      ZMC_ORACLE_USERNAME: zmc
      ZMC_ORACLE_PASSWORD: smart

      # Alertmanager
      ALERTMANAGER_URL: http://alertmanager:9093

      # Sync Settings
      SYNC_ENABLED: "true"
      SYNC_SCAN_INTERVAL: 60
      SYNC_HEARTBEAT_ENABLED: "false"
      SYNC_ALARM_LEVELS: "1,2,3,4"

      # Logging
      LOG_LEVEL: INFO
    volumes:
      - ./logs:/app/logs
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

Run:
```bash
docker-compose up -d
```

### Building Image Locally

```bash
# Build
docker build -t zmc-alarm-exporter:latest .

# Run
docker run -d -p 8080:8080 --env-file .env zmc-alarm-exporter:latest
```

---

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and edit:

```bash
cp .env.example .env
```

### Key Configuration Options

| Variable | Description | Default |
|----------|-------------|---------|
| **Oracle Database** | | |
| `ZMC_ORACLE_HOST` | Oracle host address | localhost |
| `ZMC_ORACLE_PORT` | Oracle port | 1521 |
| `ZMC_ORACLE_SERVICE_NAME` | Oracle service name | ORCL |
| `ZMC_ORACLE_USERNAME` | Database username | zmc |
| `ZMC_ORACLE_PASSWORD` | Database password | - |
| **Alertmanager** | | |
| `ALERTMANAGER_URL` | Alertmanager API URL | http://localhost:9093 |
| `ALERTMANAGER_TIMEOUT` | Request timeout (seconds) | 30 |
| **Sync Service** | | |
| `SYNC_ENABLED` | Enable sync service | true |
| `SYNC_SCAN_INTERVAL` | Scan interval (seconds) | 60 |
| `SYNC_HEARTBEAT_ENABLED` | Enable heartbeat (re-push active alarms) | false |
| `SYNC_ALARM_LEVELS` | Alarm levels to sync (1=Critical, 2=Major, 3=Minor, 4=Warning) | 1,2,3,4 |
| **Server** | | |
| `SERVER_HOST` | Listen address | 0.0.0.0 |
| `SERVER_PORT` | Listen port | 8080 |
| **Logging** | | |
| `LOG_LEVEL` | Log level (DEBUG/INFO/WARNING/ERROR) | INFO |

### Example Configuration

```env
# Oracle Database
ZMC_ORACLE_HOST=10.101.1.42
ZMC_ORACLE_PORT=1522
ZMC_ORACLE_SERVICE_NAME=rb
ZMC_ORACLE_USERNAME=zmc
ZMC_ORACLE_PASSWORD=smart

# Alertmanager
ALERTMANAGER_URL=http://10.101.1.79:9093

# Sync Service
SYNC_ENABLED=true
SYNC_SCAN_INTERVAL=60
SYNC_HEARTBEAT_ENABLED=false
SYNC_ALARM_LEVELS=1,2,3

# Server
SERVER_HOST=0.0.0.0
SERVER_PORT=8080

# Logging
LOG_LEVEL=INFO
```

---

## Service Management

### Linux/macOS

```bash
# Start
./start.sh start

# Stop
./start.sh stop

# Restart
./start.sh restart

# Status
./start.sh status

# View logs
./start.sh logs        # Last 100 lines
./start.sh logs 200    # Last 200 lines
./start.sh logs-f      # Follow logs
```

### Windows

```cmd
REM Start
start.bat start

REM Stop
start.bat stop

REM Restart
start.bat restart

REM Status
start.bat status

REM View logs
start.bat logs
start.bat logs 200
```

### Docker

```bash
# Start
docker start zmc-alarm-exporter

# Stop
docker stop zmc-alarm-exporter

# Restart
docker restart zmc-alarm-exporter

# View logs
docker logs -f zmc-alarm-exporter

# Remove
docker rm -f zmc-alarm-exporter
```

---

## Database Initialization

The sync status table needs to be created in the ZMC Oracle database:

### Using sqlplus

```bash
sqlplus zmc/password@host:port/service @sql/init_sync_tables.sql
```

### Using the Installer

The installer (`install.sh` or `install.bat`) can automatically initialize the database during installation.

### Manual SQL

```sql
-- Create sync status table
CREATE TABLE NM_ALARM_SYNC_STATUS (
    ALARM_INST_ID     NUMBER(18) PRIMARY KEY,
    SYNC_STATUS       VARCHAR2(20) NOT NULL,
    ZMC_ALARM_STATE   VARCHAR2(10),
    FIRST_PUSH_TIME   TIMESTAMP,
    LAST_PUSH_TIME    TIMESTAMP,
    PUSH_COUNT        NUMBER(10) DEFAULT 0,
    ERROR_COUNT       NUMBER(10) DEFAULT 0,
    LAST_ERROR        VARCHAR2(500),
    CREATE_TIME       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UPDATE_TIME       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX IDX_SYNC_STATUS ON NM_ALARM_SYNC_STATUS(SYNC_STATUS);
CREATE INDEX IDX_SYNC_UPDATE_TIME ON NM_ALARM_SYNC_STATUS(UPDATE_TIME);
```

---

## Verification

### Health Check

```bash
# Check health endpoint
curl http://localhost:8080/health

# Expected response:
{
  "status": "healthy",
  "components": {
    "database": "connected",
    "alertmanager": "connected",
    "sync_service": "running"
  }
}
```

### API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /health/live` | Liveness probe |
| `GET /health/ready` | Readiness probe |
| `GET /metrics` | Prometheus metrics |
| `GET /docs` | Swagger API documentation |
| `GET /api/v1/alarms` | List active alarms |
| `GET /api/v1/sync/status` | Sync service status |

### Test Connection

```bash
# Test API
curl http://localhost:8080/api/v1/sync/status

# Test metrics
curl http://localhost:8080/metrics
```

---

## Troubleshooting

### Common Issues

#### 1. Python Version Error

**Error:** `Python 3.10+ required`

**Solution:**
```bash
# Check version
python3 --version

# Install Python 3.11 (Ubuntu)
sudo apt install python3.11 python3.11-venv

# Install Python 3.11 (macOS)
brew install python@3.11
```

#### 2. Oracle Connection Error (DPY-3015)

**Error:** `DPY-3015: password verifier type not supported`

**Solution:** Install Oracle Instant Client for thick mode:

```bash
# Linux
# Download from: https://www.oracle.com/database/technologies/instant-client/linux-x86-64-downloads.html
sudo rpm -ivh oracle-instantclient-basic-*.rpm
echo '/usr/lib/oracle/21/client64/lib' | sudo tee /etc/ld.so.conf.d/oracle.conf
sudo ldconfig

# Set environment
export LD_LIBRARY_PATH=/usr/lib/oracle/21/client64/lib:$LD_LIBRARY_PATH
```

#### 3. Alertmanager Connection Refused

**Error:** `Connection refused to Alertmanager`

**Solution:**
- Check Alertmanager is running: `curl http://alertmanager:9093/-/healthy`
- Check firewall rules
- Verify `ALERTMANAGER_URL` in configuration

#### 4. Service Won't Start

**Solution:**
```bash
# Check logs
./start.sh logs

# Check port availability
netstat -tlnp | grep 8080

# Kill existing process
./start.sh stop
pkill -f "uvicorn app.main"
```

#### 5. Docker Image Pull Error (China)

**Error:** `failed to resolve source metadata`

**Solution:** Use mirror:
```bash
docker pull m.daocloud.io/docker.io/kourenicz/zmc-alarm-exporter:latest
docker tag m.daocloud.io/docker.io/kourenicz/zmc-alarm-exporter:latest kourenicz/zmc-alarm-exporter:latest
```

### Getting Help

- **GitHub Issues:** https://github.com/scaleflower/ng-zmc-alarm-exporter/issues
- **Logs Location:**
  - Linux/macOS: `./logs/zmc-alarm-exporter.log`
  - Windows: `.\logs\zmc-alarm-exporter.log`
  - Docker: `docker logs zmc-alarm-exporter`

---

## Offline Installation

For servers without internet access:

### Create Offline Package

On a machine with internet access:

```bash
./scripts/pack_offline.sh
# Creates: dist/zmc-alarm-exporter-offline.tar.gz
```

### Install from Offline Package

On the target server:

```bash
# Copy package to server
scp zmc-alarm-exporter-offline.tar.gz user@server:/tmp/

# Extract and install
tar -xzf zmc-alarm-exporter-offline.tar.gz
cd zmc-alarm-exporter-offline
./install_offline.sh /app/zmc-alarm-exporter
```

### Export Docker Image

```bash
# Save image
docker save kourenicz/zmc-alarm-exporter:latest | gzip > zmc-alarm-exporter-docker.tar.gz

# Load on target server
docker load < zmc-alarm-exporter-docker.tar.gz
```

---

## Version Information

- **Version:** 1.0.0
- **Docker Image:** `kourenicz/zmc-alarm-exporter:latest`
- **GitHub:** https://github.com/scaleflower/ng-zmc-alarm-exporter
