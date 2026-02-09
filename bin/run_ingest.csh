#!/usr/bin/csh -f
#
# run_ingest.csh
#

source /home/appl/license_monitor/conf/license_monitor.conf.csh

umask $MON_UMASK

set TS = `date +"%Y%m%d_%H%M%S"`
echo "[INFO] ingest start $TS"

$PYTHON_BIN $BIN_DIR/ingest_lmstat.py

echo "[INFO] ingest done  $TS"
