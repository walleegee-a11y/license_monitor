# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- HTML export progress tracking with detailed step-by-step updates
  - Shows progress bar with percentage (0-100%)
  - Displays current step (e.g., "rendering chart", "[1/2] company stats")
  - Calculates total steps dynamically based on number of companies
  - Matches Analyze button UX for consistency
- View HTML button with cross-session persistence and file selection
  - Auto-enables button on startup if exports directory contains HTML files
  - Shows file selection dialog when multiple reports exist
  - Lists files with modification timestamps, most recent pre-selected
  - Auto-opens single file without dialog for streamlined UX
  - Supports double-click and Open button in selection dialog
- Spinner animations on Analyze and Export HTML buttons while running
- Color states (blue/orange/green/red) for both Analyze and Export HTML buttons
- Analyze button color feedback with states: blue (default), orange (running), green (done), red (error)
- Peak concurrent and utilization % metrics across SQL views, reports, and GUI
  - v_concurrent_snapshot view to count simultaneous checkouts per snapshot
  - v_peak_weekly/monthly/quarterly/yearly views for MAX concurrent per period
  - Extended all v_usage_*_ext views with peak_concurrent and utilization_pct columns
  - New columns in make_reports.py CSV output and summary definitions
  - Expanded GUI stats table to show Peak Concurrent, Policy Max, and Utilization %
- Auto-select features and users when company filter changes
  - Build company→features and company→users mappings from policy data
  - Automatically select associated features and users based on options.opt policy definitions
- Show all policy features with zero usage in feature filter, Statistics table, and chart policy overlay
- Ingest Lmstat and Ingest Policy buttons to GUI
  - IngestThread QThread subclass for background execution
  - Proper button disabling during execution
  - Status bar feedback and error dialogs
  - Automatic policy reload on completion
- PEBBLESQUARE_Verdi group with Verdi policy to options.opt
- Project documentation
  - .gitignore to exclude runtime data, Python cache, tool metadata
  - README, ARCHITECTURE, GUI guides, examples
  - Timeline/time-unit implementation notes
  - FEATURE_VIEW_HTML.md: Comprehensive feature documentation
- Shell scripts: lmstat collection, ingestion, report generation, setup scripts (csh + bat/sh for GUI)
- init_db.sql schema, requirements_gui.txt, conf/ settings
- bulk_ingest.py and check_db.py utilities

### Changed
- Start HTML export spinner immediately on button click for instant visual feedback
  - Move animation start before date parsing and filename computation
  - Add processEvents() calls between heavy computation steps to keep spinner smooth
- Replace Quick period buttons with granularity+period combo selectors
  - Two-combo approach: granularity selector + specific period dropdown (e.g. Week-02, Month-11, Quarter-03, Year-2026)
  - Quick period and Custom Period date pickers are now mutually exclusive
  - Both use the same Analyze workflow for consistent chart rendering
- Redefine avg_concurrent as time-weighted (usage_hours / period_hours) instead of snapshot-based
- Split utilization_pct into active_utilization_pct (when in use) and period_utilization_pct (over full period capacity)
- Adjust utilization thresholds: EFFECTIVE_USE >= 60%, PARTIAL_USE >= 20%
- Add ETTIFOS_Verdi policy group, expand CIRCLE_PT group members
- Update Verdi MAX to 1
- Rename 'Avg Concurrent' to 'Avg When Active' with tooltips explaining metrics
- Add Scale dropdown (Auto/5min/Hourly/Daily/Weekly/Monthly) for granularity control
- Increase granularity thresholds: 5min up to 7 days, hourly up to 31 days
- Add 0.1x padding to chart edges for better Now line visibility
- Remove value annotations from chart (rely on Statistics table for accurate numbers)
- Rename 'Utilization' to 'Active Util. %' and 'Hours Util. %' to 'Period Util. %'
- Reorder left pane: Companies (50%), Features (40%), Users (10%)
- Period Selection vs Actions panel ratio set to 70:30
- Remove fallback period heuristics for manual date selections
  - Only use period labels (weekly-03, etc.) when quick period selector is active
  - Manual date ranges now always use date range format
- Implement GROUP-based policy format for options.opt
  - Company now derived from GROUP name prefix (split on underscore) instead of username convention
  - MAX applies as shared concurrent limit across all users in group
  - Convert to GROUP-based definitions in options.opt
  - Parse multi-user GROUPs, derive company from group name
  - Add CREATE TABLE IF NOT EXISTS with PRIMARY KEY (user, feature) in ingest_policy.py
  - LEFT JOIN license_policy in v_usage_base for company
  - Use aggregated subquery in all _ext views to prevent row duplication
  - Filter users via policy_users set with USER_RE fallback in ingest_lmstat.py
  - 4-tuple policy rows, user_company_map for parsing in gui_license_monitor.py
  - Two-step aggregation (MAX within company, SUM across) in _policy_map_for_users
- Revert options.opt to CIRCLE_PT example group (after filtering fix)
- Update options.opt to use CIRCLE_PT example group

### Fixed
- Grid toggle warning by only passing alpha parameter to ax.grid() when grid is enabled
- Make company tab bar sticky in exported HTML for easy navigation
- Fix single-item period selection by adding placeholder prompt in period combo
- Defer analysis until user explicitly picks a period item
- Fix HTML export naming to use period labels (weekly-03, monthly-08, yearly)
  - Use quick period selector for accurate period classification
  - Simplify filename to timestamp + ordinal
- Fix spiky Usage Trend chart by using steps-post drawing for Line/Area/Step chart types
  - Short sessions now render as flat plateaus instead of thin spikes
  - Accurately reflects duration on x-axis
- Fix hours decimal display to show 2 decimal places using NumericSortItem
  - Small values like 0.08 now visible instead of showing as 0
- Fix user filtering that caused empty Features/Companies/Users display
  - Parser and ingest scripts no longer skip users not found in policy table
  - Users not in policy fall back to dash-split company derivation
  - v_usage_base now handles usernames without a dash
- Fix broken get_summary_stats() in GUI (AVG(count) always returned 1.0)
  - Compute concurrent counts per snapshot then aggregate avg/peak
- Fix company-user cascading filter
  - User filter now updates to show only users belonging to selected companies
  - Preserves previous selections when possible
- Fix empty statistics columns by converting numpy types to native Python int/float for PyQt5 rendering
- Fix PEBBLESQUARE typo in policy definitions

### Documentation
- Add FEATURE_VIEW_HTML.md with comprehensive View HTML feature documentation
- Update HANDOFF.md with View HTML implementation examples
- Add .gitignore, README, ARCHITECTURE, GUI guides, examples, and implementation notes
- Add reset_views.csh with DROP statements for new views

---

*Generated by Claude Code on 2026-02-12*
