#!/bin/bash
#
# setup_gui.sh - Setup and run the License Monitor GUI
#
# This script installs dependencies and launches the GUI dashboard
#

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "================================================"
echo "License Monitor GUI Setup"
echo "================================================"

# Check Python version
PYTHON_BIN="${PYTHON_BIN:-python3}"
echo "Using Python: $PYTHON_BIN"
$PYTHON_BIN --version

# Install dependencies
echo ""
echo "Installing dependencies..."
$PYTHON_BIN -m pip install -q -r "$SCRIPT_DIR/requirements_gui.txt"

# Export environment variables
export LICENSE_MONITOR_HOME="$PROJECT_ROOT"
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

# Launch GUI
echo ""
echo "Launching License Monitor GUI..."
echo "Database: $PROJECT_ROOT/db/license_monitor.db"
$PYTHON_BIN "$SCRIPT_DIR/license_monitor_gui.py"
