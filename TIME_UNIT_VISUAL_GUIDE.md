# Time Unit Selector – Visual Guide

## 🎛️ UI Layout with Time Unit Selector

```
┌────────────────────────────────────────────────────────────────────────┐
│ License Monitor Dashboard                                              │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  📅 Filters & Options                                                 │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │ Start Date: [Jan 28, 2026] │ End Date: [Jan 28, 2026]        │   │
│  │ Period: [Last 7 Days ▼]    │ Chart Unit: [Hours ▼]           │   │
│  │                                                                │   │
│  │ Features:    │ Companies:   │ Users:       │ [Apply] [Export] │   │
│  │ ☑ Feature1   │ ☑ Company1   │ ☑ user-xxxx  │                  │   │
│  │ ☑ Feature2   │ ☑ Company2   │ ☑ user-yyyy  │                  │   │
│  └────────────────────────────────────────────────────────────────┘   │
│                                                                        │
│  📊 Main Tabs                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │ 📈 Usage Trend (SELECTED) │ 📊 Statistics │ 📋 Details          │ │
│  ├──────────────────────────────────────────────────────────────────┤ │
│  │                                                                  │ │
│  │   License Usage Over Time (Hours)                               │ │
│  │                                                                  │ │
│  │   Usage (Hours)                                                 │ │
│  │        │                                                        │ │
│  │     20├─────╱╲────────────                                      │ │
│  │        │    ╱  ╲          ╱                                     │ │
│  │     15├───╱    ╲────────╱─                                      │ │
│  │        │  ╱      ╲    ╱                                         │ │
│  │     10├─╱        ╲──╱───                                        │ │
│  │        │╱          ╲                                            │ │
│  │      5├─            ╲────                                       │ │
│  │        │                                                        │ │
│  │      0└─┴─────┴─────┴─────┴─────                                │ │
│  │        1/28   1/29   1/30   1/31    (Date)                      │ │
│  │                                                                  │ │
│  │   ▬ VirtualWafer (peak 22h)                                     │ │
│  │   ▬ CustomSim    (peak 18h)                                     │ │
│  │   ▬ Designer     (peak 12h)                                     │ │
│  │   ▬ SimEngine    (peak 8h)                                      │ │
│  │                                                                  │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                                                        │
│  Status: Ready | Loaded 1,234 records                                 │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 🔄 Switching Units

### Step 1: Locate Chart Unit Selector
```
┌─────────────────────────────────┐
│ Chart Unit: [Hours ▼]           │ ← Click here
└─────────────────────────────────┘
```

### Step 2: Click Dropdown
```
┌─────────────────────────────────┐
│ Chart Unit: [Hours ▼]           │
│            ┌──────────┐         │
│            │ Hours    │ ← Currently selected
│            │ Minutes  │ ← Click to switch
│            └──────────┘         │
└─────────────────────────────────┘
```

### Step 3: Chart Updates Instantly
```
BEFORE (Hours):               AFTER (Minutes):
└──────────────────┘         └──────────────────┘

Usage (Hours)                 Usage (Minutes)
      │                             │
   20├─╱╲                        1200├─╱╲
      │  ╲                          │  ╲
   10├───╲                        600├───╲
      │    ╲                        │    ╲
    0└─────                        0└─────

[Instant update, no delay]      [Chart rescales automatically]
```

---

## 📊 Data Conversion Examples

### Example 1: Single Feature Over 4 Days

```
Date     │ Snapshots │ Minutes  │ Hours
─────────┼───────────┼──────────┼──────
2026-01-28 │   240      │  1,200   │ 20
2026-01-29 │   180      │    900   │ 15
2026-01-30 │   120      │    600   │ 10
2026-01-31 │    60      │    300   │  5

VIEW IN HOURS:
Hours
    │
 20 ├ ●
    │  ╲
 15 ├   ●
    │    ╲
 10 ├     ●
    │      ╲
  5 ├       ●
    │
  0 └───────────
    1/28 1/29 1/30 1/31

VIEW IN MINUTES:
Minutes
       │
  1200 ├ ●
       │  ╲
   900 ├   ●
       │    ╲
   600 ├     ●
       │      ╲
   300 ├       ●
       │
    0  └───────────
      1/28 1/29 1/30 1/31

Same data, different scale!
```

### Example 2: Multiple Features

```
Feature      │ Hours │ Minutes
─────────────┼───────┼────────
VirtualWafer │  20   │  1,200
CustomSim    │  15   │    900
Designer     │  10   │    600
SimEngine    │   5   │    300

IN HOURS VIEW:              IN MINUTES VIEW:
Hours                       Minutes
  │                           │
20├ ●                      1200├ ●
  │  ╲                        │  ╲
15├   ●                     900├   ●
  │    ╲                      │    ╲
10├     ●                    600├     ●
  │      ╲                     │      ╲
 5├       ●                   300├       ●
  │                            │
  └───────                     └───────
  VW CS DE SE                 VW CS DE SE

Legend: ▬ VirtualWafer  ▬ CustomSim  ▬ Designer  ▬ SimEngine
```

---

## 🎨 Chart Title Update

The chart title dynamically reflects the selected unit:

```
With Unit Selector Set to "Hours":
┌──────────────────────────────────┐
│ License Usage Over Time (Hours)  │
└──────────────────────────────────┘

With Unit Selector Set to "Minutes":
┌──────────────────────────────────┐
│ License Usage Over Time (Minutes)│
└──────────────────────────────────┘
```

---

## 🖱️ Interaction Flow

```
User Opens GUI
    ↓
[GUI loads default data in HOURS]
    ↓
Chart displays with Hours scale
Title: "License Usage Over Time (Hours)"
    ↓
User clicks Chart Unit dropdown
    ↓
    ├─ Selects "Hours" → Chart redraws in Hours (Y-axis: 0-20)
    │
    └─ Selects "Minutes" → Chart redraws in Minutes (Y-axis: 0-1200)
         ↓
    [Instant redraw, no data reload needed]
         ↓
    Title updates: "License Usage Over Time (Minutes)"
         ↓
    User can switch back/forth instantly
```

---

## 📱 Responsive Behavior

### Window Size: Large
```
Chart Unit: [Hours ▼]    [Clear dropdown, easy to read]
```

### Window Size: Normal
```
Chart Unit: [Hours ▼]    [Standard spacing]
```

### Window Size: Small (resized)
```
Chart Unit: [Hours ▼]    [Still accessible, might wrap]
```

---

## ⌨️ Keyboard Navigation

```
Tab Key:
Filter Panel → Period Selector → Chart Unit Selector → Features List → ...

Arrow Keys (in dropdown):
↓ : Move to "Minutes"
↑ : Move back to "Hours"

Enter Key:
Select highlighted option
```

---

## 🔍 Comparison Matrix

| Aspect | Hours | Minutes |
|--------|-------|---------|
| **Y-Axis Max** | ~25 | ~1,500 |
| **Granularity** | Coarse | Fine |
| **Scale** | Hours | 300 min per major tick |
| **Best For** | Long-term trends | Short-term spikes |
| **Industry Standard** | ✅ Yes | ✅ Yes (for detailed analysis) |
| **Export Format** | ✅ Both | ✅ Both |
| **Default** | ✅ Yes | - |

---

## 📈 Real-World Example

### Scenario: Troubleshoot License Spike

```
HOURS VIEW (Initial Check):
"Hmm, there's a spike on Jan 28"

Hours
  20 ├ ┌─┐
     │ │ │  ← Spike visible
  15 ├─┘ └─
  10 ├
   5 ├
  0 └─────
    1/27 1/28 1/29

USER CLICKS: Chart Unit → Minutes

MINUTES VIEW (Detailed Analysis):
"The spike was exactly 15 minutes at 10:30 AM"

Minutes
  900 ├ ┌─┐
      │ │ │  ← Spike is 900 minutes (15 hours)
  600 ├─┘ └─
  300 ├
    0 └─────
      1/27 1/28 1/29

✓ Problem identified!
```

---

## 🎯 Quick Reference

### To View in Hours:
1. Click "Chart Unit" dropdown
2. Select "Hours"
3. Chart updates instantly

### To View in Minutes:
1. Click "Chart Unit" dropdown
2. Select "Minutes"
3. Chart updates instantly

### To Export Both:
1. Click "Export CSV"
2. CSV includes `usage_hours` AND `usage_minutes` columns
3. Use whichever in your reports

---

*Time Unit Selector – Visual Reference*
*Easy switching between Hours and Minutes view*
