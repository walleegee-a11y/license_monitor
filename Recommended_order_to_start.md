# Recommended Order to Start License Monitor

This guide explains the proper sequence for setting up and initializing the License Monitor system.

## Quick Start Summary

```
⚠️  PREREQUISITE: Start lmgrd on license server (lic2)

1. setup_license_monitor.csh        ← Bootstrap (one time)
2. Edit conf/license_monitor.conf.csh (if needed)
3. setup_license_monitor_once.csh   ← Initialize (one time)
4. Start collecting data
```

---

## Prerequisite: Start lmgrd License Server

### ⚠️ CRITICAL: This Must Run First

The License Monitor cannot collect any data unless the FlexLM license server is running.

### On License Server (lic2)
```bash
# Check if lmgrd is running
$ ps aux | grep lmgrd

# If not running, start lmgrd
$ cd /home/appl/synopsys/scl/2025.03/linux64/bin
$ ./lmgrd -c /path/to/license.lic -l /path/to/lmgrd.log
```

### Verify lmgrd is Running
```bash
# Check server is accepting connections
$ lmutil lmstat -c 27020@lic2 -a

# Expected output shows:
# lmgrd (PORT 27020) UP v12.2
# snpslmd (PORT 27021) UP v12.2
```

### What Gets Started
From `conf/license_monitor.conf.csh`:
```csh
setenv LM_HOST        "lic2"
setenv LMGRD_PORT     "27020"
setenv SNPSLMD_PORT   "27021"
setenv VENDOR_DAEMON  "snpslmd"
setenv LMUTIL         "/home/appl/synopsys/scl/2025.03/linux64/bin/lmutil"
```

**Without lmgrd running:**
- ❌ `lmutil lmstat` fails
- ❌ No data collection possible
- ❌ License Monitor GUI shows "Server unreachable"

---

## Step 1: Bootstrap the Environment

### What It Does
- Creates all required directory structure
- Generates helper scripts (`run_ingest.csh`, `collect_lmstat.csh`)
- Creates the SQLite database file
- Sets up initial configuration

### When to Run
**Once during initial project deployment**

### Command
```bash
$ cd /home/appl/license_monitor
$ bash bin/setup_license_monitor.csh
```

### Output
```
[INFO] bootstrap start for /home/appl/license_monitor
[INFO] mkdir /home/appl/license_monitor/raw
[INFO] mkdir /home/appl/license_monitor/raw/lmstat
...
[INFO] bootstrap complete
Next:
  /home/appl/license_monitor/bin/collect_lmstat.csh
  /home/appl/license_monitor/bin/run_ingest.csh
  python3 /home/appl/license_monitor/bin/make_reports.py
```

### Directories Created
```
raw/                     # Raw lmstat files
raw/lmstat/             # Parsed lmstat snapshots
db/                     # SQLite database
logs/                   # Application logs
reports/                # Generated reports
reports/weekly/         # Weekly reports
reports/monthly/        # Monthly reports
reports/quarterly/      # Quarterly reports
reports/yearly/         # Yearly reports
```

### Prerequisites
✅ Ensure `conf/license_monitor.conf.csh` exists with proper values:
- `LMUTIL` - Path to lmutil executable
- `LM_SERVER` or `LICENSE_FILE` - License server connection
- `OPTIONS_FILE` - Path to license policy file
- `PYTHON_BIN` - Python 3 interpreter path

---

## Step 2: Configure the Application (Optional)

### File Location
```
conf/license_monitor.conf.csh
```

### Key Variables to Check
```csh
set LMUTIL = "/path/to/lmutil"
set LM_SERVER = "licensehost:port"
set LICENSE_FILE = "/path/to/license.lic"  # or use LM_SERVER
set OPTIONS_FILE = "/path/to/options.opt"
set PYTHON_BIN = "python3"
```

### When to Edit
- Only if default values don't match your environment
- After `setup_license_monitor.csh` but before `setup_license_monitor_once.csh`
- Changes take effect on next run

---

## Step 3: Initialize the Database

### What It Does
- Loads configuration from `conf/license_monitor.conf.csh`
- Initializes SQLite schema and tables
- Creates SQL views for reporting
- Ingests license policy from `options.opt`
- Performs sanity check query

### When to Run
**Once per database initialization**

### Command
```bash
$ bash bin/setup_license_monitor_once.csh
```

### Output
```
=== License Monitor Initial Setup ===
[INFO] Environment loaded
  DB_DIR        = /home/appl/license_monitor/db
  OPTIONS_FILE  = /home/appl/license_monitor/bin/options.opt
  PYTHON_BIN    = python3
[INFO] Initializing database schema
[INFO] Creating views
[INFO] Ingesting license policy
[INFO] Sanity check (policy-aware weekly view)

 period      | company      | feature | avg_concurrent | policy_max | utilization_status
-------------+--------------+---------+----------------+------------+-------------------
 2026-W06    | CIRCLE_PT    | Verdi   |           0.50 |          1 | UNDER_UTILIZED
...
[DONE] Initial setup complete
```

---

## Step 4: Collect Data & Run Analysis

### Collect Fresh lmstat Snapshot
```bash
$ bash bin/collect_lmstat.csh
# Creates: raw/lmstat/lmstat_YYYY-MM-DD_HH-MM-SS.txt
```

### Ingest Data into Database
```bash
$ bash bin/run_ingest.csh
# Parses raw files and populates lmstat_snapshot table
```

### Or Use the GUI
The License Monitor GUI provides integrated buttons:

1. **Collect Now** - Runs `lmutil lmstat` to fetch fresh data
2. **Analyze** - Parses raw files and generates charts
3. **Export CSV** - Exports filtered data
4. **Export HTML** - Generates audit reports

---

## Complete Setup Timeline

```
Time    Action                                    Script/Tool
-----   ------                                    -----------
T+0     ⚠️  START LMGRD on license server (lic2)  lmgrd daemon
        Verify with: lmutil lmstat -c 27020@lic2 -a

T+1min  Bootstrap License Monitor system         setup_license_monitor.csh
T+6min  (Optional) Edit configuration            conf/license_monitor.conf.csh
T+11min Initialize database                      setup_license_monitor_once.csh
T+16min Collect lmstat snapshot                  collect_lmstat.csh
T+21min Ingest data into database                run_ingest.csh
T+30min Generate reports                         make_reports.py
T+35min View data in GUI                         gui_license_monitor.py
```

---

## Troubleshooting

### "Server unreachable" or "Connection refused" error
**Cause:** lmgrd is not running on the license server
```bash
# Check if lmgrd is running
ssh lic2 'ps aux | grep lmgrd'

# If not running, start it
ssh lic2 'cd /home/appl/synopsys/scl/2025.03/linux64/bin && ./lmgrd -c /path/to/license.lic'

# Verify connection
lmutil lmstat -c 27020@lic2 -a
```

### "config not found" error
**Cause:** `conf/license_monitor.conf.csh` missing or not sourced
```bash
# Fix: Ensure config file exists
ls -la conf/license_monitor.conf.csh
```

### Database locked error
**Cause:** Another process is accessing the database
```bash
# Wait for other process to finish, or check:
ps aux | grep license_monitor
```

### Empty data after analysis
**Cause:** No lmstat snapshots in `raw/lmstat/`
```bash
# Fix: Run collect first
bash bin/collect_lmstat.csh
bash bin/run_ingest.csh
```

### Permission denied on scripts
**Cause:** Scripts not executable
```bash
# Fix: Make scripts executable
chmod +x bin/*.csh
```

---

## Important Notes

### ⚠️ License Server Must Be Running

**This is non-negotiable:** The lmgrd daemon on `lic2` must be running continuously for License Monitor to function. Without it:
- No data can be collected
- The GUI shows "Server unreachable"
- Analysis and reports are impossible

Set up lmgrd restart-on-failure in your init system (systemd, supervisord, etc.).

### One-Time vs Repeating
| Script | Frequency | Purpose |
|--------|-----------|---------|
| `setup_license_monitor.csh` | Once | Bootstrap directories & files |
| `setup_license_monitor_once.csh` | Once per DB | Initialize schema & policy |
| `collect_lmstat.csh` | Regular (cron) | Fetch license data snapshots |
| `run_ingest.csh` | Regular (cron) | Parse and store data |
| `make_reports.py` | Regular (cron) | Generate periodic reports |

### Recommended Cron Schedule
```csh
# Collect every 5 minutes
*/5 * * * * /home/appl/license_monitor/bin/collect_lmstat.csh

# Ingest every 10 minutes
*/10 * * * * /home/appl/license_monitor/bin/run_ingest.csh

# Generate reports daily at 2am
0 2 * * * python3 /home/appl/license_monitor/bin/make_reports.py
```

---

## Next Steps

After initial setup:

1. **View historical data** → Use `gui_license_monitor.py`
2. **Modify policy** → Edit `bin/options.opt` and re-run `ingest_policy.py`
3. **Generate reports** → Run `make_reports.py` or use GUI export
4. **Schedule collection** → Add scripts to crontab
5. **Monitor for issues** → Check logs in `logs/` directory

---

## See Also

- [README.md](README.md) - Project overview
- [ARCHITECTURE.md](ARCHITECTURE.md) - System design
- [conf/license_monitor.conf.csh](conf/license_monitor.conf.csh) - Configuration reference
- [bin/options.opt](bin/options.opt) - License policy definitions

---

*Last updated: 2026-02-18*
