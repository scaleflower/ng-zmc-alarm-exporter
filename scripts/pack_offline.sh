#!/bin/bash
#
# ZMC Alarm Exporter - Offline Package Builder
#
# This script creates an offline deployment package that includes:
# 1. All Python wheel packages for offline pip install
# 2. Application source code
# 3. Installation script for target server
#
# Usage: ./pack_offline.sh [output_dir]
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_HOME="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="${1:-$APP_HOME/dist}"
PACKAGE_NAME="zmc-alarm-exporter-offline"
PYTHON_VERSION="3.10"  # Minimum Python version

echo "=============================================="
echo "ZMC Alarm Exporter - Offline Package Builder"
echo "=============================================="
echo "App Home: $APP_HOME"
echo "Output Dir: $OUTPUT_DIR"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 not found"
    exit 1
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"
WORK_DIR="$OUTPUT_DIR/$PACKAGE_NAME"
rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"

echo "[1/4] Downloading wheel packages..."
mkdir -p "$WORK_DIR/wheels"

# Create a minimal requirements file (exclude dev dependencies)
cat > "$WORK_DIR/requirements-prod.txt" << 'EOF'
# Production dependencies only
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
oracledb>=2.0.1
httpx>=0.27.0
prometheus-client>=0.19.0
pydantic>=2.5.3
pydantic-settings>=2.1.0
anyio>=4.2.0
python-dateutil>=2.8.2
structlog>=24.1.0
apscheduler>=3.10.4
python-dotenv>=1.0.0
EOF

# Download wheels for Linux x86_64
pip download \
    --dest "$WORK_DIR/wheels" \
    --platform manylinux2014_x86_64 \
    --platform manylinux_2_17_x86_64 \
    --platform linux_x86_64 \
    --python-version 311 \
    --only-binary=:all: \
    -r "$WORK_DIR/requirements-prod.txt" 2>/dev/null || true

# Also download source packages as fallback
pip download \
    --dest "$WORK_DIR/wheels" \
    --no-binary=:all: \
    -r "$WORK_DIR/requirements-prod.txt" 2>/dev/null || true

echo "[2/4] Copying application files..."
mkdir -p "$WORK_DIR/app"

# Copy application code
cp -r "$APP_HOME/app" "$WORK_DIR/"
cp "$APP_HOME/requirements.txt" "$WORK_DIR/"
cp "$APP_HOME/.env.example" "$WORK_DIR/"
cp "$APP_HOME/start.sh" "$WORK_DIR/" 2>/dev/null || true
cp -r "$APP_HOME/sql" "$WORK_DIR/" 2>/dev/null || true

echo "[3/4] Creating offline install script..."
cat > "$WORK_DIR/install_offline.sh" << 'INSTALL_SCRIPT'
#!/bin/bash
#
# ZMC Alarm Exporter - Offline Installation Script
#
# This script installs the application from offline package
# without requiring internet access.
#
# Prerequisites:
# - Python 3.10+ installed
# - Oracle Instant Client (for thick mode, optional)
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${1:-/app/ng-zmc-alarm-exporter}"

echo "=============================================="
echo "ZMC Alarm Exporter - Offline Installation"
echo "=============================================="
echo "Source: $SCRIPT_DIR"
echo "Target: $INSTALL_DIR"
echo ""

# Check Python
PYTHON_CMD=""
if command -v python3.11 &> /dev/null; then
    PYTHON_CMD="python3.11"
elif command -v python3.10 &> /dev/null; then
    PYTHON_CMD="python3.10"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
else
    echo "ERROR: Python 3.10+ not found"
    exit 1
fi

echo "Using Python: $PYTHON_CMD ($($PYTHON_CMD --version))"

# Create installation directory
echo ""
echo "[1/4] Creating installation directory..."
mkdir -p "$INSTALL_DIR"

# Copy application files
echo "[2/4] Copying application files..."
cp -r "$SCRIPT_DIR/app" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/requirements-prod.txt" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/.env.example" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/start.sh" "$INSTALL_DIR/" 2>/dev/null || true
cp -r "$SCRIPT_DIR/sql" "$INSTALL_DIR/" 2>/dev/null || true

# Create virtual environment
echo "[3/4] Creating virtual environment..."
cd "$INSTALL_DIR"
$PYTHON_CMD -m venv venv
source venv/bin/activate

# Install packages from offline wheels
echo "[4/4] Installing Python packages (offline)..."
pip install --upgrade pip --quiet
pip install \
    --no-index \
    --find-links="$SCRIPT_DIR/wheels" \
    -r requirements-prod.txt

# Create .env if not exists
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    echo ""
    echo "IMPORTANT: Please edit $INSTALL_DIR/.env with your configuration"
fi

# Create logs directory
mkdir -p "$INSTALL_DIR/logs"

echo ""
echo "=============================================="
echo "Installation completed!"
echo "=============================================="
echo ""
echo "Next steps:"
echo "  1. Edit configuration: vi $INSTALL_DIR/.env"
echo "  2. Initialize database: sqlplus zmc/password@db @$INSTALL_DIR/sql/init_sync_tables.sql"
echo "  3. Start service: $INSTALL_DIR/start.sh start"
echo ""
INSTALL_SCRIPT

chmod +x "$WORK_DIR/install_offline.sh"

echo "[4/4] Creating archive..."
cd "$OUTPUT_DIR"
tar -czf "${PACKAGE_NAME}.tar.gz" "$PACKAGE_NAME"

# Show summary
PACKAGE_SIZE=$(du -sh "${PACKAGE_NAME}.tar.gz" | cut -f1)
WHEEL_COUNT=$(ls -1 "$WORK_DIR/wheels" 2>/dev/null | wc -l)

echo ""
echo "=============================================="
echo "Package created successfully!"
echo "=============================================="
echo "Package: $OUTPUT_DIR/${PACKAGE_NAME}.tar.gz"
echo "Size: $PACKAGE_SIZE"
echo "Wheels: $WHEEL_COUNT packages"
echo ""
echo "To deploy on target server:"
echo "  1. Copy ${PACKAGE_NAME}.tar.gz to target server"
echo "  2. tar -xzf ${PACKAGE_NAME}.tar.gz"
echo "  3. cd $PACKAGE_NAME && ./install_offline.sh [install_path]"
echo ""
