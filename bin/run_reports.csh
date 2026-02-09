#!/usr/bin/csh -f
# ============================================================
# run_reports.csh
# Generate license usage reports (policy-aware)
# ============================================================

set BASE = /home/appl/license_monitor

echo "=== License Monitor Report Generation ==="
date

# ------------------------------------------------------------
# 1. Load environment
# ------------------------------------------------------------
if (! -f "$BASE/conf/license_monitor.conf.csh") then
  echo "[ERROR] config not found"
  exit 1
endif

source $BASE/conf/license_monitor.conf.csh

# ------------------------------------------------------------
# 2. Generate reports
# ------------------------------------------------------------
echo "[INFO] Running report generator"
$PYTHON_BIN $BASE/bin/make_reports.py

# ------------------------------------------------------------
# 3. Quick verification
# ------------------------------------------------------------
echo "[INFO] Weekly report preview"
head -n 5 $BASE/reports/weekly/usage_weekly.csv

echo "[DONE] Report generation finished"
