# License Monitor GUI – Visual Overview & Quick Reference

## 🖥️ Main Window Layout

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ License Monitor Dashboard                                                       │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  📅 Filters & Options                                                            │
│  ┌─────────────────────────────────────────────────────────────────────────────┐ │
│  │ Start Date: [Jan 28, 2026] │ End Date: [Jan 28, 2026] │ Period: [▼]        │ │
│  │                                                                              │ │
│  │ Features:              │ Companies:            │ Users:                      │ │
│  │ ☑ VirtualWafer        │ ☑ acme               │ ☑ acme-user                │ │
│  │ ☑ CustomSim           │ ☑ beta               │ ☑ beta-admin               │ │
│  │ ☑ Designer            │ ☑ partner            │ ☑ partner-xyz              │ │
│  │ ☑ SimEngine           │ ☑ internal           │ ☑ internal-team            │ │
│  │                                                                              │ │
│  │                             [Apply Filters]  [Export CSV]                   │ │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                   │
│  ⏳ [████████░░░░░░░░░░] Loading...                                              │
│                                                                                   │
│  📊 Main Tabs                                                                    │
│  ┌──────────────────────┬──────────────────────┬──────────────────────────────┐ │
│  │ 📈 Usage Trend       │ 📊 Statistics        │ 📋 Details                   │ │
│  ├──────────────────────┼──────────────────────┼──────────────────────────────┤ │
│  │                      │                      │                              │ │
│  │   [Line Chart]       │  Feature │ Snap  │  │  Date │ Company │ Feature │ │
│  │    ╱╲                │  ─────── │ ──── │  │  ──── │ ─────── │ ─────── │ │
│  │   ╱  ╲  ╱╲           │  Virtual │ 450  │  │  2026 │ acme    │ Virtual │ │
│  │  ╱    ╲╱  ╲          │  Wafer   │      │  │  0128 │         │ Wafer   │ │
│  │         ╲  ╱         │  🟢 85%  │      │  │       │ beta    │ Custom  │ │
│  │          ╲╱          │          │      │  │       │         │ Sim     │ │
│  │                      │  Custom  │ 320  │  │  2026 │ partner │ Designer│ │
│  │  ▬ VirtualWafer      │  Sim     │      │  │  0127 │         │         │ │
│  │  ▬ CustomSim         │  🟡 45%  │      │  │       │ internal│ SimEng  │ │
│  │  ▬ Designer          │          │      │  │       │         │         │ │
│  │  ▬ SimEngine         │  Designer│ 280  │  │       │         │         │ │
│  │                      │  🟠 8%   │      │  │                              │ │
│  │                      │  ...     │      │  │                              │ │
│  │                      │          │      │  │  [Scroll for more rows]     │ │
│  │                      │          │      │  │                              │ │
│  │                      │  [Scroll]│      │  │                              │ │
│  │                      │          │      │  │                              │ │
│  └──────────────────────┴──────────────────────┴──────────────────────────────┘ │
│                                                                                   │
│  Status: Ready | Loaded 1,234 records                                            │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🎯 Element Descriptions

### 1. **Filter Panel (Top)**

```
Start Date: [Jan 28, 2026]  End Date: [Jan 28, 2026]
```
- Click date fields to open calendar picker
- Or type directly: YYYY-MM-DD format

```
Period: [Last 7 Days ▼]
```
Options:
- Custom (manual dates)
- Last 7 Days
- Last 30 Days
- Last 90 Days
- Year-to-Date

```
Features:                 Companies:              Users:
☑ VirtualWafer          ☑ acme                  ☑ acme-user
☑ CustomSim             ☑ beta                  ☑ beta-admin
☑ Designer              ☑ partner               ☑ partner-xyz
☑ SimEngine             ☑ internal              ☑ internal-team
```
- Click checkbox to select/deselect
- Click "Select All" to select everything
- Ctrl+Click for range selection
- Shift+Click to toggle all

```
[Apply Filters]         [Export CSV]
```
- **Apply Filters:** Refresh data with current selections
- **Export CSV:** Save filtered data to file

---

### 2. **Progress Bar**

```
⏳ [████████░░░░░░░░░░] Loading...
```
- Visible during data load
- Shows progress (0-100%)
- Disappears when data ready

---

### 3. **📈 Usage Trend Tab**

```
Feature Usage Over Time

    Usage (Hours)
       │
    20├─────────╱╲────────────
       │        ╱  ╲          ╱
    15├───────╱    ╲────────╱─
       │     ╱      ╲      ╱
    10├────╱        ╲────╱───
       │  ╱          ╲  ╱
     5├─╱            ╲╱─────
       │              
     0└─┴──┴──┴──┴──┴──┴──┴──
       Jan  Feb  Mar  Apr  May

    ▬ VirtualWafer (peak at 25h)
    ▬ CustomSim    (peak at 18h)
    ▬ Designer     (peak at 12h)
    ▬ SimEngine    (peak at 8h)
```

**Interactions:**
- Hover over line → Show exact value
- Click + drag → Zoom in
- Right-click → Pan, reset zoom
- Right-click → Save as PNG

---

### 4. **📊 Statistics Tab**

```
Feature     │ Total     │ Unique │ Active │ Avg        │ Utilization
            │ Snapshots │ Users  │ Days   │ Concurrent │ Status
────────────┼───────────┼────────┼────────┼────────────┼──────────────
VirtualWafer│ 450       │ 12     │ 7      │ 8.5        │ 🟢 85%
CustomSim   │ 320       │ 8      │ 7      │ 4.5        │ 🟡 45%
Designer    │ 280       │ 5      │ 6      │ 0.8        │ 🔴 8%
SimEngine   │ 200       │ 6      │ 7      │ 3.2        │ 🟡 32%
Analyzer    │ 120       │ 3      │ 5      │ 1.5        │ 🔴 15%
```

**Color Coding:**
- 🟢 Green: ≥ 80% utilization (EFFECTIVE_USE)
- 🟡 Yellow: 30-80% utilization (PARTIAL_USE)
- 🔴 Red: < 30% utilization (UNDERUTILIZED)

**Click Column Headers to Sort:**
- Feature (A→Z)
- Total Snapshots (low→high)
- Unique Users (low→high)
- Active Days (low→high)
- Avg Concurrent (low→high)
- Utilization (low→high)

---

### 5. **📋 Details Tab**

```
Date       │ Company │ Feature      │ User         │ Snapshots │ Active │ Usage
           │         │              │              │           │ Users  │ Hours
───────────┼─────────┼──────────────┼──────────────┼───────────┼────────┼───────
2026-01-28 │ acme    │ VirtualWafer │ acme-user    │ 100       │ 1      │ 8.33
2026-01-28 │ beta    │ CustomSim    │ beta-admin   │ 75        │ 1      │ 6.25
2026-01-28 │ partner │ Designer     │ partner-xyz  │ 50        │ 1      │ 4.17
2026-01-27 │ acme    │ VirtualWafer │ acme-user    │ 95        │ 1      │ 7.92
2026-01-27 │ internal│ SimEngine    │ internal-team│ 80        │ 1      │ 6.67
2026-01-27 │ acme    │ CustomSim    │ acme-user    │ 60        │ 1      │ 5.00
```

**Features:**
- Click column header to sort
- Scroll down for more rows
- Highlight row → Right-click for copy
- Double-click cell → Edit (read-only, for display)

---

## 🔄 Common Workflows

### Workflow 1: Quick Weekly Check (5 min)

```
1. Open GUI
   ↓
2. Period: "Last 7 Days" (auto-populates dates)
   ↓
3. View "Statistics" tab
   ↓
4. Look for red/yellow rows
   ↓
5. Done! Snapshot recorded.
```

**Output:** Visual summary in head

---

### Workflow 2: Generate Customer Report (10 min)

```
1. Open GUI
   ↓
2. Companies: Select "acme" only
   ↓
3. Period: Last Month
   ↓
4. Click "Export CSV"
   ↓
5. Email file to customer
   ↓
6. Done! Report delivered.
```

**Output:** `acme_usage_jan2026.csv`

---

### Workflow 3: Audit Underutilized Features (15 min)

```
1. Open GUI
   ↓
2. Period: "Year-to-Date"
   ↓
3. View "Statistics" tab
   ↓
4. Sort by "Utilization %" (ascending)
   ↓
5. Red rows at top = underutilized
   ↓
6. Export for decision-makers
   ↓
7. Done! Capacity plan ready.
```

**Output:** Prioritized list of underutilized features

---

### Workflow 4: Troubleshoot Feature (20 min)

```
1. Open GUI
   ↓
2. Features: Select problem feature only
   ↓
3. Period: "Last 7 Days"
   ↓
4. View "Usage Trend" → Identify pattern
   ↓
5. View "Details" → Find users involved
   ↓
6. Cross-check with logs
   ↓
7. Done! Root cause identified.
```

**Output:** Usage pattern + user list

---

## 🎨 Color Reference

| Color | Meaning | Status |
|-------|---------|--------|
| 🟢 Green | ≥ 80% utilization | Healthy, effective use |
| 🟡 Yellow | 30-80% utilization | Balanced, acceptable |
| 🔴 Red | < 30% utilization | Underutilized, consider reducing |

---

## ⌨️ Keyboard Shortcuts

| Action | Keyboard |
|--------|----------|
| Apply Filters | Enter (when in any filter box) |
| Export CSV | Ctrl+S |
| Switch Tabs | Ctrl+Tab (next) / Ctrl+Shift+Tab (prev) |
| Close Window | Alt+F4 (Windows) / Cmd+Q (Mac) |
| Select All (list) | Ctrl+A |
| Deselect All (list) | Ctrl+D |

---

## 📊 Chart Interactions

### Matplotlib Chart Features

```
Legend (top-right)
├─ Hover over line
├─ See exact value in tooltip
├─ Drag to zoom in/out
└─ Right-click for menu

Right-Click Menu
├─ Pan (drag to move around)
├─ Zoom to Rectangle
├─ Reset Original View
├─ Save As... (PNG/PDF/etc)
└─ Configure Subplots (advanced)

Toolbar (below chart)
├─ 🏠 Home (reset view)
├─ ← Back (previous view)
├─ → Forward (next view)
├─ 🔍 Pan
├─ 🔎 Zoom
└─ 💾 Save
```

---

## 🗂️ Data Export Format

### CSV Structure

```csv
date,company,feature,user,snapshot_count,active_users,usage_hours
2026-01-28,acme,VirtualWafer,acme-user,100,1,8.33
2026-01-28,beta,CustomSim,beta-admin,75,1,6.25
...
```

### Use in Excel

```
1. Open exported CSV in Excel
2. Data → Text to Columns (if needed)
3. Create Pivot Table:
   - Rows: Feature
   - Columns: Company
   - Values: Sum of usage_hours
4. Generate charts
```

### Use in Python

```python
import pandas as pd

df = pd.read_csv('export.csv')
df.groupby('feature')['usage_hours'].sum()
df.groupby('company')['usage_hours'].mean()
```

---

## 🚨 Status Bar Messages

| Message | Meaning | Action |
|---------|---------|--------|
| "Ready" | Idle, waiting for input | Click "Apply Filters" |
| "Loading data..." | Fetching from DB | Wait for progress |
| "Loaded X records" | Success | View tabs for data |
| "Error: ..." | Something failed | Check error details |
| "Exported to ..." | CSV saved | File ready to use |

---

## 🎯 Tips & Tricks

### Tip 1: Fast Period Selection
- Don't manually pick dates
- Use "Period" dropdown presets
- Much faster than calendar picker

### Tip 2: Multi-Feature Analysis
- Select 2-3 features max for clear chart
- Too many lines = cluttered chart
- Use Details tab for individual rows

### Tip 3: Filter Combination
1. Filter Features first (few options)
2. Then Companies (medium options)
3. Then Users (many options)
- Narrows data early → Faster queries

### Tip 4: Sorting Details
- Click "Date" header twice to sort descending (recent first)
- Click "Usage Hours" header to sort by duration
- Find peak usage days easily

### Tip 5: Chart Zoom
1. Right-click on chart
2. Select "Zoom to Rectangle"
3. Click + drag to create box
4. Chart zooms into selection
5. Right-click → "Reset Original View" to undo

### Tip 6: Batch Export
- Export once per customer/company
- Rename file with timestamp
- Build report library over time

---

## 🔍 Visual Indicators

### In Statistics Tab

| Indicator | Meaning |
|-----------|---------|
| 🟢 Green highlight | Good utilization (≥ 80%) |
| 🟡 Yellow highlight | Fair utilization (30-80%) |
| 🔴 Red highlight | Poor utilization (< 30%) |
| → (arrow next to number) | Sortable column |
| ✓ (checkmark) | Active filter applied |

### In Details Tab

| Indicator | Meaning |
|-----------|---------|
| 📅 Date column | Snapshot date |
| 👥 Active Users column | Count of unique users |
| ⏱️ Usage Hours column | Computed (snapshots × 5 min ÷ 60) |
| [Scroll bar] | More rows available |

---

## 📈 Interpreting Metrics

### "Total Snapshots"
- Number of 5-minute intervals with activity
- 100 snapshots = ~8.3 hours
- Formula: snapshots × 5 min ÷ 60

### "Unique Users"
- How many different people used the feature
- Higher = broader adoption
- Lower = concentrated use

### "Active Days"
- Calendar days with at least one snapshot
- Out of total period days
- Measure of consistency

### "Avg Concurrent"
- Average licenses in use simultaneously
- Compare to Policy Max
- Drives utilization %

### "Utilization %"
- (Avg Concurrent ÷ Policy Max) × 100
- Green ≥ 80% = effective use
- Red < 30% = over-provisioned

---

## 🎓 Learning Sequence

```
Day 1: Read GUI_QUICKSTART.md (5 min)
       ↓
Day 1: Launch GUI & try Example 1 (5 min)
       ↓
Day 2: Generate 2-3 weekly reports (10 min each)
       ↓
Day 3: Read relevant sections of GUI_README.md (20 min)
       ↓
Day 4: Try Example 3 (Capacity Planning) (15 min)
       ↓
Day 5: Ready for production use! ✅
```

---

*License Monitor GUI – Visual Reference v1.0*
*Quick lookup for UI elements and common tasks*
