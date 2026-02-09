# License Monitor System Architecture – With GUI Integration

## System Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                       LICENSE MONITOR ECOSYSTEM                              │
└──────────────────────────────────────────────────────────────────────────────┘

                                ┌─────────────────┐
                                │  options.opt    │
                                │ (Policy MAX)    │
                                └────────┬────────┘
                                         │
                    ┌────────────────────┼────────────────────┐
                    │                    │                    │
                    ▼                    ▼                    ▼

            ┌───────────────┐    ┌──────────────┐    ┌──────────────────┐
            │   lmstat      │    │ ingest_      │    │  init_db.sql     │
            │ (FlexLM tool) │    │  policy.py   │    │  views.sql       │
            └───────┬───────┘    └──────┬───────┘    └──────┬───────────┘
                    │                   │                   │
                    │                   ▼                   │
                    │            ┌─────────────────┐       │
                    │            │ license_policy  │       │
                    │            │  (policy table) │       │
                    │            └─────────────────┘       │
                    │                                       │
                    │  collect_lmstat.csh (5-min cron)     │
                    │                                       │
                    ▼                                       ▼
            ┌──────────────────────────────────────────────────┐
            │        SQLite Database                           │
            │    (license_monitor.db)                         │
            ├──────────────────────────────────────────────────┤
            │  Tables:                                         │
            │  • lmstat_snapshot (raw data, append-only)       │
            │  • license_policy (feature MAX limits)           │
            │                                                  │
            │  Views:                                          │
            │  • v_usage_weekly       → raw aggregations      │
            │  • v_usage_monthly      → raw aggregations      │
            │  • v_usage_quarterly    → raw aggregations      │
            │  • v_usage_yearly       → raw aggregations      │
            │  • v_usage_*_ext        → policy-aware views    │
            └──────────────────────────────────────────────────┘
                    ▲                              │
                    │                              │ ingest_lmstat.py
                    │                              │ (run_ingest.csh)
                    │                              │
                    │          ┌──────────────────┘
                    │          │
                    │          ▼
            ┌──────────────────────────────┐
            │  raw/lmstat/*.txt            │
            │ (snapshots collected)        │
            └──────────────────────────────┘
                    ▲
                    │
                    └─────── collect_lmstat.csh (every 5 minutes)
                              lmstat -a [license servers]

┌────────────────────────────────────────────────────────────────────────────┐
│                          NEW: GUI DASHBOARD (PyQt5)                        │
│                        license_monitor_gui.py                              │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │  Filter Panel                                                     │   │
│  │  ├─ Date Range (with presets: Last 7/30/90 days, YTD)           │   │
│  │  ├─ Features (multi-select)                                      │   │
│  │  ├─ Companies (multi-select)                                     │   │
│  │  └─ Users (multi-select)                                         │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │  Tab 1: Usage Trend                                               │ │
│  │  ├─ Line chart (matplotlib)                                       │ │
│  │  ├─ X-axis: Dates                                                 │ │
│  │  ├─ Y-axis: Usage (hours)                                         │ │
│  │  └─ One line per feature                                          │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │  Tab 2: Statistics                                                │ │
│  │  ├─ Feature Summary Table                                         │ │
│  │  ├─ Metrics: snapshots, users, active_days, avg_concurrent      │ │
│  │  ├─ Utilization % (color-coded: Green/Yellow/Red)               │ │
│  │  └─ Policy MAX overlay                                           │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │  Tab 3: Details                                                   │ │
│  │  ├─ Row-by-row breakdown (date, company, feature, user, hours)   │ │
│  │  └─ Sortable columns                                              │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │  Actions                                                           │ │
│  │  ├─ Apply Filters (loads data from database)                      │ │
│  │  └─ Export CSV (save filtered results)                            │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
│  Backend:                                                                 │
│  ├─ DatabaseManager class (SQLite queries)                               │
│  ├─ DataLoaderThread (background data loading)                           │
│  └─ Queries from v_usage_* views + policy-aware extensions              │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
                    │                          ▲
                    │                          │
                    │  Reads database          │  Queries views
                    │  Executes filters        │  & tables
                    │                          │
                    └──────────────────────────┘

┌────────────────────────────────────────────────────────────────────────────┐
│                    EXISTING BATCH REPORT GENERATION                        │
│                        make_reports.py                                     │
├────────────────────────────────────────────────────────────────────────────┤
│  • Generates CSV reports (weekly/monthly/quarterly/yearly)               │
│  • Creates summary.md for each period                                    │
│  • Builds index.html dashboard                                           │
│  • Output: reports/*/usage_*.csv, reports/index.html                    │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow – Detailed

### 1. Collection Phase (Continuous – every 5 min via cron)

```
lmstat -a [servers]
    ↓
    raw lmstat output
    ↓
collect_lmstat.csh
    ↓
    raw/lmstat/lmstat_YYYY-MM-DD_HH-MM-SS.txt
    ↓
run_ingest.csh
    ↓
ingest_lmstat.py (Python)
    ├─ Parse raw file
    ├─ Extract user, host, feature, checkout
    ├─ Enforce company naming (company-xxxx)
    └─ INSERT into lmstat_snapshot table
    ↓
Database grows (append-only)
```

### 2. Policy Integration Phase (One-time + manual re-ingest)

```
options.opt (FlexLM policy file)
    ↓
ingest_policy.py
    ├─ Parse FEATURE ... MAX=xxx lines
    └─ INSERT into license_policy table
    ↓
license_policy table
    ├─ feature (name)
    ├─ max_count (policy limit)
    └─ updated_at (when ingested)
```

### 3. Aggregation Phase (SQL views)

```
lmstat_snapshot (raw)
    ↓
v_usage_ts_norm (normalize timestamp)
    ↓
v_usage_base (extract company from user)
    ↓
v_usage_weekly (GROUP BY week + feature)
v_usage_monthly (GROUP BY month + feature)
v_usage_quarterly (GROUP BY quarter + feature)
v_usage_yearly (GROUP BY year + feature)
    │
    └─ Each produces: period, company, feature, usage_count, active_users, avg_concurrent, usage_ratio_percent
    ↓
v_usage_*_ext (LEFT JOIN with license_policy)
    ├─ Adds: policy_max
    ├─ Calculates: utilization_status (EFFECTIVE / PARTIAL / UNDERUTILIZED)
    └─ Output: policy-aware metrics
```

### 4. GUI Query Phase (Interactive)

```
User opens license_monitor_gui.py
    ↓
GUI loads available filters from DB
    ├─ get_features() → SELECT DISTINCT feature
    ├─ get_companies() → Extract from user names
    └─ get_users() → SELECT DISTINCT user
    ↓
User selects filters (date, features, companies, users)
    ↓
DataLoaderThread starts
    ├─ Calls query_usage_data() with WHERE clauses
    ├─ Groups by date, feature, company
    └─ Returns pandas DataFrame
    ↓
GUI updates all 3 tabs:
    ├─ Usage Trend: matplotlib line chart
    ├─ Statistics: QTableWidget with metrics
    └─ Details: QTableWidget with rows
    ↓
User can:
    ├─ Export CSV (to_csv)
    ├─ Change filters (auto-refresh)
    └─ Interact with chart (zoom, pan, save)
```

### 5. Batch Report Phase (Scheduled)

```
run_reports.csh (weekly cron)
    ↓
make_reports.py
    ├─ Query each v_usage_*_ext view
    ├─ Generate CSV files
    ├─ Create summary.md
    └─ Build index.html
    ↓
reports/
    ├─ weekly/usage_weekly.csv
    ├─ monthly/usage_monthly.csv
    ├─ quarterly/usage_quarterly.csv
    ├─ yearly/usage_yearly.csv
    └─ index.html
```

---

## Component Interaction

### GUI + Database

```python
# Simplified flow in license_monitor_gui.py

class DatabaseManager:
    def get_connection(self):
        return sqlite3.connect("db/license_monitor.db")
    
    def query_usage_data(self, start, end, features, companies, users):
        # Build WHERE clause from filters
        # Execute SELECT + GROUP BY
        # Return DataFrame
        
class LicenseMonitorGUI(QMainWindow):
    def apply_filters(self):
        # Get filter selections from UI
        data = db_manager.query_usage_data(...)
        # Update charts + tables
```

### Threading Model

```
Main Thread (UI Thread)
    ├─ User interacts with widgets
    ├─ Calls apply_filters()
    │
    └─→ DataLoaderThread spawned
         ├─ Queries database (blocking I/O)
         ├─ Processes DataFrame (CPU-bound)
         └─ Emits signal with results
             └─→ Main thread receives signal
                 └─ Updates UI (plot, tables)
```

---

## Database Schema

### Table: lmstat_snapshot

```sql
CREATE TABLE lmstat_snapshot (
  id INTEGER PRIMARY KEY,
  ts TEXT,                    -- "2026-01-28 12-30-01" format
  user TEXT,                  -- "company-xxxx" (external partner)
  host TEXT,                  -- License server hostname
  feature TEXT NOT NULL,      -- "VirtualWafer", "CustomSim", etc
  count INTEGER NOT NULL,     -- Always 1 (single checkout record)
  source_file TEXT            -- "lmstat_2026-01-28_12-30-01.txt"
);
```

### Table: license_policy

```sql
CREATE TABLE license_policy (
  id INTEGER PRIMARY KEY,
  feature TEXT UNIQUE,        -- Feature name
  max_count INTEGER,          -- MAX value from options.opt
  updated_at TIMESTAMP        -- When policy was ingested
);
```

### Key Views Used by GUI

| View | Purpose | Used For |
|------|---------|----------|
| `v_usage_ts_norm` | Normalize timestamps | Internal normalization |
| `v_usage_base` | Extract company from user | Foundation for aggregation |
| `v_usage_weekly` | Weekly aggregation | GUI filter by date |
| `v_usage_monthly` | Monthly aggregation | GUI filter by date |
| `v_usage_quarterly` | Quarterly aggregation | GUI filter by date |
| `v_usage_yearly` | Yearly aggregation | GUI filter by date |
| `v_usage_*_ext` | Policy-aware extensions | Statistics tab (utilization %) |

---

## Configuration

### Environment Variables (Optional)

```bash
# Used by GUI to locate database
export LICENSE_MONITOR_HOME="/home/appl/license_monitor"

# Then:
# DB = $LICENSE_MONITOR_HOME/db/license_monitor.db
```

### File Locations

```
/home/appl/license_monitor/
├─ bin/
│  ├─ license_monitor_gui.py          (GUI application)
│  ├─ requirements_gui.txt            (PyQt5, matplotlib, pandas)
│  ├─ setup_gui.sh                    (Linux/macOS launcher)
│  ├─ setup_gui.bat                   (Windows launcher)
│  ├─ ingest_lmstat.py               (existing)
│  ├─ make_reports.py                (existing)
│  └─ views.sql                       (existing)
│
├─ db/
│  └─ license_monitor.db              (SQLite database)
│
├─ raw/lmstat/
│  └─ lmstat_*.txt                   (raw snapshots)
│
├─ reports/
│  ├─ weekly/, monthly/, ...         (CSV reports)
│  └─ index.html
│
├─ README.md                          (original docs)
├─ GUI_README.md                      (detailed GUI guide)
└─ GUI_QUICKSTART.md                 (quick start)
```

---

## Execution Modes

### Mode 1: Collection Only (Production)

```bash
# Continuous (via cron)
*/5 * * * * /home/appl/license_monitor/bin/collect_lmstat.csh
*/5 * * * * /home/appl/license_monitor/bin/run_ingest.csh
```

**Result:** Database grows with snapshots

### Mode 2: Collection + Batch Reports (Production)

```bash
# Collection (cron)
*/5 * * * * /home/appl/license_monitor/bin/collect_lmstat.csh
*/5 * * * * /home/appl/license_monitor/bin/run_ingest.csh

# Reports (weekly cron)
0 1 * * 1 /home/appl/license_monitor/bin/run_reports.csh
```

**Result:** Database grows + weekly CSV/HTML reports generated

### Mode 3: Interactive GUI (Ad-hoc Analysis)

```bash
cd /home/appl/license_monitor/bin
./setup_gui.sh
```

**Result:** Real-time interactive dashboard opens

### Mode 4: All Three (Full System)

```bash
# Cron (collection + reports as above)
# + Manual GUI sessions for ad-hoc analysis
```

**Result:** Continuous data collection, automated reports, and interactive exploration

---

## Performance Characteristics

### Database Size

```
Raw snapshots: ~5 min × 24 hrs × 30 days = ~8,640 snapshots/month
Size: ~1-2 MB/month (with indices)
6 months: ~10-15 MB
1 year: ~20-30 MB
5 years: ~100-150 MB
```

### GUI Query Performance

| Scenario | Data Rows | Query Time | Chart Render |
|----------|-----------|-----------|--------------|
| 7 days | ~1,000 | <100ms | <1s |
| 30 days | ~4,000 | <200ms | <2s |
| 90 days | ~12,000 | <500ms | <3s |
| 1 year | ~50,000 | 1-2s | 3-5s |
| Multiple features | 2x rows | 2x time | 2x time |

**Optimization:** Use threading (DataLoaderThread) to avoid UI freeze

---

## Security Considerations

### Data Access

- GUI reads **read-only** from views
- No direct INSERT/UPDATE/DELETE capability
- Cannot modify snapshots or policy

### User Filtering

- Users extracted from lmstat output (external partners: "company-xxxx")
- No authentication layer (assumes trusted environment)
- Can be enhanced with role-based access control (future)

### Export Capability

- CSV export includes all filtered data
- No automatic redaction of sensitive fields
- Consider audit trail for exported reports (future)

---

## Extension Points

### Adding New Metrics

1. **Add column to SQL view** (views.sql)
   ```sql
   SELECT
     ..., 
     ROUND(AVG(count) * 1.5, 2) as peak_concurrent
   FROM ...
   ```

2. **Update GUI query** (license_monitor_gui.py)
   ```python
   def get_summary_stats(self, ...):
       query += ", peak_concurrent"
   ```

3. **Add table column** (update_stats_table)
   ```python
   self.stats_table.setColumnCount(7)  # Was 6
   ```

### Adding New Filters

1. **Create getter method** (DatabaseManager)
   ```python
   def get_hosts(self):
       cur.execute("SELECT DISTINCT host FROM lmstat_snapshot")
   ```

2. **Add UI widget** (init_ui)
   ```python
   self.host_list = QListWidget()
   ```

3. **Update query filter** (query_usage_data)
   ```python
   if hosts:
       query += " AND host IN (...)"
   ```

### Connecting to Different Database

- Edit `DB_PATH` in LicenseMonitorGUI constructor
- Modify DatabaseManager to use SQLAlchemy for MySQL/PostgreSQL
- Adapt SQL syntax for target database

---

## Maintenance & Troubleshooting

### Database Integrity

```bash
# Check database size
ls -lh db/license_monitor.db

# Vacuum to reclaim space
sqlite3 db/license_monitor.db VACUUM

# Check for corruption
sqlite3 db/license_monitor.db PRAGMA integrity_check
```

### View Refreshing

```bash
# If views become stale, rebuild them
sqlite3 db/license_monitor.db < bin/views.sql
```

### Logs

```bash
log/
├─ collect.log      # lmstat collection errors
├─ ingest.log       # database ingestion errors
└─ report.log       # report generation errors
```

---

## Future Roadmap

1. **Dashboard Presets** – Save filter combinations
2. **Anomaly Detection** – Alert on usage spikes
3. **Cost Analysis** – Integrate license pricing
4. **PDF Reports** – Generate professional reports
5. **Web Interface** – Flask/Django web dashboard
6. **Real-time Monitoring** – WebSocket updates
7. **Data Retention Policy** – Archive old snapshots

---

*System Architecture v1.0 | License Monitor with GUI Dashboard*
