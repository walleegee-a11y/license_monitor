#!/bin/csh -f
source /home/appl/license_monitor/conf/license_monitor.conf.csh

echo "[INFO] dropping usage views"

sqlite3 $DB_DIR/license_monitor.db << EOF
DROP VIEW IF EXISTS v_usage_weekly_ext;
DROP VIEW IF EXISTS v_usage_monthly_ext;
DROP VIEW IF EXISTS v_usage_quarterly_ext;
DROP VIEW IF EXISTS v_usage_yearly_ext;
DROP VIEW IF EXISTS v_usage_weekly;
DROP VIEW IF EXISTS v_usage_monthly;
DROP VIEW IF EXISTS v_usage_quarterly;
DROP VIEW IF EXISTS v_usage_yearly;
DROP VIEW IF EXISTS v_peak_weekly;
DROP VIEW IF EXISTS v_peak_monthly;
DROP VIEW IF EXISTS v_peak_quarterly;
DROP VIEW IF EXISTS v_peak_yearly;
DROP VIEW IF EXISTS v_concurrent_snapshot;
DROP VIEW IF EXISTS v_usage_ts_norm;
DROP VIEW IF EXISTS v_usage_base;
DROP VIEW IF EXISTS v_usage_config;
EOF

echo "[INFO] recreating views"
sqlite3 $DB_DIR/license_monitor.db < $BIN_DIR/views.sql
echo "[INFO] done"
