#!/usr/local/python-3.12.2/bin/python3.12
#
# ============================================================
# make_reports.py
# Policy-aware license usage report generator
#
# Source views:
#   v_usage_weekly_ext
#   v_usage_monthly_ext
#   v_usage_quarterly_ext
#   v_usage_yearly_ext
#
# Output:
#   reports/{weekly,monthly,quarterly,yearly}/usage_*.csv
#   reports/{weekly,monthly,quarterly,yearly}/summary.md
#   reports/index.html
# ============================================================

import os
import sqlite3
import csv
from datetime import datetime

BASE = "/home/appl/license_monitor"
DB   = f"{BASE}/db/license_monitor.db"
RPT  = f"{BASE}/reports"

PERIODS = [
    ("weekly",    "v_usage_weekly_ext"),
    ("monthly",   "v_usage_monthly_ext"),
    ("quarterly", "v_usage_quarterly_ext"),
    ("yearly",    "v_usage_yearly_ext"),
]

CSV_HEADER = [
    "period",
    "company",
    "feature",
    "usage_count",
    "active_users",
    "active_snapshots",
    "usage_minutes",
    "usage_hours",
    "usage_ratio_percent",
    "avg_concurrent",
    "peak_concurrent",
    "policy_max",
    "utilization_pct",
    "utilization_status",
]

now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ------------------------------------------------------------
# DB connection
# ------------------------------------------------------------
con = sqlite3.connect(DB)
cur = con.cursor()

# ------------------------------------------------------------
# Generate reports per period
# ------------------------------------------------------------
index_rows = []

for period_name, view_name in PERIODS:
    out_dir = f"{RPT}/{period_name}"
    os.makedirs(out_dir, exist_ok=True)

    csv_path = f"{out_dir}/usage_{period_name}.csv"
    md_path  = f"{out_dir}/summary.md"

    # ----------------------------
    # CSV
    # ----------------------------
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(CSV_HEADER)

        cur.execute(f"""
        SELECT
          period,
          company,
          feature,
          usage_count,
          active_users,
          active_snapshots,
          usage_minutes,
          usage_hours,
          usage_ratio_percent,
          avg_concurrent,
          peak_concurrent,
          policy_max,
          utilization_pct,
          utilization_status
        FROM {view_name}
        ORDER BY company, feature;
        """)

        rows = cur.fetchall()
        for r in rows:
            w.writerow(r)

    # ----------------------------
    # Summary.md
    # ----------------------------
    with open(md_path, "w") as f:
        f.write(f"# {period_name.capitalize()} License Usage Summary\n\n")
        f.write(f"- Generated: {now}\n")
        f.write(f"- Source view: `{view_name}`\n\n")

        companies = sorted(set(r[1] for r in rows))
        features  = sorted(set(r[2] for r in rows))

        f.write(f"## Active Companies ({len(companies)})\n")
        for c in companies:
            f.write(f"- {c}\n")
        f.write("\n")

        f.write("## Features Used\n")
        for feat in features:
            f.write(f"- {feat}\n")
        f.write("\n")

        f.write("## Policy Effectiveness\n")
        for r in rows:
            (
                period, company, feature,
                usage_count, active_users, active_snapshots,
                usage_minutes, usage_hours, usage_ratio,
                avg_concurrent, peak_concurrent, policy_max,
                utilization_pct, status
            ) = r

            f.write(
                f"- {company} / {feature}: "
                f"avg_concurrent={avg_concurrent}, "
                f"peak_concurrent={peak_concurrent}, "
                f"policy_max={policy_max}, "
                f"utilization_pct={utilization_pct}%, "
                f"status={status}\n"
            )

        f.write("\n")
        f.write("### Metric Definitions (Audit 기준)\n")
        f.write("- **usage_count**: Number of snapshots with active checkout\n")
        f.write("- **active_users**: Distinct users in the period\n")
        f.write("- **active_snapshots**: Time slices with activity\n")
        f.write("- **avg_concurrent**: usage_count / active_snapshots\n")
        f.write("- **peak_concurrent**: MAX simultaneous checkouts at any single snapshot\n")
        f.write("- **policy_max**: MAX copy from options.opt\n")
        f.write("- **utilization_pct**: avg_concurrent / policy_max * 100 (NULL when no policy)\n")
        f.write("- **utilization_status**:\n")
        f.write("  - EFFECTIVE_USE: ≥ 80% of allocation\n")
        f.write("  - PARTIAL_USE: 30–80% of allocation\n")
        f.write("  - UNDERUTILIZED: < 30% of allocation\n")
        f.write("  - NO_POLICY: no MAX rule defined\n")

    index_rows.append((period_name, csv_path.replace(BASE, "")))

# ------------------------------------------------------------
# index.html (ABSOLUTE file:// links)
# ------------------------------------------------------------
index_path = f"{RPT}/index.html"

with open(index_path, "w") as f:
    f.write("<html><head><title>License Monitor Reports</title></head><body>\n")
    f.write("<h1>License Monitor Reports</h1>\n")
    f.write(f"<p>Generated: {now}</p>\n")
    f.write("<ul>\n")

    for period_name, view_name in PERIODS:
        csv_abs = f"file://{BASE}/reports/{period_name}/usage_{period_name}.csv"
        md_abs  = f"file://{BASE}/reports/{period_name}/summary.md"

        f.write(
            f"<li>{period_name.capitalize()}: "
            f"<a href='{csv_abs}'>CSV</a> | "
            f"<a href='{md_abs}'>Summary</a>"
            f"</li>\n"
        )

    f.write("</ul>\n")
    f.write("</body></html>\n")

con.close()

