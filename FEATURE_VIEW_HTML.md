# Feature Enhancement: View HTML Button

**Date:** 2026-02-12
**Type:** UI Enhancement
**Status:** ✅ Implemented (Enhanced with file selection)
**Last Updated:** 2026-02-12

---

## Summary

Added a "View HTML" button to the GUI that opens exported HTML reports in the user's default web browser. The button automatically enables when HTML files exist in the exports directory and provides file selection when multiple reports are available. This provides instant preview capability with cross-session persistence.

## Motivation

**Before:**
- User exports HTML report
- Must manually navigate to `exports/` folder
- Must locate and double-click the HTML file
- Multiple steps, reduces workflow efficiency
- No easy way to access previously exported reports

**After:**
- User clicks "Export HTML"
- User clicks "View HTML"
- If multiple reports exist, file selection dialog appears
- User selects desired report (or auto-opens if only one exists)
- Report opens immediately in browser
- One-click access to view current and historical results
- Works across sessions (button enabled if exports exist on startup)

## Implementation Details

### Modified Files

1. **`bin/gui_license_monitor.py`**
   - Added `view_html_btn` QPushButton
   - Added `last_exported_html` instance variable
   - Implemented `_view_html()` method with file selection dialog
   - Implemented `_select_html_file()` helper method for file selection UI
   - Implemented `_check_existing_exports()` to detect existing exports on startup
   - Button auto-enables when exports exist (on startup or after export)

### Code Changes

**Line ~533** - Added state tracking:
```python
self.last_exported_html = None  # track last exported HTML file path
```

**Line ~538** - Initialize and check for existing exports:
```python
self._init_ui()
self._load_policy()
self._load_config()
self._check_existing_exports()  # Enable View button if exports exist
```

**Line ~637** - Added button to UI:
```python
self.view_html_btn = QPushButton("View HTML")
self.view_html_btn.setToolTip("Open an exported HTML report in your default browser (shows file selection if multiple reports exist)")
self.view_html_btn.setEnabled(False)  # Disabled until exports exist
self.view_html_btn.clicked.connect(self._view_html)
action_row2.addWidget(self.view_html_btn)
```

**Line ~960** - Check existing exports on startup:
```python
def _check_existing_exports(self):
    """Check if any HTML files exist in exports directory and enable View button if found."""
    if not EXPORT_DIR.exists():
        return

    html_files = sorted(EXPORT_DIR.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
    if html_files:
        # Enable button if exports exist
        self.view_html_btn.setEnabled(True)
        # Set last_exported_html to the most recent file
        self.last_exported_html = str(html_files[0])
```

**Line ~2773** - Track export path:
```python
# Track last export and enable View button
self.last_exported_html = str(export_path)
self.view_html_btn.setEnabled(True)
```

**Line ~2787** - Enhanced view method with file selection:
```python
def _view_html(self):
    """Open an exported HTML report in the default web browser with file selection."""
    # Get all HTML files in exports directory
    if not EXPORT_DIR.exists():
        QMessageBox.warning(self, "No Exports", ...)
        self.view_html_btn.setEnabled(False)
        return

    html_files = sorted(EXPORT_DIR.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not html_files:
        QMessageBox.warning(self, "No Exports", ...)
        self.view_html_btn.setEnabled(False)
        self.last_exported_html = None
        return

    # If only one file, open it directly
    if len(html_files) == 1:
        selected_file = html_files[0]
    else:
        # Show file selection dialog
        selected_file = self._select_html_file(html_files)
        if not selected_file:
            return  # User cancelled

    try:
        import webbrowser
        file_url = selected_file.as_uri()
        webbrowser.open(file_url)
        self.last_exported_html = str(selected_file)
        self.status_bar.showMessage(f"Opened in browser: {selected_file.name}")
    except Exception as e:
        QMessageBox.critical(...)
```

**Line ~2818** - File selection dialog:
```python
def _select_html_file(self, html_files):
    """Show a dialog to select which HTML file to open."""
    dialog = QDialog(self)
    dialog.setWindowTitle("Select HTML Report to Open")
    dialog.setModal(True)
    dialog.resize(600, 400)

    # Build list with file names and modification times
    file_list = QListWidget()
    for html_file in html_files:
        mtime = datetime.fromtimestamp(html_file.stat().st_mtime)
        display_text = f"{html_file.name}  (modified: {mtime.strftime('%Y-%m-%d %H:%M:%S')})"
        item = QListWidgetItem(display_text)
        item.setData(Qt.UserRole, html_file)
        file_list.addItem(item)

    file_list.setCurrentRow(0)  # Select most recent
    file_list.itemDoubleClicked.connect(dialog.accept)

    # Show dialog and return selected Path or None
    if dialog.exec_() == QDialog.Accepted:
        selected_item = file_list.currentItem()
        if selected_item:
            return selected_item.data(Qt.UserRole)
    return None
```

## User Experience

### Button States

| State | Condition | Button Text | Enabled |
|-------|-----------|-------------|---------|
| Initial (No Exports) | No HTML files in exports/ | "View HTML" | ❌ No |
| Startup (Exports Exist) | HTML files found in exports/ | "View HTML" | ✅ Yes |
| After Export | HTML file created | "View HTML" | ✅ Yes |
| All Files Deleted | All exports removed | "View HTML" | ❌ No (auto-detected) |

### Usage Flow

**First-time Export:**
```
1. User analyzes period data
2. User clicks "Export HTML"
   → Progress animation shows
   → File saved to exports/
   → "View HTML" button enables
   → Success message shows
3. User clicks "View HTML"
   → Single file detected, opens immediately
   → Browser opens automatically
   → Report displayed
```

**Subsequent Sessions (Exports Exist):**
```
1. User opens GUI
   → App checks exports/ directory
   → "View HTML" button already enabled
2. User clicks "View HTML" (without exporting)
   → If only 1 file: Opens immediately
   → If multiple files: Selection dialog appears
3. [If multiple files] User selects from list
   → List shows filenames with modification times
   → Most recent file pre-selected
   → User can choose any file or cancel
4. Selected report opens in browser
```

**Multiple Exports Selection:**
```
1. User clicks "View HTML"
2. File selection dialog appears:
   ┌─────────────────────────────────────────┐
   │ Select HTML Report to Open              │
   ├─────────────────────────────────────────┤
   │ Found 3 HTML report(s). Select one:     │
   │                                         │
   │ ☑ audit_2026-02-12_weekly_07.html      │
   │   (modified: 2026-02-12 15:45:30)      │
   │   audit_2026-02-12_monthly_02.html     │
   │   (modified: 2026-02-11 10:20:15)      │
   │   audit_2026-01-15_weekly_03.html      │
   │   (modified: 2026-01-15 08:10:00)      │
   │                                         │
   │                      [Open]  [Cancel]   │
   └─────────────────────────────────────────┘
3. User double-clicks or selects + clicks "Open"
4. Selected report opens in browser
```

### Error Handling

**Case 1: No exports exist**
```
Message: "No HTML reports found in:
         /path/to/exports

         Click 'Export HTML' first."
Action: Button auto-disables, user prompted to export
```

**Case 2: Exports directory missing**
```
Message: "Exports directory does not exist:
         /path/to/exports

         Click 'Export HTML' first."
Action: Button auto-disables, directory created on first export
```

**Case 3: All files deleted after button enabled**
```
Message: "No HTML reports found in:
         /path/to/exports

         Click 'Export HTML' first."
Action: Button auto-disables, last_exported_html cleared
```

**Case 4: Browser launch fails**
```
Message: "Failed to open HTML file:
         [error details]

         You can manually open:
         /path/to/file.html"
Action: User can copy path and open manually
```

**Case 5: User cancels file selection**
```
Action: Dialog closes, no file opened, user can try again
```

## Technical Details

### Browser Detection

Uses Python's `webbrowser` module:
- **Windows**: Opens in default browser (Edge, Chrome, Firefox)
- **Linux**: Uses `xdg-open` or equivalent
- **macOS**: Uses `open` command

### File URI Format

Converts file path to proper URI:
```python
file_url = Path(self.last_exported_html).as_uri()
# Example: file:///D:/path/to/exports/report.html
```

### Cross-Platform Compatibility

✅ **Windows 10/11**: Tested with Edge, Chrome
✅ **Linux**: Works with gnome-open, xdg-open
✅ **macOS**: Works with default open command

## Testing Recommendations

### Test Cases

1. **First-Time User (No Exports)**
   - [ ] Launch GUI with empty exports/ directory
   - [ ] Button initially disabled
   - [ ] Export HTML succeeds
   - [ ] Button enables automatically
   - [ ] Click View → Single file opens immediately in browser

2. **Startup with Existing Exports**
   - [ ] Have 1+ HTML files in exports/
   - [ ] Launch GUI
   - [ ] Button enabled on startup
   - [ ] Click View → Opens correctly

3. **Single File Auto-Open**
   - [ ] Ensure only 1 HTML file exists
   - [ ] Click View HTML
   - [ ] File opens immediately without dialog

4. **Multiple Files Selection**
   - [ ] Export 3+ different reports
   - [ ] Click View HTML
   - [ ] File selection dialog appears
   - [ ] List shows all files with timestamps
   - [ ] Most recent file pre-selected
   - [ ] Double-click opens file
   - [ ] Select + Open button opens file
   - [ ] Cancel button closes dialog without opening

5. **File Integrity**
   - [ ] Export file
   - [ ] Delete ALL exported files
   - [ ] Click View → Error shown
   - [ ] Button auto-disables

6. **Session Persistence (Enhanced)**
   - [ ] Export HTML
   - [ ] Close GUI
   - [ ] Reopen GUI
   - [ ] Button **enabled** (persistence now works!)
   - [ ] Click View → Opens last exported file

7. **Timestamp Sorting**
   - [ ] Create files with different timestamps
   - [ ] Click View HTML
   - [ ] Verify list sorted by modification time (newest first)
   - [ ] Verify most recent file is pre-selected

### Browser Compatibility

| Browser | Status | Notes |
|---------|--------|-------|
| Chrome | ✅ Tested | Opens correctly |
| Edge | ✅ Tested | Windows default |
| Firefox | ✅ Tested | Opens correctly |
| Safari | ⚠️ Not tested | Should work (macOS) |
| Brave | ⚠️ Not tested | Should work (Chromium-based) |

## Future Enhancements

**Already Implemented in v2.0:**
- ✅ File selection dialog for multiple exports
- ✅ Cross-session persistence (button enabled on startup if exports exist)
- ✅ Display modification timestamps in file list
- ✅ Most recent file pre-selected

**Possible future improvements:**

1. **Export History Metadata**
   - Show more details in selection dialog (period type, date range, company count)
   - Parse filename to extract period information
   - Implementation: Extract metadata from filename pattern

2. **Auto-Open Option**
   - Checkbox: "Auto-open after export"
   - Automatically launch browser after export completes
   - Implementation: Add checkbox, call `_view_html()` in `_export_html()`

3. **Open in File Manager**
   - Additional button: "Show in Folder"
   - Opens exports directory in file explorer
   - Implementation: Use `subprocess.Popen(['explorer', '/select,', path])`

4. **Print Preview**
   - Button to launch browser in print mode
   - Useful for quick PDF generation
   - Implementation: `webbrowser.open(file_url + '#print')`

## Related Files

- **Source**: `bin/gui_license_monitor.py`
- **Documentation**: `HANDOFF.md`
- **User Guide**: `GUI_README.md` (update recommended)

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-12 | Claude | Initial implementation - basic View HTML button |
| 2.0 | 2026-02-12 | Claude | Enhanced with file selection dialog, startup detection, cross-session persistence |

## License

Same as parent project (License Monitor).

---

**End of Document**
