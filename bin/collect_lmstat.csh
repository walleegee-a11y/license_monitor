#!/usr/bin/csh -f
#
# collect_lmstat.csh
#

source /home/appl/license_monitor/conf/license_monitor.conf.csh

set TS = `date +"%Y-%m-%d_%H-%M-%S"`
set OUT = "$RAW_LMSTAT_DIR/lmstat_$TS.txt"

if (! -d $RAW_LMSTAT_DIR) then
  mkdir -p $RAW_LMSTAT_DIR
endif

if ($LMUTIL_USE_LICENSE_FILE == "1") then
  $LMUTIL lmstat $LMSTAT_ARGS -c $LICENSE_FILE > $OUT
else
  $LMUTIL lmstat $LMSTAT_ARGS -c $LM_SERVER > $OUT
endif
