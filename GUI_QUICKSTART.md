# Quick Start: License Monitor GUI

## One-Command Launch

### Windows
```batch
cd bin
setup_gui.bat
```

### Linux/macOS
```bash
cd bin
chmod +x setup_gui.sh
./setup_gui.sh
```

---

## What You Get

✅ **Interactive Dashboard** with real-time filtering
✅ **Time-Series Charts** showing license usage trends
✅ **Statistical Analysis** per feature, company, user
✅ **Data Export** to CSV for reporting
✅ **Multi-select Filters** for flexible queries

---

## Key Features

### 1. Flexible Date Selection
- Quick presets: Last 7/30/90 days, Year-to-Date
- Custom date range support
- Auto-loads full data range on startup

### 2. Multi-Dimensional Filtering
```
├─ Features (select one or many)
├─ Companies (filter by customer)
├─ Users (drill down to specific users)
└─ Auto-apply when selections change
```

### 3. Visual Analytics
- **Usage Trend Tab:** Line chart of hours/feature over time
- **Statistics Tab:** Aggregate metrics with utilization status
- **Details Tab:** Row-by-row breakdown with sorting

### 4. Color-Coded Utilization
- 🟢 **Green (≥80%):** Effective utilization
- 🟡 **Yellow (30-80%):** Partial utilization
- 🔴 **Red (<30%):** Underutilized capacity

### 5. Export & Report
- CSV export of filtered data
- Copy/paste friendly table formats
- Integration with Excel, Tableau, Power BI

---

## Database Structure (Automatic)

The GUI reads from the existing license monitor database:

```
db/license_monitor.db
├── lmstat_snapshot       (raw 5-min snapshots)
│   ├── ts (timestamp)
│   ├── user (company-xxxx)
│   ├── feature (VirtualWafer, etc)
│   └── count (concurrent checkouts)
└── license_policy        (MAX limits from options.opt)
```

No additional setup required beyond your existing `init_db.sql`.

---

## Example Workflows

### Scenario 1: Audit Feature X Usage Last Month
1. Set Period → "Last 30 Days"
2. Features → Select only "Feature X"
3. Click **Apply Filters**
4. View **Statistics Tab** → See avg_concurrent vs policy_max
5. Click **Export CSV** → Send to auditor

### Scenario 2: Find Underutilized Licenses
1. Set Period → "Year-to-Date"
2. All filters selected (defaults)
3. View **Statistics Tab**
4. Sort by Utilization % (red rows = underutilized)
5. Plan capacity adjustments

### Scenario 3: Customer Usage Analysis
1. Set date range (week/month)
2. Companies → Select target customer
3. View **Usage Trend** → See their feature pattern
4. Click **Export CSV** → Share with customer

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "No data available" | Run `bin/collect_lmstat.csh` to generate snapshots |
| Missing Python module | Run `pip install -r bin/requirements_gui.txt` |
| Chart rendering slow | Reduce date range or filter by feature |
| Database not found | Verify `db/license_monitor.db` exists |

---

## Next Steps

- **Documentation:** See [GUI_README.md](GUI_README.md) for detailed guide
- **Advanced Features:** Read GUI_README.md → "Advanced Customization"
- **Development:** Extend GUI in `bin/license_monitor_gui.py`

---

For full documentation, see **GUI_README.md** in this directory.
