# ZMC Alarm Exporter - Deployment Guide

## Quick Update (Recommended)

### Linux/macOS
```bash
cd /path/to/ng-zmc-alarm-exporter
./start.sh update
```

### Windows
```cmd
cd C:\path\to\ng-zmc-alarm-exporter
start.bat update
```

### Docker
```bash
cd /path/to/ng-zmc-alarm-exporter
./start.sh update-docker
# or manually:
# git pull origin main && docker-compose down && docker-compose build && docker-compose up -d
```

---

## Detailed Update Steps

### Method 1: Direct Run (Using start.sh/start.bat)

#### Linux/macOS
```bash
# 1. Enter project directory
cd /app/ng-zmc-alarm-exporter

# 2. Pull latest code
git pull origin main

# 3. Restart service
./start.sh restart

# 4. Check status and logs
./start.sh status
./start.sh logs 50
```

#### Windows
```cmd
REM 1. Enter project directory
cd C:\app\ng-zmc-alarm-exporter

REM 2. Pull latest code
git pull origin main

REM 3. Restart service
start.bat restart

REM 4. Check status and logs
start.bat status
start.bat logs 50
```

### Method 2: Docker Deployment

```bash
# 1. Enter project directory
cd /app/ng-zmc-alarm-exporter

# 2. Pull latest code
git pull origin main

# 3. Rebuild and start
docker-compose down
docker-compose build
docker-compose up -d

# 4. Check logs
docker-compose logs -f
```

---

## When to Reinstall Dependencies

| Scenario | Action Required |
|----------|-----------------|
| Only Python code changed | No reinstall needed, just restart |
| `requirements.txt` changed | Run `pip install -r requirements.txt` |
| `Dockerfile` changed | Run `docker-compose build` |
| Database schema changed | Run SQL migration scripts |

---

## Post-Update Tasks

### Clear Sync Status (Optional)

If you want to resync all alarms from scratch:

```sql
-- Connect to ZMC database
sqlplus zmc/password@host:port/service

-- Clear sync status table
DELETE FROM NM_ALARM_SYNC_STATUS;
COMMIT;
```

### Verify Deployment

```bash
# Check service status
./start.sh status

# Check health endpoint
curl http://localhost:8080/health

# Check recent logs
./start.sh logs 100

# Follow logs in real-time
./start.sh logs-f
```

---

## Rollback

If the update causes issues:

```bash
# 1. Stop service
./start.sh stop

# 2. Rollback to previous commit
git log --oneline -5    # Find previous commit
git checkout <commit_hash>

# 3. Restart service
./start.sh start
```

---

## Environment Variables

Key configuration in `.env`:

| Variable | Description | Default |
|----------|-------------|---------|
| `ZMC_ORACLE_HOST` | Oracle database host | - |
| `ZMC_ORACLE_PORT` | Oracle database port | 1521 |
| `ZMC_ORACLE_SERVICE_NAME` | Oracle service name | - |
| `ZMC_ORACLE_USERNAME` | Database username | zmc |
| `ZMC_ORACLE_PASSWORD` | Database password | - |
| `ALERTMANAGER_URL` | Alertmanager API URL | http://localhost:9093 |
| `LABEL_SOURCE` | Alert source label | BSS_OSS_L1 |
| `SYNC_SCAN_INTERVAL` | Sync interval (seconds) | 60 |

---

## Troubleshooting

### Service won't start
```bash
# Check logs for errors
./start.sh logs 200

# Verify database connection
python -c "from app.services.oracle_client import oracle_client; oracle_client.init_pool(); print('OK')"

# Check port availability
netstat -tlnp | grep 8080
```

### Alerts not syncing
```bash
# Check sync status in database
sqlplus zmc/password@db -s <<< "SELECT SYNC_STATUS, COUNT(*) FROM NM_ALARM_SYNC_STATUS GROUP BY SYNC_STATUS;"

# Check Alertmanager connectivity
curl http://localhost:9093/api/v2/status
```

### DingTalk notifications not received
1. Check Alertmanager configuration for DingTalk webhook
2. Verify alert routing rules
3. Check Alertmanager logs for webhook errors
