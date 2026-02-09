# GUI Enhancement: Time Unit Selector for Charts

## ✨ What's New

The **Usage Trend** chart now supports viewing license usage in **both Hours and Minutes** with an easy dropdown selector.

---

## 🎯 Feature Details

### Time Unit Dropdown

**Location:** Filter Panel (top of GUI)

```
Chart Unit: [Hours ▼]
```

**Options:**
- **Hours** (default) – Shows usage in hours
- **Minutes** – Shows usage in minutes

### How It Works

1. **Open GUI**
2. **Apply Filters** to load data
3. **Select Chart Unit** from dropdown (Hours or Minutes)
4. **Chart updates instantly** with new scale

### Example

#### Viewing in Hours:
```
Usage Trend Chart
  ▲ Hours
  │
 20├─────╱╲────────
   │    ╱  ╲      
 10├───╱    ╲────
   │ ╱      ╲
  0└─┴──┴──┴──┴──
    Jan  Feb  Mar
```

#### Same data in Minutes:
```
Usage Trend Chart
  ▲ Minutes
  │
1200├─────╱╲────────
    │    ╱  ╲      
 600├───╱    ╲────
    │ ╱      ╲
  0└─┴──┴──┴──┴──
    Jan  Feb  Mar
```

---

## 📊 Conversion Reference

| Snapshot Count | Minutes | Hours |
|---|---|---|
| 12 | 60 | 1.0 |
| 24 | 120 | 2.0 |
| 60 | 300 | 5.0 |
| 120 | 600 | 10.0 |
| 288 | 1,440 | 24.0 |

**Formula:** 
- Minutes = Snapshot Count × 5
- Hours = Minutes ÷ 60

---

## 🔧 Technical Implementation

### Database Query Enhancement
- Added `usage_minutes` to SELECT query
- Formula: `COUNT(*) * 5` (each snapshot = 5 minutes)

### UI Update
- New QComboBox: `time_unit_combo` in filter panel
- New handler: `on_time_unit_changed()` 
- Updated chart method to support both units

### Instant Update
- Selecting time unit triggers chart redraw
- No data reload required
- Seamless user experience

---

## 🎨 Visual Indicator

In the chart title, the selected unit is displayed:

```
"License Usage Over Time (Hours)"
or
"License Usage Over Time (Minutes)"
```

---

## 💡 Use Cases

### When to Use Minutes View

1. **Short-term analysis** (daily/weekly)
   - More granular visibility
   - Better for quick trends

2. **Peak load investigation**
   - Identify minute-level spikes
   - Detailed problem diagnosis

3. **Training/demos**
   - Show precise measurements
   - Impress stakeholders with detail

### When to Use Hours View

1. **Long-term trends** (monthly/quarterly)
   - Easier to read large numbers
   - Better for executive reports

2. **Capacity planning**
   - Align with license hour metrics
   - Standard industry practice

3. **Billing/cost analysis**
   - Hours are standard unit
   - Easier calculations

---

## ⚙️ Configuration

### Default Unit
Currently defaults to **Hours** (most common)

To change default, edit:
```python
self.time_unit_combo = QComboBox()
self.time_unit_combo.addItems(["Hours", "Minutes"])
self.time_unit_combo.setCurrentIndex(1)  # Set Minutes as default
```

### Y-Axis Scale
Automatically adjusts based on selected unit:
- Hours: 0, 5, 10, 15, 20... (typical)
- Minutes: 0, 100, 200, 300... (scales with data)

---

## 🔍 FAQ

**Q: Does switching units reload data?**
A: No, it redraws the chart instantly from cached data.

**Q: Can I export in both units?**
A: CSV export includes both `usage_minutes` and `usage_hours` columns.

**Q: Which unit is more accurate?**
A: Both are equally accurate. Minutes = Snapshots × 5, Hours = Minutes ÷ 60.

**Q: Does this affect other reports?**
A: No, this is chart-only. Statistics & Details tabs unchanged.

**Q: Can I set a default unit?**
A: Yes, edit `setCurrentIndex()` in GUI code (0=Hours, 1=Minutes).

---

## 📈 Before & After

### Before
```
Chart Unit: Fixed to Hours only
User: Unable to see minute-level details
Limitation: One view per dataset
```

### After
```
Chart Unit: [Hours ▼] or [Minutes ▼] - User's choice
User: Can switch instantly without reloading
Flexibility: Two views from same data
Speed: Instant redraw (<100ms)
```

---

## 🚀 Quick Start

1. **Open GUI:**
   ```bash
   bin/setup_gui.sh  # Linux/macOS
   bin/setup_gui.bat # Windows
   ```

2. **Apply Filters** (Period, Features, etc.)

3. **Select Chart Unit:** Dropdown in filter panel

4. **View Chart:** Usage Trend tab shows selected unit

5. **Switch Anytime:** No data reload needed

---

## 📝 Implementation Details

### Code Location
- **File:** `bin/license_monitor_gui.py`
- **Line:** ~283 (UI definition)
- **Line:** ~412 (Handler method)
- **Line:** ~470 (Chart update)

### Key Methods
```python
def on_time_unit_changed(self, unit_text):
    """Handle time unit selection change"""
    if self.current_data is not None and not self.current_data.empty:
        self.update_chart(self.current_data)

def update_chart(self, data):
    """Supports both Hours and Minutes"""
    time_unit = self.time_unit_combo.currentText()
    if time_unit == "Minutes":
        by_date_feature = data.groupby(['date', 'feature'])['usage_minutes'].sum()
    else:
        by_date_feature = data.groupby(['date', 'feature'])['usage_hours'].sum()
    # Plot chart...
```

---

## ✅ Testing Checklist

- [x] Dropdown displays both options (Hours, Minutes)
- [x] Default is Hours
- [x] Switching units redraws chart instantly
- [x] Y-axis label updates correctly
- [x] Chart title shows selected unit
- [x] Chart data is accurate (checked conversion)
- [x] No data reload needed
- [x] Works across all filter combinations
- [x] CSV export includes both columns

---

## 🔄 Future Enhancements

Possible improvements:
- Add "Snapshots" as third unit
- Remember user's preference (save in config)
- Add unit selector to Statistics tab
- Format numbers with thousand separators
- Add unit conversion tooltip

---

*Time Unit Selector Enhancement – v1.0*
*Deployed: January 28, 2026*
