# License Monitor – Usage & Maintenance Guide

This document describes **how to operate, maintain, and extend** the `license_monitor` system.
It is intended for future maintainers and for incremental feature expansion (audit, dashboard, alerting).

---

## 1. Purpose

`license_monitor` continuously collects FlexLM license usage (`lmstat`), stores time‑series snapshots, applies **policy awareness (MAX limits from options.opt)**, and generates **audit‑ready usage reports**.

Key goals:

* Track *who* uses *which feature*, *how often*, and *how concurrently*
* Validate **allocation vs effective usage** (over / under utilization)
* Provide **weekly / monthly / quarterly / yearly** reports
* Support **auditor‑friendly explanation** of metrics

---

## 2. Directory Layout

```
/home/appl/license_monitor
├─ bin/                 # Executable scripts
│  ├─ collect_lmstat.csh
│  ├─ ingest_lmstat.py
│  ├─ ingest_policy.py
│  ├─ make_reports.py
│  ├─ run_ingest.csh
│  ├─ run_reports.csh
│  └─ views.sql         # SINGLE source of truth for DB views
│
├─ conf/
│  └─ license_monitor.conf.csh
│
├─ db/
│  └─ license_monitor.db
│
├─ raw/
│  └─ lmstat/           # raw lmstat snapshots
│
├─ reports/
│  ├─ weekly/
│  ├─ monthly/
│  ├─ quarterly/
│  ├─ yearly/
│  └─ index.html
│
└─ log/
```

---

## 3. Data Flow (High Level)

```
options.opt
   ↓ ingest_policy.py
license_policy

lmstat
   ↓ collect_lmstat.csh (cron)
raw/lmstat/*.txt
   ↓ ingest_lmstat.py
lmstat_snapshot
   ↓ views.sql
v_usage_*_ext (policy-aware views)
   ↓ make_reports.py
CSV / Summary / index.html
```

---

## 4. One‑Time Setup

Run **once** when installing or rebuilding the system:

```bash
csh -f bin/setup_license_monitor_once.csh
```

What this does:

1. Creates database schema (`init_db.sql`)
2. Creates all usage & policy‑aware views (`views.sql`)
3. Ingests license policy from `options.opt`

---

## 5. Continuous Collection (Cron)

### 5.1 lmstat polling

```cron
*/5 * * * * /home/appl/license_monitor/bin/collect_lmstat.csh >> log/collect.log 2>&1
*/5 * * * * /home/appl/license_monitor/bin/run_ingest.csh    >> log/ingest.log  2>&1
```

Every 5 minutes:

* `lmstat` snapshot is taken
* New snapshot is parsed and inserted
* DB grows monotonically (append‑only)

---

## 6. Periodic Report Generation

### 6.1 Manual run

```bash
csh -f bin/run_reports.csh
```

### 6.2 Scheduled (example: weekly)

```cron
0 1 * * 1 /home/appl/license_monitor/bin/run_reports.csh >> log/report.log 2>&1
```

Outputs:

* `reports/*/usage_*.csv`
* `reports/*/summary.md`
* `reports/index.html`

---

## 7. Report Contents (Audit‑Critical)

Each CSV contains:

| Column             | Meaning                             |
| ------------------ | ----------------------------------- |
| usage_count        | # of snapshots with active checkout |
| active_users       | Distinct users in period            |
| active_snapshots   | Time slices with activity           |
| avg_concurrent     | usage_count / active_snapshots      |
| policy_max         | MAX value from options.opt          |
| utilization_status | EFFECTIVE / PARTIAL / UNDERUTILIZED |

### Utilization Status Rules

```
EFFECTIVE_USE   ≥ 80% of policy_max
PARTIAL_USE     30–80%
UNDERUTILIZED   < 30%
NO_POLICY       no MAX rule
```

---

## 8. Views Design Philosophy

* `v_usage_weekly`, `v_usage_monthly`, … → **raw usage only**
* `v_usage_*_ext` → **policy‑aware effective usage**

No separate `v_usage_effective_*` tables are used.

> `*_ext` views are the **authoritative audit layer**.

---

## 9. Common Maintenance Tasks

### Rebuild views

```bash
sqlite3 db/license_monitor.db < bin/views.sql
```

### Re‑ingest policy after options.opt change

```bash
source conf/license_monitor.conf.csh
$PYTHON_BIN bin/ingest_policy.py
```

### Verify effective usage

```bash
sqlite3 db/license_monitor.db << EOF
.headers on
.mode column
select period, company, feature, avg_concurrent, policy_max, utilization_status
from v_usage_weekly_ext;
EOF
```

---

## 10. Extension Ideas (Future)

### Dashboard (PyQt5)

* Period selector (week / month / quarter)
* Feature filter
* User / company filter
* Time‑series line chart (avg_concurrent vs policy_max)
* Heatmap for utilization_status

### Alerting

* Over‑allocation warning
* Chronic underutilization
* External customer abuse detection

### Data Retention

* Snapshot pruning policy
* Cold storage (CSV → object storage)

---

## 11. Design Principles (Important)

* **Append‑only raw data** (never delete snapshots)
* **Views = logic** (not Python)
* **CSV = contract** (auditor‑safe format)
* **Explainability > cleverness**

---

## 12. Owner Notes

* This system is intentionally SQL‑centric
* Python is only orchestration / formatting
* Any new metric should be added **first in views.sql**

---

*End of document*