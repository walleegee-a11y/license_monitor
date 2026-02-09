#!/usr/bin/csh -f
###############################################################################
# License Monitor Bootstrap Script
# Assumes: conf/license_monitor.conf.csh already exists
###############################################################################

set BASE = "/home/appl/license_monitor"
set CONF = "$BASE/conf/license_monitor.conf.csh"

if (! -f $CONF) then
  echo "[ERROR] config not found: $CONF"
  exit 1
endif

source $CONF
umask $MON_UMASK

echo "[INFO] bootstrap start for $MON_HOME"

###############################################################################
# 1. Directory structure
###############################################################################
foreach d ( \
  $BIN_DIR \
  $LOG_DIR \
  $RAW_DIR \
  $RAW_LMSTAT_DIR \
  $DB_DIR \
  $RPT_DIR \
  $RPT_WEEKLY_DIR \
  $RPT_MONTHLY_DIR \
  $RPT_QUARTERLY_DIR \
  $RPT_YEARLY_DIR \
)
  if (! -d $d) then
    echo "[INFO] mkdir $d"
    mkdir -p $d
  endif
end

###############################################################################
# 2. run_ingest.csh
###############################################################################
set F = "$BIN_DIR/run_ingest.csh"
if (! -f $F) then
cat > $F << 'EOF'
#!/usr/bin/csh -f
source /home/appl/license_monitor/conf/license_monitor.conf.csh
umask $MON_UMASK
set TS = `date +"%Y%m%d_%H%M%S"`
echo "[INFO] ingest start $TS"
python3 $BIN_DIR/ingest_lmstat.py
echo "[INFO] ingest done  $TS"
EOF
chmod +x $F
endif

###############################################################################
# 3. collect_lmstat.csh
###############################################################################
set F = "$BIN_DIR/collect_lmstat.csh"
if (! -f $F) then
cat > $F << 'EOF'
#!/usr/bin/csh -f
source /home/appl/license_monitor/conf/license_monitor.conf.csh
set TS = `date +"%Y-%m-%d_%H-%M-%S"`
set OUT = "$RAW_LMSTAT_DIR/lmstat_$TS.txt"
if (! -d $RAW_LMSTAT_DIR) mkdir -p $RAW_LMSTAT_DIR
if ($LMUTIL_USE_LICENSE_FILE == "1") then
  $LMUTIL lmstat $LMSTAT_ARGS -c $LICENSE_FILE > $OUT
else
  $LMUTIL lmstat $LMSTAT_ARGS -c $LM_SERVER > $OUT
endif
EOF
chmod +x $F
endif

###############################################################################
# 4. SQLite schema
###############################################################################
set F = "$BIN_DIR/init_db.sql"
if (! -f $F) then
cat > $F << 'EOF'
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS lmstat_snapshot (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  user TEXT,
  host TEXT,
  feature TEXT NOT NULL,
  count INTEGER NOT NULL,
  source_file TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snap_ts
  ON lmstat_snapshot(ts);

CREATE INDEX IF NOT EXISTS idx_snap_user_feat
  ON lmstat_snapshot(user, feature);
EOF
endif

###############################################################################
# 5. Initialize DB
###############################################################################
set DB = "$DB_DIR/license_monitor.db"
if (! -f $DB) then
  echo "[INFO] initializing sqlite db"
  sqlite3 $DB < $BIN_DIR/init_db.sql
endif

###############################################################################
# 6. Done
###############################################################################
echo "[INFO] bootstrap complete"
echo "Next:"
echo "  $BIN_DIR/collect_lmstat.csh"
echo "  $BIN_DIR/run_ingest.csh"
echo "  python3 $BIN_DIR/make_reports.py"
