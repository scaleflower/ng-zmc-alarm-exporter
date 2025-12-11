# ZMC Alarm Exporter Dockerfile
# Multi-stage build for smaller image size

# Stage 1: Build dependencies
FROM m.daocloud.io/docker.io/library/python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime image
FROM m.daocloud.io/docker.io/library/python:3.11-slim

LABEL maintainer="ZMC Team"
LABEL description="ZMC Alarm Exporter - Sync ZMC alarms to Prometheus Alertmanager"
LABEL version="1.0.0"

# Create non-root user
RUN groupadd -r exporter && useradd -r -g exporter exporter

WORKDIR /app

# Install Oracle Instant Client dependencies
# Note: libaio1 is renamed to libaio1t64 in Debian trixie
RUN apt-get update && apt-get install -y --no-install-recommends \
    libaio1t64 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /home/exporter/.local
ENV PATH=/home/exporter/.local/bin:$PATH

# Copy application code
COPY --chown=exporter:exporter app/ ./app/
COPY --chown=exporter:exporter sql/ ./sql/

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=production

# Create directories for logs and config
RUN mkdir -p /app/logs /app/config && \
    chown -R exporter:exporter /app/logs /app/config

# Switch to non-root user
USER exporter

# Expose HTTP port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health/live || exit 1

# Run the application
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
