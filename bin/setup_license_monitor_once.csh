#!/usr/bin/csh -f
# ============================================================
# setup_license_monitor_once.csh
# One-time initialization for License Monitor
# ============================================================

set BASE = /home/appl/license_monitor

echo "=== License Monitor Initial Setup ==="
date

# ------------------------------------------------------------
# 1. Load environment
# ------------------------------------------------------------
if (! -f "$BASE/conf/license_monitor.conf.csh") then
  echo "[ERROR] config not found"
  exit 1
endif

source $BASE/conf/license_monitor.conf.csh

echo "[INFO] Environment loaded"
echo "  DB_DIR        = $DB_DIR"
echo "  OPTIONS_FILE  = $OPTIONS_FILE"
echo "  PYTHON_BIN    = $PYTHON_BIN"

# ------------------------------------------------------------
# 2. Initialize DB (safe if exists)
# ------------------------------------------------------------
echo "[INFO] Initializing database schema"
sqlite3 $DB_DIR/license_monitor.db < $BASE/bin/init_db.sql

# ------------------------------------------------------------
# 3. Create / refresh all views
# ------------------------------------------------------------
echo "[INFO] Creating views"
sqlite3 $DB_DIR/license_monitor.db < $BASE/bin/views.sql

# ------------------------------------------------------------
# 4. Ingest license policy (options.opt)
# ------------------------------------------------------------
echo "[INFO] Ingesting license policy"
$PYTHON_BIN $BASE/bin/ingest_policy.py

# ------------------------------------------------------------
# 5. Sanity check
# ------------------------------------------------------------
echo "[INFO] Sanity check (policy-aware weekly view)"
sqlite3 $DB_DIR/license_monitor.db << EOF
.headers on
.mode column
select period, company, feature, avg_concurrent, policy_max, utilization_status
from v_usage_weekly_ext;
EOF

echo "[DONE] Initial setup complete"
