# License Monitor GUI Dashboard

## Overview

The **License Monitor GUI Dashboard** is an interactive PyQt5-based application that provides real-time visualization and analysis of FlexLM license usage data. It enables users to track license utilization across different time periods, features, companies, and users with intuitive filtering and charting capabilities.

---

## Features

### 🎯 Key Capabilities

1. **Multi-Dimensional Filtering**
   - Date range selection with quick preset periods
   - Feature filtering (multi-select)
   - Company filtering (multi-select)
   - User filtering (multi-select)

2. **Visual Analytics**
   - Time-series line charts showing usage trends over time
   - Per-feature usage visualization
   - Interactive matplotlib-based plotting

3. **Statistical Summaries**
   - Total snapshots per feature
   - Unique users per feature
   - Active days in period
   - Average concurrent usage
   - Utilization status (color-coded: Green ≥80%, Yellow 30-80%, Red <30%)

4. **Detailed Reporting**
   - Row-by-row usage breakdown
   - Date, company, feature, user, snapshot count, active users, usage hours
   - Sortable and searchable tables

5. **Data Export**
   - Export filtered data to CSV for further analysis
   - Compatible with Excel and other tools

---

## Installation

### Prerequisites

- **Python 3.7+** (3.10+ recommended)
- **pip** package manager

### Setup Steps

#### On Windows

1. Open Command Prompt in the `bin/` directory
2. Run:
   ```batch
   setup_gui.bat
   ```

#### On Linux/macOS

1. Open terminal in the `bin/` directory
2. Make script executable:
   ```bash
   chmod +x setup_gui.sh
   ```
3. Run:
   ```bash
   ./setup_gui.sh
   ```

### Manual Installation

If you prefer manual setup:

```bash
pip install -r requirements_gui.txt
export LICENSE_MONITOR_HOME=/path/to/license_monitor
python license_monitor_gui.py
```

---

## Usage Guide

### Starting the Application

**Windows:**
```batch
bin\setup_gui.bat
```

**Linux/macOS:**
```bash
bin/setup_gui.sh
```

Or directly with Python:
```bash
python bin/license_monitor_gui.py
```

### Main Interface

The application window is divided into several sections:

#### 1. **Filter Panel** (Top)

```
┌─────────────────────────────────────────────────────────────┐
│ Start Date: [Jan 28, 2026] End Date: [Jan 28, 2026]        │
│ Period: [Last 30 Days ▼]                                    │
│                                                              │
│ Features:           Companies:           Users:             │
│ ☑ Feature1          ☑ Company1           ☑ user-xxxx       │
│ ☑ Feature2          ☑ Company2           ☑ user-yyyy       │
│                                                              │
│                    [Apply Filters] [Export CSV]             │
└─────────────────────────────────────────────────────────────┘
```

**Elements:**

- **Start Date / End Date:** Select custom date ranges
- **Period:** Quick presets:
  - Last 7 Days
  - Last 30 Days
  - Last 90 Days
  - Year-to-Date
  - Custom (manual dates)

- **Features List:** Multi-select from available license features
- **Companies List:** Filter by company (extracted from username prefix)
- **Users List:** Filter by specific user accounts
- **Apply Filters:** Manually refresh data with current filter settings
- **Export CSV:** Save filtered results to CSV file

#### 2. **Tabs**

**📈 Usage Trend Tab**
- Line chart showing usage (in hours) over time
- One line per feature
- Interactive matplotlib plot (zoom, pan, save capabilities)
- X-axis: Dates
- Y-axis: Usage hours

**📊 Statistics Tab**
- Aggregated metrics per feature:
  - Feature name
  - Total snapshots (5-minute intervals)
  - Unique users
  - Active days in period
  - Average concurrent usage
  - Utilization % (color-coded)

**📋 Details Tab**
- Row-by-row breakdown
- Columns: Date, Company, Feature, User, Snapshots, Active Users, Usage Hours
- Sortable by clicking column headers

### Workflow Examples

#### Example 1: Check Last Month's Usage for Feature X

1. Set **Period** to "Last 30 Days" → Dates auto-populate
2. In **Features**, unselect all except "Feature X"
3. Click **Apply Filters**
4. View results in:
   - **Usage Trend** tab: See usage pattern over 30 days
   - **Statistics** tab: See summary metrics
   - **Details** tab: See day-by-day breakdown

#### Example 2: Analyze Specific Customer Usage

1. Set date range (e.g., Last 7 Days)
2. In **Companies**, select only the target company
3. Click **Apply Filters**
4. Review **Usage Trend** to see customer's feature usage
5. Click **Export CSV** to send to customer

#### Example 3: Find Underutilized Licenses

1. Set period to "Year-to-Date"
2. View **Statistics** tab
3. Look for red-highlighted rows (< 30% utilization)
4. Filter by those features for deeper analysis

---

## Data Interpretation

### Metrics Explained

| Metric | Definition | Example |
|--------|-----------|---------|
| **Usage Count** | Number of 5-min snapshots with activity | 100 = ~8.3 hours |
| **Active Users** | Distinct users in period | 5 users |
| **Active Snapshots** | Number of unique time intervals | 100 snapshots |
| **Usage Hours** | Usage count × 5 minutes ÷ 60 | 8.33 hours |
| **Avg Concurrent** | Mean concurrent checkouts | 2.5 licenses in use |
| **Policy Max** | License policy limit (from options.opt) | 10 licenses |
| **Utilization %** | avg_concurrent / policy_max | 25% = underutilized |

### Utilization Status Colors

| Status | Range | Color | Meaning |
|--------|-------|-------|---------|
| **EFFECTIVE_USE** | ≥ 80% | 🟢 Green | Well-utilized |
| **PARTIAL_USE** | 30–80% | 🟡 Yellow | Moderate use |
| **UNDERUTILIZED** | < 30% | 🔴 Red | Excess capacity |

---

## Performance Tips

### Large Datasets

If you have several months of data:

1. **Use Period Presets:** Faster than custom date picking
2. **Filter by Feature:** Select specific features to reduce rows
3. **Filter by Company:** Narrow to relevant customers
4. **Export for Heavy Analysis:** Use CSV export + external tools (Excel, Tableau)

### Display Optimization

- Keep the detail table **sorted** by clicking column headers
- Use **Statistics** tab for high-level overview
- Use **Details** tab only when needed for drilling down

---

## Keyboard Shortcuts

| Action | Windows | Linux/macOS |
|--------|---------|------------|
| Apply Filters | `Enter` (in filter box) | `Return` |
| Export | `Ctrl+S` | `Cmd+S` |
| Switch Tabs | `Ctrl+Tab` | `Cmd+Tab` |
| Exit | `Alt+F4` | `Cmd+Q` |

---

## Troubleshooting

### Issue: "No data available" message

**Cause:** Database is empty or filters are too restrictive

**Solution:**
1. Check database path: `db/license_monitor.db` exists
2. Verify lmstat collection is running (check `log/collect.log`)
3. Remove all filters and try again

### Issue: Slow chart rendering

**Cause:** Too much data selected

**Solution:**
1. Reduce date range
2. Filter by specific features
3. Export to CSV for bulk analysis

### Issue: "ModuleNotFoundError: No module named 'PyQt5'"

**Cause:** Dependencies not installed

**Solution:**
```bash
pip install -r bin/requirements_gui.txt
```

### Issue: Chart not updating after filter change

**Cause:** Data loading in background

**Solution:**
1. Wait for progress bar to complete
2. Check status bar message
3. Try clicking **Apply Filters** again

---

## Advanced Customization

### Changing Chart Style

Edit `license_monitor_gui.py`, function `update_chart()`:

```python
# Add grid style
ax.grid(True, alpha=0.3, linestyle='--')

# Change colors
colors = ['#FF6B6B', '#4ECDC4', '#45B7D1']
for idx, line in enumerate(ax.get_lines()):
    line.set_color(colors[idx % len(colors)])
```

### Adding New Metrics

Edit `update_stats_table()` to add columns:

```python
# Add cost column (example)
self.stats_table.setColumnCount(7)  # Was 6
self.stats_table.setHorizontalHeaderLabels([
    ..., "Estimated Cost"
])
# Add data fetch and calculation
```

### Connecting to Remote Database

Edit constructor:

```python
DB_PATH = "sqlite:///remote_path/license_monitor.db"
# Or use MySQL/PostgreSQL with SQLAlchemy
```

---

## Architecture

### Component Overview

```
┌─────────────────────────────────────────┐
│   LicenseMonitorGUI (Main Window)       │
├─────────────────────────────────────────┤
│   • init_ui()         - Build UI         │
│   • apply_filters()   - Load data        │
│   • update_chart()    - Plot graphs      │
│   • export_data()     - CSV export       │
└─────────────────────────────────────────┘
          ↓ uses ↓
┌─────────────────────────────────────────┐
│   DatabaseManager                       │
├─────────────────────────────────────────┤
│   • get_features()    - Unique features  │
│   • get_companies()   - Unique companies │
│   • query_usage_data()- Query with filters
│   • get_summary_stats()- Aggregated stats
└─────────────────────────────────────────┘
          ↓ uses ↓
┌─────────────────────────────────────────┐
│   SQLite Database                       │
│   (license_monitor.db)                  │
└─────────────────────────────────────────┘
```

### Threading

- **DataLoaderThread:** Loads data without blocking UI
- Prevents "Not Responding" during large queries
- Emits signals when complete

---

## Future Enhancements

### Planned Features

1. **Dashboard Presets**
   - Save/load favorite filter combinations
   - One-click reports

2. **Advanced Analytics**
   - Anomaly detection (usage spikes)
   - Trend forecasting
   - Cost projections

3. **Alerting Integration**
   - Email alerts for over-usage
   - Slack notifications

4. **Database Comparison**
   - Side-by-side period analysis
   - Year-over-year trends

5. **Report Scheduling**
   - Auto-generate weekly/monthly PDFs
   - Email distribution

---

## Support

For issues, questions, or feature requests:

1. Check logs: `log/gui.log`
2. Review database: `sqlite3 db/license_monitor.db .tables`
3. Test data connection: Use **Statistics** tab to verify data exists

---

*License Monitor GUI v1.0 | Built with PyQt5 and Matplotlib*
