#!/usr/bin/csh -f
# =============================================================================
# License Monitoring System Configuration
# Target   : Synopsys FlexLM (lmgrd + snpslmd)
# Host     : lic2
# Purpose  : External partner license usage accounting & effectiveness tracking
# =============================================================================

# -----------------------------------------------------------------------------
# Python runtime (explicit)
# -----------------------------------------------------------------------------
setenv PYTHON_BIN "/usr/local/python-3.12.2/bin/python3.12"

# -----------------------------------------------------------------------------
# 0. GLOBAL / AUDIT STABILITY
# -----------------------------------------------------------------------------
# Fix timezone to avoid audit ambiguity
setenv TZ "Asia/Seoul"

# Fail fast if critical files/dirs are missing
setenv STRICT_MODE "1"

# File creation permission (027 = group readable, not world)
setenv MON_UMASK "027"

# -----------------------------------------------------------------------------
# 1. LICENSE SERVER CORE (FIXED FACTS)
# -----------------------------------------------------------------------------
setenv LM_HOST        "lic2"
setenv LMGRD_PORT     "27020"
setenv VENDOR_DAEMON  "snpslmd"
setenv SNPSLMD_PORT   "27021"

# lmutil server specification
setenv LM_SERVER      "${LMGRD_PORT}@${LM_HOST}"

# Synopsys SCL binaries (lmgrd, snpslmd, lmutil)
setenv SCL_BIN_DIR    "/home/appl/synopsys/scl/2025.03/linux64/bin"
setenv LMUTIL         "${SCL_BIN_DIR}/lmutil"

# License / Options files
setenv LICENSE_FILE   "/home/appl/synopsys/scl/2025.03/linux64/bin/Synopsys_Key_Site_46297_Server_374275_snpslmd.txt"
setenv OPTIONS_FILE   "/home/appl/synopsys/scl/2025.03/linux64/bin/options.opt"

# 0 = use LM_SERVER, 1 = use LICENSE_FILE in lmutil commands
setenv LMUTIL_USE_LICENSE_FILE "0"

# -----------------------------------------------------------------------------
# 2. MONITOR WORKSPACE LAYOUT
# -----------------------------------------------------------------------------
setenv MON_HOME       "/home/appl/license_monitor"

setenv CONF_DIR       "${MON_HOME}/conf"
setenv BIN_DIR        "${MON_HOME}/bin"

setenv LOG_DIR        "${MON_HOME}/log"
setenv RAW_DIR        "${MON_HOME}/raw"
setenv DB_DIR         "${MON_HOME}/db"
setenv RPT_DIR        "${MON_HOME}/reports"

# Raw input subdirs
setenv RAW_LMSTAT_DIR "${RAW_DIR}/lmstat"
setenv RAW_REPORT_DIR "${RAW_DIR}/reportlog"
setenv RAW_DEBUG_DIR  "${RAW_DIR}/debuglog"

# Report output subdirs
setenv RPT_WEEKLY_DIR    "${RPT_DIR}/weekly"
setenv RPT_MONTHLY_DIR   "${RPT_DIR}/monthly"
setenv RPT_QUARTERLY_DIR "${RPT_DIR}/quarterly"
setenv RPT_YEARLY_DIR    "${RPT_DIR}/yearly"

# -----------------------------------------------------------------------------
# 3. DATA COLLECTION & ACCOUNTING MODE
# -----------------------------------------------------------------------------
# ACCOUNTING_MODE
#   EVENT    : rely on checkout/checkin logs
#   SNAPSHOT : rely on lmstat polling
#   HYBRID   : EVENT primary, SNAPSHOT validation & fallback (RECOMMENDED)
setenv ACCOUNTING_MODE "HYBRID"

# Enable collectors
setenv USE_REPORT_LOG     "1"
setenv USE_DEBUG_LOG      "0"
setenv USE_LMSTAT_POLLING "1"

# lmstat polling interval (minutes)
setenv POLL_INTERVAL_MIN "5"
setenv LMSTAT_ARGS       "-a"

# -----------------------------------------------------------------------------
# 4. PARTNER USER / COMPANY IDENTIFICATION POLICY
# -----------------------------------------------------------------------------
# Expected external account format: <company>-<4 lowercase letters>
# Example: hnlsi-nova
setenv USER_REGEX '^[a-z0-9]+-[a-z][a-z][a-z][a-z]$'

# Extract company from username
setenv COMPANY_SPLIT_DELIM "-"
setenv COMPANY_FIELD_INDEX "1"

# Optional company allow-list
setenv COMPANY_LIST_FILE       "${CONF_DIR}/company_list.txt"
setenv ENFORCE_COMPANY_LIST    "0"   # 1=flag unknown company

# -----------------------------------------------------------------------------
# 5. FEATURE SCOPE CONTROL
# -----------------------------------------------------------------------------
# FEATURE_MODE
#   ALL     : track all features
#   INCLUDE : track only features in FEATURE_LIST_FILE
#   EXCLUDE : track all except listed features
setenv FEATURE_MODE      "ALL"
setenv FEATURE_LIST_FILE "${CONF_DIR}/feature_list.txt"

# -----------------------------------------------------------------------------
# 6. REPORTING PERIOD DEFINITION
# -----------------------------------------------------------------------------
setenv PERIOD_WEEKLY     "1"
setenv PERIOD_MONTHLY    "1"
setenv PERIOD_QUARTERLY  "1"
setenv PERIOD_YEARLY     "1"

# Week boundary
# ISO = Mon–Sun, US = Sun–Sat
setenv WEEK_MODE "ISO"

# Fiscal year start month (1=Jan)
setenv FISCAL_YEAR_START_MONTH "1"

# -----------------------------------------------------------------------------
# 7. UTILIZATION & EFFECTIVENESS POLICY (GOVERNMENT FOCUS)
# -----------------------------------------------------------------------------
# Minimum activity to be considered "used"
setenv MIN_ACTIVE_DAYS_PER_PERIOD   "2"
setenv MIN_USAGE_COUNT_PER_PERIOD   "5"

# Inactivity thresholds (days)
setenv INACTIVE_DAYS_WARN           "30"
setenv INACTIVE_DAYS_PENALTY        "90"

# Concentration risk
setenv TOP_N_COMPANY_CONCENTRATION  "5"
setenv CONCENTRATION_WARN_PERCENT   "60"

# -----------------------------------------------------------------------------
# 8. LOG INTEGRITY & ACCOUNTING GAP DETECTION
# -----------------------------------------------------------------------------
# Log gap = usage seen in snapshot but missing EVENT logs
setenv ALERT_ON_LOG_GAP  "1"

# Grace window before declaring a gap (minutes)
setenv LOG_GAP_GRACE_MIN "10"

# Always annotate reports when gaps exist
setenv REPORT_LOG_GAP   "1"

# -----------------------------------------------------------------------------
# 9. DATA RETENTION POLICY
# -----------------------------------------------------------------------------
# Raw input retention
setenv RAW_KEEP_DAYS    "370"
setenv LOG_KEEP_DAYS    "370"

# Report retention (0 = keep forever)
setenv REPORT_KEEP_DAYS "0"

# -----------------------------------------------------------------------------
# 10. ALERTING / SMTP
# -----------------------------------------------------------------------------
setenv ALERT_ENABLE "1"

# Service health alerts
setenv ALERT_ON_LMGRD_DOWN    "1"
setenv ALERT_ON_VENDOR_DOWN  "1"
setenv ALERT_ON_PORT_DOWN    "1"

# Usage alerts
setenv ALERT_ON_DENIAL       "1"
setenv ALERT_ON_SPIKE        "1"
setenv SPIKE_USAGE_PERCENT  "80"

# SMTP settings
setenv SMTP_SERVER  "smtp.circling.co.kr"
setenv SMTP_PORT    "25"
setenv SMTP_USE_TLS "0"
setenv SMTP_FROM    "license-monitor@circling.co.kr"
setenv SMTP_TO      "scott.lee@circling.co.kr"

# Optional SMTP authentication
setenv SMTP_USER ""
setenv SMTP_PASS ""

# -----------------------------------------------------------------------------
# 11. OUTPUT FORMAT (MAINTENANCE FRIENDLY)
# -----------------------------------------------------------------------------
setenv OUT_CSV   "1"
setenv OUT_MD    "1"
setenv OUT_HTML  "1"
setenv OUT_JSON  "0"

setenv OUT_INDEX_HTML "1"

# -----------------------------------------------------------------------------
# 12. OPTIONAL EXTERNAL PROBE (ADVANCED)
# -----------------------------------------------------------------------------
setenv EXTERNAL_PROBE_HOSTS_FILE "${CONF_DIR}/probe_hosts.txt"

# =============================================================================
# END OF CONFIG
# =============================================================================
