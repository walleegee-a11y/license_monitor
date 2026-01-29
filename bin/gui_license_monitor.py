#!/usr/local/python-3.12.2/bin/python3.12
"""
License Monitor - Usage Analysis Dashboard
===============================================================================
Interactive PyQt5 GUI that reads raw lmstat files, parses them on-demand,
and displays interactive time-series charts with auto-scaled X-axis.

Data source: raw/lmstat/lmstat_YYYY-MM-DD_HH-MM-SS.txt
Optional:    db/license_monitor.db (license_policy table for policy_max overlay)
===============================================================================
"""

import sys
import os
import re
import glob
import sqlite3
from datetime import datetime, date
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QDateEdit, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QTabWidget, QGroupBox, QGridLayout, QMessageBox,
    QFileDialog, QProgressBar, QStatusBar, QListWidget, QListWidgetItem,
    QAbstractItemView, QFrame,
)
from PyQt5.QtCore import Qt, QDate, QThread, pyqtSignal
from PyQt5.QtGui import QColor

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.dates import DateFormatter

import pandas as pd


# ============================================================
# Configuration
# ============================================================

BASE_DIR = Path(os.environ.get(
    "LICENSE_MONITOR_HOME",
    Path(__file__).parent.parent
))
RAW_DIR = BASE_DIR / "raw" / "lmstat"
DB_PATH = BASE_DIR / "db" / "license_monitor.db"

USER_RE = re.compile(r"^[a-z0-9]+-[a-z]{4}$")


# ============================================================
# LmstatParser — parse raw lmstat files
# ============================================================

class LmstatParser:
    """Static methods to parse raw lmstat snapshot files."""

    @staticmethod
    def scan_files(raw_dir, start_date, end_date):
        """Return list of file paths whose date falls within [start_date, end_date]."""
        pattern = str(Path(raw_dir) / "lmstat_*.txt")
        all_files = sorted(glob.glob(pattern))
        matched = []
        for fp in all_files:
            fname = Path(fp).name
            # lmstat_2026-01-28_10-04-22.txt → 2026-01-28
            m = re.match(r"lmstat_(\d{4}-\d{2}-\d{2})_", fname)
            if not m:
                continue
            file_date = date.fromisoformat(m.group(1))
            if start_date <= file_date <= end_date:
                matched.append(fp)
        return matched

    @staticmethod
    def parse_file(filepath):
        """Parse a single lmstat file.

        Returns list of dicts: {ts, feature, user, company, host}
        """
        fname = Path(filepath).name
        # lmstat_2026-01-28_10-04-22.txt → 2026-01-28 10:04:22
        ts_str = fname.replace("lmstat_", "").replace(".txt", "")
        ts_str = ts_str.replace("_", " ", 1)
        parts = ts_str.split(" ")
        if len(parts) == 2:
            date_part = parts[0]
            time_part = parts[1].replace("-", ":")
            ts_str = f"{date_part} {time_part}"

        records = []
        current_feature = None

        try:
            with open(filepath, encoding="utf-8", errors="replace") as f:
                for raw_line in f:
                    line = raw_line.rstrip()

                    # Feature header: "Users of FeatureName:  (Total of X licenses..."
                    if line.startswith("Users of ") and "licenses issued" in line:
                        m = re.match(r"Users of ([^:]+):", line)
                        if m:
                            current_feature = m.group(1).strip()
                        continue

                    if not current_feature:
                        continue

                    # Skip empty / metadata / quoted lines
                    if not line.strip() or line.lstrip().startswith('"'):
                        continue

                    # User checkout line: 4-space indent (not 6+), contains " start "
                    if line.startswith("    ") and not line.startswith("      ") and " start " in line:
                        tokens = line.split()
                        if len(tokens) < 2:
                            continue
                        user = tokens[0]
                        host = tokens[1]

                        if not USER_RE.match(user):
                            continue

                        company = user.split("-")[0]
                        records.append({
                            "ts": ts_str,
                            "feature": current_feature,
                            "user": user,
                            "company": company,
                            "host": host,
                        })
        except Exception:
            pass

        return records


# ============================================================
# PolicyLoader — optional DB policy_max lookup
# ============================================================

class PolicyLoader:
    """Load policy_max per (user, feature) from license_policy table if available."""

    @staticmethod
    def load(db_path):
        """Return dict  {feature: max_across_users}  or empty dict on failure."""
        policy = {}
        try:
            if not Path(db_path).exists():
                return policy
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()
            # Check if table exists
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='license_policy'"
            )
            if not cur.fetchone():
                conn.close()
                return policy
            cur.execute("SELECT feature, MAX(policy_max) FROM license_policy GROUP BY feature")
            for row in cur.fetchall():
                if row[0] and row[1]:
                    policy[row[0]] = int(row[1])
            conn.close()
        except Exception:
            pass
        return policy


# ============================================================
# AnalyzerThread — background file parsing
# ============================================================

class AnalyzerThread(QThread):
    """Background thread that scans and parses raw lmstat files."""

    analysis_complete = pyqtSignal(object, int)   # (DataFrame, file_count)
    progress = pyqtSignal(int)                     # percentage 0-100
    error_occurred = pyqtSignal(str)

    def __init__(self, raw_dir, start_date, end_date):
        super().__init__()
        self.raw_dir = raw_dir
        self.start_date = start_date
        self.end_date = end_date

    def run(self):
        try:
            files = LmstatParser.scan_files(self.raw_dir, self.start_date, self.end_date)
            total = len(files)
            if total == 0:
                self.analysis_complete.emit(pd.DataFrame(), 0)
                return

            all_records = []
            for idx, fp in enumerate(files):
                recs = LmstatParser.parse_file(fp)
                all_records.extend(recs)
                pct = int((idx + 1) / total * 100)
                self.progress.emit(pct)

            if all_records:
                df = pd.DataFrame(all_records)
            else:
                df = pd.DataFrame(columns=["ts", "feature", "user", "company", "host"])

            self.analysis_complete.emit(df, total)

        except Exception as e:
            self.error_occurred.emit(str(e))


# ============================================================
# Helper: time-bin aggregation and X-axis scaling
# ============================================================

def determine_granularity(start_date, end_date):
    """Return (granularity_label, strftime_fmt, tick_format) based on period length."""
    delta = (end_date - start_date).days
    if delta <= 2:
        return "5min", "%Y-%m-%d %H:%M", "%H:%M"
    elif delta <= 7:
        return "hourly", "%Y-%m-%d %H:00", "%m-%d %H:00"
    elif delta <= 31:
        return "daily", "%Y-%m-%d", "%Y-%m-%d"
    elif delta <= 93:
        return "weekly", None, "%G-W%V"   # special handling
    else:
        return "monthly", "%Y-%m", "%Y-%m"


def assign_time_bin(dt, granularity, bin_fmt):
    """Assign a datetime to a time-bin string."""
    if granularity == "5min":
        minute = (dt.minute // 5) * 5
        binned = dt.replace(minute=minute, second=0, microsecond=0)
        return binned.strftime(bin_fmt)
    elif granularity == "weekly":
        iso = dt.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    else:
        return dt.strftime(bin_fmt)


def aggregate_by_time_bin(df, start_date, end_date):
    """Group df by time bin and feature, counting concurrent licenses.

    Returns (aggregated_df, granularity_label, tick_format).
    """
    if df.empty:
        return df, "daily", "%Y-%m-%d"

    granularity, bin_fmt, tick_fmt = determine_granularity(start_date, end_date)

    df = df.copy()
    df["datetime"] = pd.to_datetime(df["ts"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
    df.dropna(subset=["datetime"], inplace=True)

    df["time_bin"] = df["datetime"].apply(lambda dt: assign_time_bin(dt, granularity, bin_fmt))

    # Concurrent licenses per feature per time bin = count of checkout rows
    agg = (
        df.groupby(["time_bin", "feature"])
        .agg(
            concurrent=("user", "size"),
            unique_users=("user", "nunique"),
        )
        .reset_index()
    )

    return agg, granularity, tick_fmt


# ============================================================
# Main GUI Application
# ============================================================

class LicenseMonitorGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("License Monitor - Usage Analysis Dashboard")
        self.setGeometry(80, 80, 1450, 950)

        self.raw_data = None          # full parsed DataFrame (all records)
        self.filtered_data = None     # after filter selection
        self.analyzer_thread = None
        self.policy_map = {}          # {feature: policy_max}

        self._init_ui()
        self._load_policy()

    # --------------------------------------------------------
    # UI construction
    # --------------------------------------------------------
    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout()

        # ---- Period Selection ----
        period_group = QGroupBox("Period Selection")
        period_layout = QVBoxLayout()

        # Quick buttons row
        quick_row = QHBoxLayout()
        quick_row.addWidget(QLabel("Quick:"))
        for label, days in [("Weekly", 7), ("Monthly", 30), ("Quarterly", 90), ("Yearly", 365)]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked, d=days: self._quick_period(d))
            quick_row.addWidget(btn)
        quick_row.addStretch()
        period_layout.addLayout(quick_row)

        # Custom date row
        custom_row = QHBoxLayout()
        custom_row.addWidget(QLabel("Custom:"))
        custom_row.addWidget(QLabel("Start"))
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDate(QDate.currentDate().addDays(-7))
        custom_row.addWidget(self.start_date_edit)
        custom_row.addWidget(QLabel("End"))
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDate(QDate.currentDate())
        custom_row.addWidget(self.end_date_edit)
        custom_row.addStretch()
        period_layout.addLayout(custom_row)

        period_group.setLayout(period_layout)
        root.addWidget(period_group)

        # ---- Separator ----
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        root.addWidget(sep)

        # ---- Filters ----
        filter_group = QGroupBox("Filters (populated after Analyze)")
        filter_layout = QGridLayout()

        filter_layout.addWidget(QLabel("Features:"), 0, 0)
        self.feature_list = QListWidget()
        self.feature_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.feature_list.setMaximumHeight(100)
        self.feature_list.itemSelectionChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.feature_list, 0, 1)

        filter_layout.addWidget(QLabel("Companies:"), 0, 2)
        self.company_list = QListWidget()
        self.company_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.company_list.setMaximumHeight(100)
        self.company_list.itemSelectionChanged.connect(self._on_company_filter_changed)
        filter_layout.addWidget(self.company_list, 0, 3)

        filter_layout.addWidget(QLabel("Users:"), 0, 4)
        self.user_list = QListWidget()
        self.user_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.user_list.setMaximumHeight(100)
        self.user_list.itemSelectionChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.user_list, 0, 5)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.analyze_btn = QPushButton("Analyze")
        self.analyze_btn.setMinimumWidth(120)
        font = self.analyze_btn.font()
        font.setBold(True)
        self.analyze_btn.setFont(font)
        self.analyze_btn.clicked.connect(self._run_analyze)
        btn_row.addWidget(self.analyze_btn)

        self.export_btn = QPushButton("Export CSV")
        self.export_btn.setMinimumWidth(120)
        self.export_btn.clicked.connect(self._export_csv)
        btn_row.addWidget(self.export_btn)
        btn_row.addStretch()
        filter_layout.addLayout(btn_row, 1, 0, 1, 6)

        filter_group.setLayout(filter_layout)
        root.addWidget(filter_group)

        # ---- Progress bar ----
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        root.addWidget(self.progress_bar)

        # ---- Tabs ----
        self.tabs = QTabWidget()

        # Tab 1: Usage Trend chart
        chart_widget = QWidget()
        chart_layout = QVBoxLayout()
        self.figure = Figure(figsize=(12, 5), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        chart_layout.addWidget(self.canvas)
        chart_widget.setLayout(chart_layout)
        self.tabs.addTab(chart_widget, "Usage Trend")

        # Tab 2: Statistics table
        self.stats_table = QTableWidget()
        self.stats_table.setColumnCount(8)
        self.stats_table.setHorizontalHeaderLabels([
            "Feature", "Total Checkouts", "Unique Users", "Active Days",
            "Avg Concurrent", "Peak Concurrent", "Policy Max", "Utilization",
        ])
        self.stats_table.horizontalHeader().setStretchLastSection(True)
        self.stats_table.setSortingEnabled(True)
        self.tabs.addTab(self.stats_table, "Statistics")

        # Tab 3: Details table
        self.detail_table = QTableWidget()
        self.detail_table.setColumnCount(5)
        self.detail_table.setHorizontalHeaderLabels([
            "Timestamp", "Feature", "User", "Company", "Host",
        ])
        self.detail_table.horizontalHeader().setStretchLastSection(True)
        self.detail_table.setSortingEnabled(True)
        self.tabs.addTab(self.detail_table, "Details")

        root.addWidget(self.tabs, stretch=1)

        # ---- Status bar ----
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready. Select a period and click Analyze.")

        central.setLayout(root)

    # --------------------------------------------------------
    # Policy loading (optional)
    # --------------------------------------------------------
    def _load_policy(self):
        self.policy_map = PolicyLoader.load(DB_PATH)

    # --------------------------------------------------------
    # Quick period buttons
    # --------------------------------------------------------
    def _quick_period(self, days):
        today = QDate.currentDate()
        self.start_date_edit.setDate(today.addDays(-days))
        self.end_date_edit.setDate(today)
        self._run_analyze()

    # --------------------------------------------------------
    # Analyze workflow
    # --------------------------------------------------------
    def _run_analyze(self):
        start_qd = self.start_date_edit.date()
        end_qd = self.end_date_edit.date()
        start = date(start_qd.year(), start_qd.month(), start_qd.day())
        end = date(end_qd.year(), end_qd.month(), end_qd.day())

        if start > end:
            QMessageBox.warning(self, "Invalid range", "Start date must be before end date.")
            return

        self.analyze_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_bar.showMessage("Scanning files...")

        self.analyzer_thread = AnalyzerThread(str(RAW_DIR), start, end)
        self.analyzer_thread.progress.connect(self._on_progress)
        self.analyzer_thread.analysis_complete.connect(self._on_analysis_complete)
        self.analyzer_thread.error_occurred.connect(self._on_analysis_error)
        self.analyzer_thread.start()

    def _on_progress(self, pct):
        self.progress_bar.setValue(pct)

    def _on_analysis_complete(self, df, file_count):
        self.raw_data = df
        self.analyze_btn.setEnabled(True)
        self.progress_bar.setVisible(False)

        # Populate filter lists — all selected by default
        self._populate_filters(df)

        # Apply filters (initially everything selected) → draw chart + tables
        self._apply_and_refresh()

        start_str = self.start_date_edit.date().toString("yyyy-MM-dd")
        end_str = self.end_date_edit.date().toString("yyyy-MM-dd")
        rec_count = len(df)
        self.status_bar.showMessage(
            f"Analyzed {file_count} files, {rec_count} records  |  "
            f"Period: {start_str} to {end_str}"
        )

    def _on_analysis_error(self, msg):
        self.analyze_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage(f"Error: {msg}")
        QMessageBox.critical(self, "Analysis Error", msg)

    # --------------------------------------------------------
    # Filter population
    # --------------------------------------------------------
    def _populate_filters(self, df):
        # Block signals while populating to avoid repeated refreshes
        self.feature_list.blockSignals(True)
        self.company_list.blockSignals(True)
        self.user_list.blockSignals(True)

        self.feature_list.clear()
        self.company_list.clear()
        self.user_list.clear()

        if not df.empty:
            for feat in sorted(df["feature"].unique()):
                item = QListWidgetItem(feat)
                self.feature_list.addItem(item)
                item.setSelected(True)

            for comp in sorted(df["company"].unique()):
                item = QListWidgetItem(comp)
                self.company_list.addItem(item)
                item.setSelected(True)

            for usr in sorted(df["user"].unique()):
                item = QListWidgetItem(usr)
                self.user_list.addItem(item)
                item.setSelected(True)

        self.feature_list.blockSignals(False)
        self.company_list.blockSignals(False)
        self.user_list.blockSignals(False)

    # --------------------------------------------------------
    # Filter change → instant re-draw (no re-parse)
    # --------------------------------------------------------
    def _on_filter_changed(self):
        if self.raw_data is not None:
            self._apply_and_refresh()

    def _on_company_filter_changed(self):
        """When company selection changes, update user list to show only related users."""
        if self.raw_data is None or self.raw_data.empty:
            return

        sel_companies = self._get_selected(self.company_list)

        # Filter users to those belonging to selected companies
        if sel_companies:
            related_users = sorted(
                self.raw_data[self.raw_data["company"].isin(sel_companies)]["user"].unique()
            )
        else:
            related_users = []

        # Preserve currently selected users that still exist in the new list
        prev_selected = set(self._get_selected(self.user_list))

        self.user_list.blockSignals(True)
        self.user_list.clear()
        for usr in related_users:
            item = QListWidgetItem(usr)
            self.user_list.addItem(item)
            # Select if previously selected, or select all if none were previously selected
            item.setSelected(usr in prev_selected if prev_selected else True)
        # If nothing ended up selected, select all
        if not self.user_list.selectedItems() and self.user_list.count() > 0:
            for i in range(self.user_list.count()):
                self.user_list.item(i).setSelected(True)
        self.user_list.blockSignals(False)

        self._apply_and_refresh()

    def _get_selected(self, list_widget):
        return [item.text() for item in list_widget.selectedItems()]

    def _apply_and_refresh(self):
        if self.raw_data is None or self.raw_data.empty:
            self.filtered_data = pd.DataFrame()
            self._update_chart(self.filtered_data)
            self._update_stats(self.filtered_data)
            self._update_details(self.filtered_data)
            return

        sel_features = self._get_selected(self.feature_list)
        sel_companies = self._get_selected(self.company_list)
        sel_users = self._get_selected(self.user_list)

        mask = pd.Series(True, index=self.raw_data.index)
        if sel_features:
            mask &= self.raw_data["feature"].isin(sel_features)
        else:
            mask &= False
        if sel_companies:
            mask &= self.raw_data["company"].isin(sel_companies)
        else:
            mask &= False
        if sel_users:
            mask &= self.raw_data["user"].isin(sel_users)
        else:
            mask &= False

        self.filtered_data = self.raw_data[mask].copy()

        self._update_chart(self.filtered_data)
        self._update_stats(self.filtered_data)
        self._update_details(self.filtered_data)

    # --------------------------------------------------------
    # Chart (Usage Trend tab)
    # --------------------------------------------------------
    def _update_chart(self, df):
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        if df.empty:
            ax.text(0.5, 0.5, "No data available", ha="center", va="center",
                    transform=ax.transAxes, fontsize=14, color="gray")
            self.canvas.draw()
            return

        start_qd = self.start_date_edit.date()
        end_qd = self.end_date_edit.date()
        start_d = date(start_qd.year(), start_qd.month(), start_qd.day())
        end_d = date(end_qd.year(), end_qd.month(), end_qd.day())

        agg, granularity, tick_fmt = aggregate_by_time_bin(df, start_d, end_d)

        if agg.empty:
            ax.text(0.5, 0.5, "No data after aggregation", ha="center", va="center",
                    transform=ax.transAxes, fontsize=14, color="gray")
            self.canvas.draw()
            return

        # Convert time_bin back to datetime for plotting
        if granularity == "weekly":
            # "2026-W04" → Monday of that ISO week
            agg["plot_dt"] = agg["time_bin"].apply(
                lambda s: datetime.strptime(s + "-1", "%G-W%V-%u")
            )
        elif granularity == "monthly":
            agg["plot_dt"] = pd.to_datetime(agg["time_bin"] + "-01")
        else:
            agg["plot_dt"] = pd.to_datetime(agg["time_bin"])

        # Plot one line per feature
        features = sorted(agg["feature"].unique())
        for feat in features:
            fdata = agg[agg["feature"] == feat].sort_values("plot_dt")
            ax.plot(fdata["plot_dt"], fdata["concurrent"],
                    marker="o", linewidth=2, markersize=4, label=feat)

        # Policy overlay (dashed horizontal lines)
        for feat in features:
            if feat in self.policy_map:
                ax.axhline(y=self.policy_map[feat], linestyle="--", linewidth=1.2, alpha=0.7,
                           label=f"{feat} MAX={self.policy_map[feat]}")

        # Axis formatting
        ax.set_ylabel("Concurrent Licenses", fontsize=11, fontweight="bold")
        ax.set_xlabel("Time", fontsize=11, fontweight="bold")
        ax.xaxis.set_major_formatter(DateFormatter(tick_fmt))
        self.figure.autofmt_xdate(rotation=45)
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best", fontsize=8, ncol=2)

        # Dynamic title
        gran_labels = {
            "5min": "5-Minute",
            "hourly": "Hourly",
            "daily": "Daily",
            "weekly": "Weekly",
            "monthly": "Monthly",
        }
        period_label = gran_labels.get(granularity, granularity)
        ax.set_title(
            f"License Usage \u2014 {period_label} View ({start_d} to {end_d})",
            fontsize=13, fontweight="bold",
        )

        self.figure.tight_layout()
        self.canvas.draw()

    # --------------------------------------------------------
    # Statistics tab
    # --------------------------------------------------------
    def _update_stats(self, df):
        self.stats_table.setSortingEnabled(False)
        self.stats_table.setRowCount(0)

        if df.empty:
            self.stats_table.setSortingEnabled(True)
            return

        df = df.copy()
        df["datetime"] = pd.to_datetime(df["ts"], format="%Y-%m-%d %H:%M:%S", errors="coerce")

        features = sorted(df["feature"].unique())

        for row_idx, feat in enumerate(features):
            fdf = df[df["feature"] == feat]
            total_checkouts = len(fdf)
            unique_users = fdf["user"].nunique()
            active_days = fdf["datetime"].dt.date.nunique()

            # Concurrent per snapshot: count rows per unique ts
            concurrent_per_snap = fdf.groupby("ts").size()
            avg_concurrent = float(round(concurrent_per_snap.mean(), 2)) if not concurrent_per_snap.empty else 0
            peak_concurrent = int(concurrent_per_snap.max()) if not concurrent_per_snap.empty else 0

            policy_max = self.policy_map.get(feat, None)

            self.stats_table.insertRow(row_idx)
            self.stats_table.setItem(row_idx, 0, QTableWidgetItem(feat))
            self._set_numeric_item(row_idx, 1, total_checkouts)
            self._set_numeric_item(row_idx, 2, unique_users)
            self._set_numeric_item(row_idx, 3, active_days)
            self._set_numeric_item(row_idx, 4, avg_concurrent)
            self._set_numeric_item(row_idx, 5, peak_concurrent)

            if policy_max is not None:
                self._set_numeric_item(row_idx, 6, policy_max)
                # Utilization = avg_concurrent / policy_max * 100
                if policy_max > 0:
                    util_pct = avg_concurrent / policy_max * 100
                else:
                    util_pct = 0
                util_item = QTableWidgetItem(f"{util_pct:.1f}%")
                if util_pct >= 80:
                    util_item.setBackground(QColor(144, 238, 144))  # green
                elif util_pct >= 30:
                    util_item.setBackground(QColor(255, 255, 153))  # yellow
                else:
                    util_item.setBackground(QColor(255, 182, 182))  # red
                self.stats_table.setItem(row_idx, 7, util_item)
            else:
                self.stats_table.setItem(row_idx, 6, QTableWidgetItem("-"))
                no_policy = QTableWidgetItem("No policy")
                no_policy.setBackground(QColor(220, 220, 220))  # gray
                self.stats_table.setItem(row_idx, 7, no_policy)

        self.stats_table.resizeColumnsToContents()
        self.stats_table.setSortingEnabled(True)

    def _set_numeric_item(self, row, col, value):
        """Set a table item that sorts numerically."""
        item = QTableWidgetItem()
        item.setData(Qt.DisplayRole, value)
        self.stats_table.setItem(row, col, item)

    # --------------------------------------------------------
    # Details tab
    # --------------------------------------------------------
    def _update_details(self, df):
        self.detail_table.setSortingEnabled(False)
        self.detail_table.setRowCount(0)

        if df.empty:
            self.detail_table.setSortingEnabled(True)
            return

        max_rows = 10000
        display = df.head(max_rows)

        for idx, (_, row) in enumerate(display.iterrows()):
            self.detail_table.insertRow(idx)
            self.detail_table.setItem(idx, 0, QTableWidgetItem(str(row["ts"])))
            self.detail_table.setItem(idx, 1, QTableWidgetItem(str(row["feature"])))
            self.detail_table.setItem(idx, 2, QTableWidgetItem(str(row["user"])))
            self.detail_table.setItem(idx, 3, QTableWidgetItem(str(row["company"])))
            self.detail_table.setItem(idx, 4, QTableWidgetItem(str(row.get("host", ""))))

        self.detail_table.resizeColumnsToContents()
        self.detail_table.setSortingEnabled(True)

        if len(df) > max_rows:
            self.status_bar.showMessage(
                self.status_bar.currentMessage() +
                f"  (Details tab limited to {max_rows} of {len(df)} rows)"
            )

    # --------------------------------------------------------
    # Export CSV
    # --------------------------------------------------------
    def _export_csv(self):
        if self.filtered_data is None or self.filtered_data.empty:
            QMessageBox.warning(self, "No Data", "Nothing to export. Run Analyze first.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Filtered Data", "license_usage_export.csv",
            "CSV Files (*.csv);;All Files (*)"
        )
        if not file_path:
            return

        try:
            self.filtered_data.to_csv(file_path, index=False)
            QMessageBox.information(self, "Exported", f"Data exported to:\n{file_path}")
            self.status_bar.showMessage(f"Exported {len(self.filtered_data)} records to {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))


# ============================================================
# Entry point
# ============================================================

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    gui = LicenseMonitorGUI()
    gui.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
