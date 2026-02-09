# License Monitor GUI – Practical Examples & Use Cases

## Use Case 1: Weekly Audit Preparation

**Goal:** Generate a weekly usage report for all features and identify underutilized licenses

### Steps:

1. **Launch GUI**
   ```bash
   bin/setup_gui.sh
   ```

2. **Apply Filters**
   - Period: Select "Last 7 Days"
   - Features: Select all (default)
   - Companies: Select all (default)

3. **Navigate to Statistics Tab**
   - View summary metrics
   - Look for **Red** rows (< 30% utilization)
   - Note features with low usage

4. **Drill Down on Underutilized Feature**
   - Features: Unselect all, select only "VirtualWafer"
   - Click **Apply Filters**
   - View **Usage Trend** tab → See if usage is consistent or sporadic
   - View **Details** tab → Identify which users are using it

5. **Export Results**
   - Click **Export CSV**
   - Save as `weekly_audit_2026-01-28.csv`
   - Share with licensing team

### Expected Output:

```
CSV contains:
Date,Company,Feature,User,Snapshots,Active Users,Usage Hours
2026-01-28,acme-xxxx,VirtualWafer,acme-user,100,1,8.33
2026-01-28,acme-yyyy,VirtualWafer,acme-user,50,1,4.17
...

Statistics show:
Feature: VirtualWafer | Total Snapshots: 150 | Users: 2 | Avg Concurrent: 0.5
Policy Max: 10 | Utilization: 5% | Status: UNDERUTILIZED (Red)
```

### Time Required: ~5 minutes

---

## Use Case 2: Customer Usage Analysis (External Partner)

**Goal:** Show customer "ACME Corp" their usage of specific features over the last month

### Steps:

1. **Launch GUI**

2. **Set Date Range**
   - Start: January 1, 2026
   - End: January 31, 2026

3. **Filter by Company**
   - Companies: Select only "acme" (will show acme-xxxx, acme-yyyy, acme-zzzz)
   - Apply Filters

4. **Review Usage Trend Tab**
   - Shows ACME's usage pattern over the month
   - Demonstrates peak usage days
   - Validates feature adoption

5. **Generate Customer Report**
   - Statistics Tab: Extract key metrics
   - Export CSV: `acme_usage_jan2026.csv`
   - Format for customer (add header, timestamp)

### Sample Report (CSV):

```csv
ACME Corp - License Usage Report (January 2026)

Date,Feature,Snapshots,Active Users,Usage Hours
2026-01-01,CustomSim,50,2,4.17
2026-01-02,CustomSim,100,3,8.33
2026-01-03,VirtualWafer,75,1,6.25
...
2026-01-31,CustomSim,120,4,10.0

Summary:
Total Usage Hours: 184.5
Avg Concurrent Users: 2.5
Features Used: 2 (CustomSim, VirtualWafer)
Peak Usage Day: January 15 (24 hours)
```

### Time Required: ~10 minutes

---

## Use Case 3: Cost Projection & Capacity Planning

**Goal:** Identify which features need license increases in Q1 2026

### Steps:

1. **Launch GUI**

2. **Set Period**
   - Period: "Year-to-Date" (Jan 1 - Jan 28, 2026)

3. **View Statistics Tab**
   - Sort by **Avg Concurrent** (descending)
   - Features with high concurrent usage show high demand

4. **Identify Bottlenecks**
   - Feature "SimEngine": Avg Concurrent = 8.5, Policy Max = 10 (85% utilization) ✅ OK
   - Feature "Designer": Avg Concurrent = 12.0, Policy Max = 10 (120% utilization) ⚠️ OVER
   - Feature "Analyzer": Avg Concurrent = 2.0, Policy Max = 10 (20% utilization) ✅ OK

5. **Export for Capacity Planning**
   - Export CSV: `q1_utilization_report.csv`
   - Use to request license increases for "Designer"
   - Document over-subscription incidents

### Decisions:

```
Current License Pool:
├─ SimEngine: 10 licenses (85% used) → Keep as is
├─ Designer: 10 licenses (120% used) → REQUEST 5 MORE (→15 total)
└─ Analyzer: 10 licenses (20% used) → Reduce to 5 (save cost)

Estimated Annual Savings: $50,000 (from reducing Analyzer)
Estimated Additional Cost: $30,000 (for Designer increase)
Net Impact: Save $20,000/year + resolve bottleneck
```

### Time Required: ~15 minutes

---

## Use Case 4: Troubleshoot License Checkout Failures

**Goal:** User reports "License Not Available" error. Investigate why and when.

### Steps:

1. **Launch GUI**

2. **Filter by Problem Feature**
   - Features: Select "CustomSim" (the failing tool)
   - Start Date: 3 days ago
   - End Date: Today

3. **View Usage Trend Tab**
   - Look for usage pattern → Spike at time of failure?
   - Usage appears consistently high (no gaps)

4. **View Details Tab**
   - Sort by **Date** descending
   - Find entries from time of failure (e.g., Jan 28, 10:00 AM)
   - See who was using licenses: users acme-user, beta-admin

5. **Check Against Policy Max**
   - Statistics Tab shows: Avg Concurrent = 10.0, Policy Max = 10
   - **Root Cause:** License pool fully exhausted (10/10 licenses in use)
   - Not a bug, but a capacity issue

6. **Recommendations**
   - Add more licenses
   - Implement license scheduling/queuing
   - Educate users on peak hours

### Investigation Results:

```
Feature: CustomSim
Policy Max: 10 licenses
Avg Concurrent Usage (Last 3 Days): 9.8 licenses
Peak Concurrent: 10.0 licenses (Jan 28, 10:15 AM)

Users Active During Failure:
- acme-user (simultaneous checkout)
- beta-admin (simultaneous checkout)
- partner-xyz (simultaneous checkout)

Conclusion: All 10 licenses in use when user tried to check out.
Recommendation: Increase pool to 15 licenses or implement queuing.
```

### Time Required: ~20 minutes

---

## Use Case 5: Quarterly Executive Summary

**Goal:** Present usage metrics to executives; show ROI on license investments

### Steps:

1. **Launch GUI**

2. **Set Period**
   - Start: October 1, 2025
   - End: December 31, 2025

3. **Generate All Metrics**
   - Statistics Tab: Capture key numbers
   - Export CSV: `q4_2025_executive_summary.csv`

4. **Create Presentation Slide**

   ```
   QUARTERLY SUMMARY – Q4 2025
   
   Total Features: 5
   Total Users: 45
   Total Usage: 1,250 hours
   
   Feature Breakdown:
   ┌─────────────────┬───────────┬──────────────┬───────────────┐
   │ Feature         │ Users     │ Utilization  │ Status        │
   ├─────────────────┼───────────┼──────────────┼───────────────┤
   │ SimEngine       │ 32        │ 85%          │ ✅ Healthy    │
   │ Designer        │ 28        │ 110%         │ ⚠️  Over-used  │
   │ CustomSim       │ 18        │ 45%          │ 📊 Balanced   │
   │ VirtualWafer    │ 12        │ 15%          │ ⚠️  Underused  │
   │ Analyzer        │ 8         │ 8%           │ ⚠️  Underused  │
   └─────────────────┴───────────┴──────────────┴───────────────┘
   
   Investment ROI:
   Total License Cost: $200,000
   Effective Usage: 85% average
   Utilization Score: B+ (Target: 70-90%)
   
   Recommendation:
   - Increase Designer licenses (+20%)
   - Consider reducing VirtualWafer, Analyzer (save $30K)
   ```

5. **Attach CSV & Charts**
   - Include export CSV
   - Embed Usage Trend chart from GUI
   - Provide filtering logic for drill-down

### Time Required: ~30 minutes

---

## Use Case 6: Compliance & Audit Trail

**Goal:** Document license usage for compliance audit (SOX, HIPAA, etc.)

### Steps:

1. **Launch GUI**

2. **Set Audit Period**
   - Start: January 1, 2026 (fiscal year start)
   - End: December 31, 2026 (or current date)

3. **Generate Full Dataset**
   - Features: Select all
   - Companies: Select all
   - Click **Export CSV**

4. **Create Audit Report Structure**
   ```
   License Usage Audit Report – FY 2026
   Generated: January 28, 2026
   Audit Period: January 1 – December 31, 2026
   
   1. Executive Summary
   2. Data Collection Methodology (every 5 minutes via lmstat)
   3. Database Integrity Verification
   4. Feature-by-Feature Usage Breakdown
   5. Policy Compliance Certification
   6. Attached Data (CSV)
   ```

5. **Verify Data Completeness**
   - Check for gaps in snapshots (if any → explain)
   - Confirm all features are included
   - Validate user naming convention

6. **Submit to Auditor**
   - Main CSV file (anonymized if needed)
   - Audit report PDF
   - Methodology documentation

### Audit Checklist:

```
☐ Data Collection: Automated every 5 minutes
☐ Data Retention: All snapshots preserved (append-only)
☐ Database Backup: Verified backup procedures
☐ Policy Enforcement: Policy MAX limits documented
☐ User Accountability: User IDs logged for all checkouts
☐ Segregation of Duties: IT operates collection, Business reviews reports
☐ Change Management: Policy updates logged (ingest_policy.py)
☐ Report Accuracy: Cross-verified with make_reports.py output
```

### Time Required: ~45 minutes (mostly preparation, 5 min for GUI)

---

## Use Case 7: Real-Time Monitoring (Ad-hoc)

**Goal:** Monitor license availability during a critical project period (live)

### Steps:

1. **Launch GUI**

2. **Set Short Time Window**
   - Period: "Last 7 Days"
   - This captures current + recent history

3. **Focus on Critical Feature**
   - Features: Select "SimEngine" only
   - Companies: Select customer company (e.g., "acme")

4. **Watch Usage Trend Tab**
   - Refresh every 5-10 minutes (manually)
   - Look for:
     - Consistent high usage → Good adoption
     - Spikes → Project milestone
     - Drops → Issue or end of usage

5. **Real-Time Decision Making**
   ```
   10:00 AM: Usage at 8/10 → Continue monitoring
   10:30 AM: Usage at 9/10 → Alert team
   11:00 AM: Usage at 10/10 → Check if users waiting
   11:30 AM: Usage drops to 6/10 → Relax, shift complete
   ```

6. **Escalate if Needed**
   - If stuck at 10/10 for > 30 min → Request emergency license increase
   - If pattern repeats → Permanent increase needed

### Real-Time Report Template:

```
REAL-TIME LICENSE MONITORING – SimEngine

Current Time: Jan 28, 2026 2:00 PM
Period Monitored: Last 7 Days

Current Usage: 9.5 / 10 licenses (95%)
Trend: ↗ Increasing (was 7.0 yesterday same time)

Active Users: 5
├─ acme-user (2 checkouts)
├─ beta-admin (1 checkout)
├─ partner-xyz (1 checkout)
└─ internal-team (1 checkout)

Forecast: Peak expected at 3:00 PM (based on trend)
Action: Monitor next hour; prepare for overflow

Last Updated: 2:00 PM EST
Next Update: 2:05 PM EST (automated)
```

### Time Required: ~5 minutes (per check)

---

## Use Case 8: Bulk User Report (For All Users)

**Goal:** Send each customer their personalized usage report

### Steps:

1. **Launch GUI**

2. **Loop Through Each Company**
   ```
   For each company in [acme, beta, partner, internal]:
     - Companies: Select company
     - Period: Set to relevant period (e.g., Last Month)
     - Export CSV: company_usage_[period].csv
     - Email: Report to company contact
   ```

3. **Automate Script (Optional)**
   ```bash
   #!/bin/bash
   for company in acme beta partner internal; do
     python bin/license_monitor_gui.py \
       --period "last_month" \
       --company "$company" \
       --export "reports/${company}_usage_dec2025.csv"
   done
   ```

4. **Email Template**
   ```
   Subject: Your License Usage Report – December 2025
   
   Dear [Company Name],
   
   Attached is your personalized license usage report for December 2025.
   
   Key Metrics:
   - Total Usage Hours: 450
   - Average Concurrent Users: 3.2
   - Features Used: 3
   - Peak Usage Day: Dec 15 (8 hours)
   
   Questions? Contact: licensing@company.com
   
   Best regards,
   License Management Team
   ```

### Time Required: ~30 minutes (for 5 companies, ~6 min each)

---

## Quick Reference: Common Filter Combinations

### Report Type | Filters | Output
|---|---|---|
| **Audit (All Data)** | All features, companies, users; YTD | Full CSV, 50K+ rows |
| **Customer Quarterly** | Select customer; 3-month period | Summary CSV + stats |
| **Underutilized** | All; sort by util % | Red features only |
| **Peak Usage** | Feature; Last 30 days | Charts + top days |
| **User Drill-Down** | Feature + user; Custom period | Row-by-row detail |
| **Capacity Plan** | All features; YTD | Utilization summary |
| **Compliance** | All; FY date range | Archived dataset |
| **Troubleshoot** | Problem feature; 7 days | Usage pattern + users |

---

## Tips & Tricks

### Speed Up Large Queries
1. Use **Period Presets** (faster than custom dates)
2. Filter by **Feature First** (narrows rows early)
3. Filter by **Company Second** (further reduction)

### Best Chart Visualization
- Feature count ≤ 5: Good for line chart
- Feature count > 5: Use Statistics tab instead

### Export for Spreadsheet Analysis
1. Export CSV from GUI
2. Open in Excel
3. Create pivot table: Rows=Date, Columns=Feature, Values=Usage Hours
4. Add trendline

### Batch Processing
```bash
# Use make_reports.py for automated batch
csh -f bin/run_reports.csh
# This generates all reports automatically (faster than GUI for large datasets)
```

---

## Troubleshooting Guide

| Problem | Cause | Solution |
|---------|-------|----------|
| "No data available" | Empty database | Run `bin/collect_lmstat.csh` to generate data |
| Chart very flat | Single user / feature | Try different period or features |
| Slow chart rendering | Too many rows | Reduce date range or filter features |
| Missing users | They didn't check out licenses | Normal; only active users appear |
| Policy Max shows 0 | Policy not ingested | Run `bin/ingest_policy.py` |
| Export button disabled | No data loaded | Click Apply Filters first |

---

## Integration with Existing Workflow

### Before (Batch Reports Only)
```
make_reports.py (weekly)
  ↓
CSV files (static)
  ↓
Email to users
  ↓
Users manually analyze
```

### After (Batch + GUI)
```
make_reports.py (weekly)      [Automated batch]
  ↓
CSV files (static)
  ↓
Email to users

+ 

GUI on demand             [Interactive analysis]
  ↓
Real-time filtering
  ↓
Immediate insights
  ↓
Ad-hoc export
```

Both modes coexist and complement each other.

---

## Performance Benchmarks

### Test Scenario: 1 Year Data (50K Snapshots)

| Operation | GUI | Batch Reports |
|-----------|-----|----------------|
| Load all data | 2-3s | 5-10s |
| Filter by feature | <1s | 10-20s |
| Generate chart | 3-5s | N/A |
| Export CSV | 1-2s | Auto |
| User interaction | Real-time | N/A |

**Recommendation:** GUI for < 90 days, Batch for full-year reporting

---

*Practical Examples v1.0 | License Monitor GUI Use Cases*
