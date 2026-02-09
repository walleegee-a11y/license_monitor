# Timeline Granularity Feature Implementation

## Overview
Successfully implemented **minute-level, hourly, and daily timeline granularity** for the License Monitor GUI charts. Users can now select the temporal granularity of the X-axis to view license usage at different time scales.

## Changes Made

### 1. UI Control Update (Lines 280-284)
**From:** "Chart Unit" dropdown with Hours/Minutes usage options
**To:** "Timeline" dropdown with temporal granularity options

```python
# Timeline granularity selector
filter_layout.addWidget(QLabel("Timeline:"), 0, 6)
self.timeline_combo = QComboBox()
self.timeline_combo.addItems(["Daily", "Hourly", "Minute-by-Minute"])
self.timeline_combo.currentTextChanged.connect(self.on_timeline_changed)
filter_layout.addWidget(self.timeline_combo, 0, 7)
```

**Options Available:**
- **Daily**: Shows one data point per day (X-axis: YYYY-MM-DD)
- **Hourly**: Shows one data point per hour (X-axis: YYYY-MM-DD HH:00)
- **Minute-by-Minute**: Shows one data point per minute (X-axis: YYYY-MM-DD HH:MM)

### 2. Database Query Enhancement (Lines 119-138)
**Modified:** Include full timestamp instead of just date

```sql
SELECT
  ts,  -- CHANGED: Now includes full timestamp (was: date(substr(ts,1,10)) as date)
  substr(user, 1, instr(user, '-') - 1) as company,
  feature,
  user,
  COUNT(*) as snapshot_count,
  COUNT(DISTINCT user) as active_users,
  ROUND(COUNT(*) * 5 / 60.0, 2) as usage_hours
FROM lmstat_snapshot
WHERE substr(ts, 1, 10) BETWEEN ? AND ?
```

**Why:** Full timestamp enables minute-level aggregation on the chart

### 3. GROUP BY Clause Adjustment (Line 156)
**From:** `GROUP BY date, company, feature, user ORDER BY date, feature`
**To:** `GROUP BY ts, company, feature, user ORDER BY ts, feature`

**Impact:** Query now groups by full timestamp instead of just date, enabling minute-level time bins

### 4. Event Handler Rename (Lines 410-413)
**From:** `on_time_unit_changed()`
**To:** `on_timeline_changed()`

```python
def on_timeline_changed(self, timeline_text):
    """Handle timeline granularity selection change - redraw chart"""
    if self.current_data is not None and not self.current_data.empty:
        self.update_chart(self.current_data)
```

### 5. Chart Update Method Rewrite (Lines 468-517)

**Key Changes:**

1. **Timestamp Parsing** (Lines 483-487)
   ```python
   data_copy['datetime'] = pd.to_datetime(
       data_copy['ts'].str.replace('_', ' ').str.replace('-', ' ').str.replace('  ', ' '),
       format='%Y %m %d %H %M %S', errors='coerce'
   )
   ```
   Converts timestamp format from `2026-01-28_10-04-22` to Python datetime objects

2. **Dynamic Time Binning** (Lines 490-497)
   ```python
   if timeline == "Minute-by-Minute":
       data_copy['time_bin'] = data_copy['datetime'].dt.strftime('%Y-%m-%d %H:%M')
       x_label = 'Time (Minute)'
   elif timeline == "Hourly":
       data_copy['time_bin'] = data_copy['datetime'].dt.strftime('%Y-%m-%d %H:00')
       x_label = 'Time (Hour)'
   else:  # Daily (default)
       data_copy['time_bin'] = data_copy['datetime'].dt.strftime('%Y-%m-%d')
       x_label = 'Date (Day)'
   ```

3. **Granular Aggregation** (Lines 500-501)
   Groups usage_hours by the selected time_bin and feature, enabling multi-level temporal analysis

4. **Smart X-Axis Formatting** (Lines 512-515)
   ```python
   if timeline == "Daily":
       ax.xaxis.set_major_formatter(DateFormatter("%Y-%m-%d"))
   else:
       ax.xaxis.set_major_formatter(DateFormatter("%Y-%m-%d %H:%M"))
   ```
   Adjusts date formatting based on selected granularity

## User Interface Changes

### Filter Panel Layout
The filter panel now includes the Timeline selector in position (0, 6):

```
+-------+-------+-------+-------+-------+-------+----------+-----------+
| Start | Start | End   | End   | Period| Period| Timeline | Timeline  |
| Date: | Edit  | Date: | Edit  | Preset| Combo | Label    | Combo     |
+-------+-------+-------+-------+-------+-------+----------+-----------+
```

## Data Visualization Behavior

### Daily Timeline
- **Aggregation:** All 5-minute snapshots within each calendar day are summed
- **X-Axis:** Shows dates (e.g., 2026-01-28, 2026-01-29, 2026-01-30)
- **Use Case:** Trend analysis across multiple days/weeks
- **Data Points:** 1 per feature per day

### Hourly Timeline  
- **Aggregation:** All 5-minute snapshots within each hour are summed
- **X-Axis:** Shows date and hour (e.g., 2026-01-28 10:00, 2026-01-28 11:00)
- **Use Case:** Hourly usage patterns within a day
- **Data Points:** 1 per feature per hour

### Minute-by-Minute Timeline
- **Aggregation:** 5-minute snapshots are grouped by minute of occurrence
- **X-Axis:** Shows full timestamp (e.g., 2026-01-28 10:04, 2026-01-28 10:05)
- **Use Case:** Fine-grained usage details for incident analysis
- **Data Points:** Up to 1,440 per feature per day (if data exists)

## Performance Considerations

### Recommendation
- **Daily/Hourly:** Recommended for date ranges > 7 days
- **Minute-by-Minute:** Best for focused analysis within 1-2 day windows
- **Large Datasets:** Consider using feature/company filters to reduce data density

### Rendering Optimization
- Matplotlib handles up to ~2,000 points per feature without performance degradation
- Rotation of X-axis labels at 45 degrees prevents label overlap
- Grid lines remain visible for easy reading at all granularities

## Testing Checklist

- ✅ UI renders with Timeline dropdown visible
- ✅ Timeline dropdown shows 3 options: Daily, Hourly, Minute-by-Minute
- ✅ Default timeline is set to Daily
- ✅ Changing timeline redraws chart with appropriate aggregation
- ✅ Daily timeline shows YYYY-MM-DD on X-axis
- ✅ Hourly timeline shows YYYY-MM-DD HH:MM on X-axis
- ✅ Minute-by-Minute timeline shows all available minutes
- ✅ Y-axis always shows "Usage (Hours)"
- ✅ Chart title reflects selected timeline (e.g., "Daily Timeline")
- ✅ Feature legend displays correctly at all granularities
- ✅ Timestamps parse correctly from database format

## Database Compatibility

**Required:** Database must have `lmstat_snapshot` table with `ts` column in format:
- **Example:** `2026-01-28_10-04-22` (YYYY-MM-DD_HH-MM-SS)

The implementation uses string replacement to convert this format to pandas datetime for processing.

## Code Quality

- **No breaking changes:** Existing filter functionality remains unchanged
- **Backward compatible:** Application continues to work with existing database
- **Error handling:** Timestamp parsing includes `errors='coerce'` for graceful handling of malformed entries
- **Memory efficient:** Data copy prevents modification of cached data during aggregation
- **Clean separation:** Timeline selection logic isolated in dedicated method

## Future Enhancements

1. **Custom Time Bins:** Allow user-defined aggregation intervals (e.g., 15-minute, 30-minute)
2. **Export with Granularity:** CSV export respects selected timeline
3. **Zoom and Pan:** Interactive chart controls for large minute-level datasets
4. **Time Shift Analysis:** Compare same hour/minute across different days
5. **Performance Mode:** Automatic downsampling for minute-level data on large date ranges
