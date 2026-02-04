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
import base64
import subprocess
from io import BytesIO
from datetime import datetime, date
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QDateEdit, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QTabWidget, QGroupBox, QGridLayout, QMessageBox,
    QFileDialog, QProgressBar, QStatusBar, QListWidget, QListWidgetItem,
    QAbstractItemView, QFrame, QCheckBox, QComboBox,
    QSplitter, QLineEdit,
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
EXPORT_DIR = BASE_DIR / "exports"

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
    def parse_file(filepath, user_company_map=None):
        """Parse a single lmstat file.

        Returns list of dicts: {ts, feature, user, company, host}

        If user_company_map is provided, use it for user filtering and company
        derivation. Otherwise fall back to USER_RE + user.split("-")[0].
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

                        if user_company_map:
                            if user not in user_company_map:
                                continue
                            company = user_company_map[user]
                        else:
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
    """Load per-user policy_max from license_policy table if available."""

    @staticmethod
    def load(db_path):
        """Return list of (user, company, feature, policy_max) tuples, or empty list."""
        rows = []
        try:
            if not Path(db_path).exists():
                return rows
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='license_policy'"
            )
            if not cur.fetchone():
                conn.close()
                return rows
            cur.execute("SELECT user, company, feature, policy_max FROM license_policy")
            rows = [(r[0], r[1], r[2], int(r[3])) for r in cur.fetchall() if r[2] and r[3]]
            conn.close()
        except Exception:
            pass
        return rows


# ============================================================
# ConfigLoader — parse csh config for lmutil settings
# ============================================================

class ConfigLoader:
    """Parse csh-style config file to extract setenv variables."""

    @staticmethod
    def load(conf_path=None):
        """Return dict of resolved config variables."""
        if conf_path is None:
            conf_path = BASE_DIR / "conf" / "license_monitor.conf.csh"
        config = {}
        try:
            if not Path(conf_path).exists():
                return config
            with open(conf_path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    m = re.match(r'setenv\s+(\w+)\s+"([^"]*)"', line)
                    if not m:
                        continue
                    key, val = m.group(1), m.group(2)
                    # Resolve ${VAR} references
                    def _resolve(match, _cfg=config):
                        return _cfg.get(match.group(1), match.group(0))
                    val = re.sub(r'\$\{(\w+)\}', _resolve, val)
                    val = re.sub(r'\$(\w+)', _resolve, val)
                    config[key] = val
        except Exception:
            pass
        return config


# ============================================================
# AnalyzerThread — background file parsing
# ============================================================

class AnalyzerThread(QThread):
    """Background thread that scans and parses raw lmstat files."""

    analysis_complete = pyqtSignal(object, int)   # (DataFrame, file_count)
    progress = pyqtSignal(int)                     # percentage 0-100
    error_occurred = pyqtSignal(str)

    def __init__(self, raw_dir, start_date, end_date, user_company_map=None):
        super().__init__()
        self.raw_dir = raw_dir
        self.start_date = start_date
        self.end_date = end_date
        self.user_company_map = user_company_map

    def run(self):
        try:
            files = LmstatParser.scan_files(self.raw_dir, self.start_date, self.end_date)
            total = len(files)
            if total == 0:
                self.analysis_complete.emit(pd.DataFrame(), 0)
                return

            all_records = []
            for idx, fp in enumerate(files):
                recs = LmstatParser.parse_file(fp, self.user_company_map)
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
# CollectorThread — run lmutil lmstat in background
# ============================================================

class CollectorThread(QThread):
    """Background thread that runs lmutil lmstat to collect a fresh snapshot."""

    collection_complete = pyqtSignal(str)   # output file path
    error_occurred = pyqtSignal(str)

    def __init__(self, lmutil, lmstat_args, server_spec, output_dir):
        super().__init__()
        self.lmutil = lmutil
        self.lmstat_args = lmstat_args
        self.server_spec = server_spec
        self.output_dir = output_dir

    def run(self):
        try:
            Path(self.output_dir).mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            out_path = str(Path(self.output_dir) / f"lmstat_{ts}.txt")

            cmd = [self.lmutil, "lmstat"]
            if self.lmstat_args:
                cmd += self.lmstat_args.split()
            cmd += ["-c", self.server_spec]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120
            )

            # Only write stdout (matching collect_lmstat.csh behavior).
            # Stderr is NOT written — it would corrupt the parser.
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(result.stdout)

            # Warn if output looks empty (server unreachable, etc.)
            if len(result.stdout.strip()) < 50:
                self.error_occurred.emit(
                    f"Collected file appears empty or too small.\n"
                    f"Check license server connectivity.\n"
                    f"stderr: {result.stderr[:300] if result.stderr else '(none)'}"
                )
                return

            self.collection_complete.emit(out_path)

        except FileNotFoundError:
            self.error_occurred.emit(
                f"lmutil not found: {self.lmutil}\n"
                f"Verify the path in conf/license_monitor.conf.csh"
            )
        except subprocess.TimeoutExpired:
            self.error_occurred.emit("lmstat collection timed out (120s).")
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

    # Step 1: concurrent licenses per snapshot (ts) per feature
    per_snap = (
        df.groupby(["ts", "time_bin", "feature"])
        .agg(
            concurrent=("user", "size"),
            unique_users=("user", "nunique"),
        )
        .reset_index()
    )

    # Step 2: aggregate per-snapshot values into time bins (peak concurrent)
    agg = (
        per_snap.groupby(["time_bin", "feature"])
        .agg(
            concurrent=("concurrent", "max"),
            unique_users=("unique_users", "max"),
        )
        .reset_index()
    )

    return agg, granularity, tick_fmt


def generate_all_time_bins(start_date, end_date, granularity, bin_fmt):
    """Generate a complete list of time-bin strings covering [start_date, end_date]."""
    start_dt = datetime(start_date.year, start_date.month, start_date.day)
    end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59)

    if granularity == "5min":
        idx = pd.date_range(start_dt, end_dt, freq="5min")
        return [dt.strftime(bin_fmt) for dt in idx]
    elif granularity == "hourly":
        idx = pd.date_range(start_dt, end_dt, freq="h")
        return [dt.strftime(bin_fmt) for dt in idx]
    elif granularity == "daily":
        idx = pd.date_range(start_dt, end_dt, freq="D")
        return [dt.strftime(bin_fmt) for dt in idx]
    elif granularity == "weekly":
        bins = []
        cur = start_dt
        while cur <= end_dt:
            iso = cur.isocalendar()
            bins.append(f"{iso[0]}-W{iso[1]:02d}")
            cur += pd.Timedelta(days=7)
        return list(dict.fromkeys(bins))  # dedupe preserving order
    elif granularity == "monthly":
        idx = pd.date_range(start_dt, end_dt, freq="MS")
        # ensure end month is included
        if idx.empty or idx[-1].month != end_dt.month or idx[-1].year != end_dt.year:
            idx = idx.append(pd.DatetimeIndex([end_dt.replace(day=1)]))
        return list(dict.fromkeys(dt.strftime(bin_fmt) for dt in idx))
    return []


def fill_missing_time_bins(agg, start_date, end_date, granularity, bin_fmt):
    """Reindex aggregated data so every (time_bin, feature) pair exists; fill gaps with 0."""
    if agg.empty:
        return agg

    all_bins = generate_all_time_bins(start_date, end_date, granularity, bin_fmt)
    if not all_bins:
        return agg

    features = sorted(agg["feature"].unique())
    full_index = pd.MultiIndex.from_product(
        [all_bins, features], names=["time_bin", "feature"]
    )
    agg_indexed = agg.set_index(["time_bin", "feature"])
    agg_filled = agg_indexed.reindex(full_index, fill_value=0).reset_index()
    return agg_filled


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
        self.collector_thread = None
        self._collect_then_analyze = False
        self.policy_rows = []         # [(user, company, feature, policy_max), ...]
        self.policy_map = {}          # {feature: policy_max} — computed per filter
        self.user_company_map = {}    # {user: company} — from policy
        self.config = {}              # parsed from conf/license_monitor.conf.csh

        self._init_ui()
        self._load_policy()
        self._load_config()

    # --------------------------------------------------------
    # UI construction
    # --------------------------------------------------------
    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout()

        # ---- Top bar: Period + Actions ----
        top_bar = QHBoxLayout()

        # Period selection
        period_group = QGroupBox("Period Selection")
        period_layout = QVBoxLayout()
        period_layout.setContentsMargins(6, 4, 6, 4)

        quick_row = QHBoxLayout()
        quick_row.addWidget(QLabel("Quick:"))
        for label, days in [("Weekly", 7), ("Monthly", 30), ("Quarterly", 90), ("Yearly", 365)]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked, d=days: self._quick_period(d))
            quick_row.addWidget(btn)
        quick_row.addStretch()
        period_layout.addLayout(quick_row)

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
        top_bar.addWidget(period_group, stretch=1)

        # Action buttons (vertical stack, right side)
        action_group = QGroupBox("Actions")
        action_layout = QVBoxLayout()
        action_layout.setContentsMargins(6, 4, 6, 4)

        action_row1 = QHBoxLayout()
        self.collect_btn = QPushButton("Collect Now")
        self.collect_btn.setToolTip("Run lmutil lmstat to collect a fresh snapshot")
        self.collect_btn.clicked.connect(self._run_collect)
        action_row1.addWidget(self.collect_btn)
        self.auto_collect_cb = QCheckBox("Auto-collect")
        self.auto_collect_cb.setChecked(True)
        self.auto_collect_cb.setToolTip("Collect fresh lmstat data before each analysis")
        action_row1.addWidget(self.auto_collect_cb)
        action_layout.addLayout(action_row1)

        action_row2 = QHBoxLayout()
        self.analyze_btn = QPushButton("Analyze")
        font = self.analyze_btn.font()
        font.setBold(True)
        self.analyze_btn.setFont(font)
        self.analyze_btn.clicked.connect(self._run_analyze)
        action_row2.addWidget(self.analyze_btn)
        self.export_btn = QPushButton("Export CSV")
        self.export_btn.clicked.connect(self._export_csv)
        action_row2.addWidget(self.export_btn)
        self.export_html_btn = QPushButton("Export HTML")
        self.export_html_btn.clicked.connect(self._export_html)
        action_row2.addWidget(self.export_html_btn)
        action_layout.addLayout(action_row2)

        action_group.setLayout(action_layout)
        top_bar.addWidget(action_group)

        root.addLayout(top_bar)

        # ---- Progress bar ----
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        root.addWidget(self.progress_bar)

        # ---- Main area: Left filter pane + Right content ----
        splitter = QSplitter(Qt.Horizontal)

        # ======== LEFT PANE — Filters ========
        left_pane = QWidget()
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(2, 2, 2, 2)
        left_layout.setSpacing(4)

        # -- Features --
        self.feature_label = QLabel("Features")
        self.feature_label.setStyleSheet("font-weight: bold;")
        left_layout.addWidget(self.feature_label)

        feat_btn_row = QHBoxLayout()
        feat_btn_row.setSpacing(2)
        feat_all_btn = QPushButton("All")
        feat_all_btn.setFixedHeight(22)
        feat_all_btn.clicked.connect(lambda: self._select_all(self.feature_list))
        feat_btn_row.addWidget(feat_all_btn)
        feat_none_btn = QPushButton("None")
        feat_none_btn.setFixedHeight(22)
        feat_none_btn.clicked.connect(lambda: self._select_none(self.feature_list))
        feat_btn_row.addWidget(feat_none_btn)
        feat_btn_row.addStretch()
        left_layout.addLayout(feat_btn_row)

        self.feature_search = QLineEdit()
        self.feature_search.setPlaceholderText("Search features...")
        self.feature_search.setClearButtonEnabled(True)
        self.feature_search.textChanged.connect(
            lambda text: self._filter_list(self.feature_list, text))
        left_layout.addWidget(self.feature_search)

        self.feature_list = QListWidget()
        self.feature_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.feature_list.itemSelectionChanged.connect(self._on_filter_changed)
        left_layout.addWidget(self.feature_list, stretch=3)

        # -- Companies --
        self.company_label = QLabel("Companies")
        self.company_label.setStyleSheet("font-weight: bold;")
        left_layout.addWidget(self.company_label)

        comp_btn_row = QHBoxLayout()
        comp_btn_row.setSpacing(2)
        comp_all_btn = QPushButton("All")
        comp_all_btn.setFixedHeight(22)
        comp_all_btn.clicked.connect(lambda: self._select_all(self.company_list))
        comp_btn_row.addWidget(comp_all_btn)
        comp_none_btn = QPushButton("None")
        comp_none_btn.setFixedHeight(22)
        comp_none_btn.clicked.connect(lambda: self._select_none(self.company_list))
        comp_btn_row.addWidget(comp_none_btn)
        comp_btn_row.addStretch()
        left_layout.addLayout(comp_btn_row)

        self.company_search = QLineEdit()
        self.company_search.setPlaceholderText("Search companies...")
        self.company_search.setClearButtonEnabled(True)
        self.company_search.textChanged.connect(
            lambda text: self._filter_list(self.company_list, text))
        left_layout.addWidget(self.company_search)

        self.company_list = QListWidget()
        self.company_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.company_list.itemSelectionChanged.connect(self._on_company_filter_changed)
        left_layout.addWidget(self.company_list, stretch=2)

        # -- Users --
        self.user_label = QLabel("Users")
        self.user_label.setStyleSheet("font-weight: bold;")
        left_layout.addWidget(self.user_label)

        user_btn_row = QHBoxLayout()
        user_btn_row.setSpacing(2)
        user_all_btn = QPushButton("All")
        user_all_btn.setFixedHeight(22)
        user_all_btn.clicked.connect(lambda: self._select_all(self.user_list))
        user_btn_row.addWidget(user_all_btn)
        user_none_btn = QPushButton("None")
        user_none_btn.setFixedHeight(22)
        user_none_btn.clicked.connect(lambda: self._select_none(self.user_list))
        user_btn_row.addWidget(user_none_btn)
        user_btn_row.addStretch()
        left_layout.addLayout(user_btn_row)

        self.user_search = QLineEdit()
        self.user_search.setPlaceholderText("Search users...")
        self.user_search.setClearButtonEnabled(True)
        self.user_search.textChanged.connect(
            lambda text: self._filter_list(self.user_list, text))
        left_layout.addWidget(self.user_search)

        self.user_list = QListWidget()
        self.user_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.user_list.itemSelectionChanged.connect(self._on_filter_changed)
        left_layout.addWidget(self.user_list, stretch=2)

        left_pane.setLayout(left_layout)
        left_pane.setMinimumWidth(140)
        left_pane.setMaximumWidth(350)
        splitter.addWidget(left_pane)

        # ======== RIGHT PANE — Tabs ========
        right_pane = QWidget()
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(2, 2, 2, 2)

        self.tabs = QTabWidget()

        # Tab 1: Usage Trend chart
        chart_widget = QWidget()
        chart_layout = QVBoxLayout()

        # Chart Options row
        chart_opts = QHBoxLayout()
        chart_opts.addWidget(QLabel("Type:"))
        self.chart_type_cb = QComboBox()
        self.chart_type_cb.addItems(["Line", "Bar", "Area", "Step"])
        self.chart_type_cb.setCurrentIndex(2)  # Area
        self.chart_type_cb.currentIndexChanged.connect(self._on_chart_option_changed)
        chart_opts.addWidget(self.chart_type_cb)

        chart_opts.addWidget(QLabel("Line:"))
        self.line_style_cb = QComboBox()
        self.line_style_cb.addItems(["Solid", "Dashed", "Dotted", "Dash-dot"])
        self.line_style_cb.currentIndexChanged.connect(self._on_chart_option_changed)
        chart_opts.addWidget(self.line_style_cb)

        chart_opts.addWidget(QLabel("Width:"))
        self.line_width_cb = QComboBox()
        self.line_width_cb.addItems(["Thin", "Medium", "Thick"])
        self.line_width_cb.currentIndexChanged.connect(self._on_chart_option_changed)
        chart_opts.addWidget(self.line_width_cb)

        chart_opts.addWidget(QLabel("Marker:"))
        self.marker_cb = QComboBox()
        self.marker_cb.addItems(["Circle", "Square", "Triangle", "Diamond", "None"])
        self.marker_cb.setCurrentIndex(4)  # None
        self.marker_cb.currentIndexChanged.connect(self._on_chart_option_changed)
        chart_opts.addWidget(self.marker_cb)

        chart_opts.addWidget(QLabel("Font:"))
        self.font_size_cb = QComboBox()
        self.font_size_cb.addItems(["Small", "Medium", "Large", "X-Large"])
        self.font_size_cb.setCurrentIndex(1)
        self.font_size_cb.currentIndexChanged.connect(self._on_chart_option_changed)
        chart_opts.addWidget(self.font_size_cb)

        chart_opts.addWidget(QLabel("Grid:"))
        self.grid_cb = QComboBox()
        self.grid_cb.addItems(["On", "Off"])
        self.grid_cb.currentIndexChanged.connect(self._on_chart_option_changed)
        chart_opts.addWidget(self.grid_cb)

        chart_opts.addWidget(QLabel("Legend:"))
        self.legend_cb = QComboBox()
        self.legend_cb.addItems(["Best", "Upper Right", "Upper Left", "Lower Right", "Lower Left"])
        self.legend_cb.currentIndexChanged.connect(self._on_chart_option_changed)
        chart_opts.addWidget(self.legend_cb)

        chart_opts.addStretch()
        chart_layout.addLayout(chart_opts)

        self.figure = Figure(figsize=(12, 5), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        chart_layout.addWidget(self.canvas)
        chart_widget.setLayout(chart_layout)
        self.tabs.addTab(chart_widget, "Usage Trend")

        # Tab 2: Statistics table
        self.stats_table = QTableWidget()
        self.stats_table.setColumnCount(12)
        self.stats_table.setHorizontalHeaderLabels([
            "Feature", "Total Checkouts", "Unique Users", "Active Days",
            "Avg Concurrent", "Peak Concurrent", "Est. Usage Hours",
            "First Seen", "Last Seen",
            "Policy Max", "Utilization", "Hours Util. %",
        ])
        self.stats_table.horizontalHeader().setStretchLastSection(True)
        self.stats_table.setSortingEnabled(True)
        self.tabs.addTab(self.stats_table, "Statistics")

        # Tab 3: User Activity table
        self.user_activity_table = QTableWidget()
        self.user_activity_table.setColumnCount(9)
        self.user_activity_table.setHorizontalHeaderLabels([
            "User", "Company", "Features Used", "Total Checkouts",
            "Est. Usage Hours", "Active Days", "First Active", "Last Active",
            "Avg Hours/Day",
        ])
        self.user_activity_table.horizontalHeader().setStretchLastSection(True)
        self.user_activity_table.setSortingEnabled(True)
        self.tabs.addTab(self.user_activity_table, "User Activity")

        # Tab 4: Details table
        self.detail_table = QTableWidget()
        self.detail_table.setColumnCount(5)
        self.detail_table.setHorizontalHeaderLabels([
            "Timestamp", "Feature", "User", "Company", "Host",
        ])
        self.detail_table.horizontalHeader().setStretchLastSection(True)
        self.detail_table.setSortingEnabled(True)
        self.tabs.addTab(self.detail_table, "Details")

        right_layout.addWidget(self.tabs)
        right_pane.setLayout(right_layout)
        splitter.addWidget(right_pane)

        # Splitter proportions: ~200px left, rest right
        splitter.setSizes([200, 1200])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, stretch=1)

        # ---- Status bar ----
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready. Select a period and click Analyze.")

        central.setLayout(root)

    # --------------------------------------------------------
    # Policy loading (optional)
    # --------------------------------------------------------
    def _load_policy(self):
        self.policy_rows = PolicyLoader.load(DB_PATH)
        self.user_company_map = {user: company for user, company, _, _ in self.policy_rows}

    def _compute_policy_map(self, selected_users=None):
        """Compute {feature: SUM(policy_max)} filtered by selected users."""
        self.policy_map = self._policy_map_for_users(selected_users)

    def _policy_map_for_users(self, users=None):
        """Return {feature: total_policy_max} for given user set (or all if None).

        Aggregation: MAX(policy_max) within each (company, feature),
        then SUM across companies per feature.
        """
        # Step 1: per (company, feature) -> MAX(policy_max)
        company_feat = {}
        for user, company, feature, pmax in self.policy_rows:
            if users is not None and user not in users:
                continue
            key = (company, feature)
            company_feat[key] = max(company_feat.get(key, 0), pmax)
        # Step 2: SUM across companies per feature
        policy = {}
        for (company, feature), pmax in company_feat.items():
            policy[feature] = policy.get(feature, 0) + pmax
        return policy

    # --------------------------------------------------------
    # Config loading (lmutil settings)
    # --------------------------------------------------------
    def _load_config(self):
        self.config = ConfigLoader.load()
        lmutil = self.config.get("LMUTIL", "")
        server = self.config.get("LM_SERVER", "")
        if lmutil and server:
            self.status_bar.showMessage(
                f"Ready. lmutil: {lmutil}  |  Server: {server}"
            )
        else:
            self.auto_collect_cb.setChecked(False)
            self.auto_collect_cb.setEnabled(False)
            self.collect_btn.setEnabled(False)
            self.status_bar.showMessage(
                "Ready (collection disabled — conf/license_monitor.conf.csh not found or incomplete)."
            )

    # --------------------------------------------------------
    # Collect lmstat snapshot
    # --------------------------------------------------------
    def _run_collect(self):
        """Collect a fresh lmstat snapshot via lmutil."""
        lmutil = self.config.get("LMUTIL", "")
        lmstat_args = self.config.get("LMSTAT_ARGS", "-a")
        use_lic_file = self.config.get("LMUTIL_USE_LICENSE_FILE", "0")
        if use_lic_file == "1":
            server_spec = self.config.get("LICENSE_FILE", "")
        else:
            server_spec = self.config.get("LM_SERVER", "")

        if not lmutil or not server_spec:
            QMessageBox.warning(
                self, "Configuration Missing",
                "lmutil path or server not configured.\n"
                "Check conf/license_monitor.conf.csh"
            )
            return

        self.collect_btn.setEnabled(False)
        self.analyze_btn.setEnabled(False)
        self.status_bar.showMessage("Collecting lmstat snapshot...")

        self.collector_thread = CollectorThread(
            lmutil, lmstat_args, server_spec, str(RAW_DIR)
        )
        self.collector_thread.collection_complete.connect(self._on_collection_complete)
        self.collector_thread.error_occurred.connect(self._on_collection_error)
        self.collector_thread.start()

    def _on_collection_complete(self, filepath):
        self.collect_btn.setEnabled(True)
        self.analyze_btn.setEnabled(True)
        fname = Path(filepath).name
        self.status_bar.showMessage(f"Collected: {fname}")

        if self._collect_then_analyze:
            self._collect_then_analyze = False
            self._start_analysis()

    def _on_collection_error(self, msg):
        self.collect_btn.setEnabled(True)
        self.analyze_btn.setEnabled(True)
        self.status_bar.showMessage(f"Collection error: {msg}")
        QMessageBox.warning(self, "Collection Error",
                            f"{msg}\n\nProceeding with existing files.")

        # Still run analysis with whatever files already exist
        if self._collect_then_analyze:
            self._collect_then_analyze = False
            self._start_analysis()

    # --------------------------------------------------------
    # Chart options helpers
    # --------------------------------------------------------
    def _get_chart_options(self):
        """Read current chart option widgets and return a settings dict."""
        type_map = {"Line": "line", "Bar": "bar", "Area": "area", "Step": "step"}
        ls_map = {"Solid": "-", "Dashed": "--", "Dotted": ":", "Dash-dot": "-."}
        marker_map = {"Circle": "o", "Square": "s", "Triangle": "^",
                       "Diamond": "D", "None": ""}
        width_map = {"Thin": 0.8, "Medium": 1.5, "Thick": 2.5}
        font_map = {"Small": 8, "Medium": 10, "Large": 12, "X-Large": 14}
        legend_map = {
            "Best": "best", "Upper Right": "upper right",
            "Upper Left": "upper left", "Lower Right": "lower right",
            "Lower Left": "lower left",
        }
        return {
            "chart_type": type_map.get(self.chart_type_cb.currentText(), "line"),
            "linestyle": ls_map.get(self.line_style_cb.currentText(), "-"),
            "marker": marker_map.get(self.marker_cb.currentText(), "o"),
            "linewidth": width_map.get(self.line_width_cb.currentText(), 0.8),
            "fontsize": font_map.get(self.font_size_cb.currentText(), 10),
            "grid": self.grid_cb.currentText() == "On",
            "legend_loc": legend_map.get(self.legend_cb.currentText(), "best"),
        }

    def _on_chart_option_changed(self):
        """Redraw chart when any chart option changes."""
        if self.filtered_data is not None:
            self._update_chart(self.filtered_data)

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

        # Auto-collect before analysis if enabled
        if self.auto_collect_cb.isChecked() and self.auto_collect_cb.isEnabled():
            self._collect_then_analyze = True
            self._run_collect()
            return

        self._start_analysis()

    def _start_analysis(self):
        """Begin the file-parsing analysis (called directly or after collection)."""
        start_qd = self.start_date_edit.date()
        end_qd = self.end_date_edit.date()
        start = date(start_qd.year(), start_qd.month(), start_qd.day())
        end = date(end_qd.year(), end_qd.month(), end_qd.day())

        self.analyze_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_bar.showMessage("Scanning files...")

        self.analyzer_thread = AnalyzerThread(str(RAW_DIR), start, end, self.user_company_map or None)
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
    # Filter helpers: All / None / Search / Count
    # --------------------------------------------------------
    def _select_all(self, list_widget):
        list_widget.blockSignals(True)
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if not item.isHidden():
                item.setSelected(True)
        list_widget.blockSignals(False)
        self._update_filter_labels()
        if list_widget is self.company_list:
            self._on_company_filter_changed()
        else:
            self._on_filter_changed()

    def _select_none(self, list_widget):
        list_widget.blockSignals(True)
        list_widget.clearSelection()
        list_widget.blockSignals(False)
        self._update_filter_labels()
        if list_widget is self.company_list:
            self._on_company_filter_changed()
        else:
            self._on_filter_changed()

    def _filter_list(self, list_widget, text):
        """Show/hide list items based on search text."""
        text_lower = text.lower()
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            item.setHidden(text_lower not in item.text().lower())

    def _update_filter_labels(self):
        """Update the selection-count labels for each filter list."""
        def _label(lbl_widget, name, list_widget):
            total = list_widget.count()
            sel = len(list_widget.selectedItems())
            lbl_widget.setText(f"{name} ({sel}/{total})")

        _label(self.feature_label, "Features", self.feature_list)
        _label(self.company_label, "Companies", self.company_list)
        _label(self.user_label, "Users", self.user_list)

    # --------------------------------------------------------
    # Filter population
    # --------------------------------------------------------
    def _populate_filters(self, df):
        self.feature_list.blockSignals(True)
        self.company_list.blockSignals(True)
        self.user_list.blockSignals(True)

        # Clear search boxes
        self.feature_search.clear()
        self.company_search.clear()
        self.user_search.clear()

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

        self._update_filter_labels()

    # --------------------------------------------------------
    # Filter change → instant re-draw (no re-parse)
    # --------------------------------------------------------
    def _on_filter_changed(self):
        self._update_filter_labels()
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

        self._update_filter_labels()
        self._apply_and_refresh()

    def _get_selected(self, list_widget):
        return [item.text() for item in list_widget.selectedItems()]

    def _apply_and_refresh(self):
        if self.raw_data is None or self.raw_data.empty:
            self.filtered_data = pd.DataFrame()
            self._update_chart(self.filtered_data)
            self._update_stats(self.filtered_data)
            self._update_user_activity(self.filtered_data)
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

        # Recompute policy map based on selected users
        self._compute_policy_map(set(sel_users) if sel_users else None)

        self._update_chart(self.filtered_data)
        self._update_stats(self.filtered_data)
        self._update_user_activity(self.filtered_data)
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

        # Fill missing time bins with zero
        _, bin_fmt, _ = determine_granularity(start_d, end_d)
        agg = fill_missing_time_bins(agg, start_d, end_d, granularity, bin_fmt)

        # Convert time_bin back to datetime for plotting
        if granularity == "weekly":
            agg["plot_dt"] = agg["time_bin"].apply(
                lambda s: datetime.strptime(s + "-1", "%G-W%V-%u")
            )
        elif granularity == "monthly":
            agg["plot_dt"] = pd.to_datetime(agg["time_bin"] + "-01")
        else:
            agg["plot_dt"] = pd.to_datetime(agg["time_bin"])

        # Read chart options
        opts = self._get_chart_options()
        ct = opts["chart_type"]
        ls = opts["linestyle"]
        mk = opts["marker"] or None
        lw = opts["linewidth"]
        fs = opts["fontsize"]

        # Plot per feature, track colors for policy overlay
        features = sorted(agg["feature"].unique())
        feat_colors = {}

        if ct == "bar":
            n_feat = max(len(features), 1)
            width_days = {
                "5min": 1 / 288, "hourly": 1 / 24, "daily": 1,
                "weekly": 7, "monthly": 28,
            }
            base_w = width_days.get(granularity, 1) * 0.8
            bar_w = base_w / n_feat
            for i, feat in enumerate(features):
                fdata = agg[agg["feature"] == feat].sort_values("plot_dt")
                offset = pd.Timedelta(days=bar_w * (i - (n_feat - 1) / 2))
                bars = ax.bar(fdata["plot_dt"] + offset, fdata["concurrent"],
                              width=bar_w, label=feat, alpha=0.8)
                feat_colors[feat] = bars[0].get_facecolor() if len(bars) else None
        else:
            for feat in features:
                fdata = agg[agg["feature"] == feat].sort_values("plot_dt")
                x, y = fdata["plot_dt"], fdata["concurrent"]
                if ct == "area":
                    line, = ax.plot(x, y, marker=mk, linewidth=lw, markersize=4,
                                    linestyle=ls, label=feat)
                    ax.fill_between(x, y, alpha=0.15, color=line.get_color())
                elif ct == "step":
                    line, = ax.step(x, y, where="mid", linewidth=lw,
                                    linestyle=ls, label=feat)
                    if mk:
                        ax.plot(x, y, marker=mk, linewidth=0, markersize=4,
                                color=line.get_color())
                else:  # line
                    line, = ax.plot(x, y, marker=mk, linewidth=lw, markersize=4,
                                    linestyle=ls, label=feat)
                feat_colors[feat] = line.get_color()

                # Annotate transition points (where value changes)
                y_vals = y.values if hasattr(y, 'values') else list(y)
                x_vals = x.values if hasattr(x, 'values') else list(x)
                for j in range(len(y_vals)):
                    if j == 0 or y_vals[j] != y_vals[j - 1]:
                        val = int(y_vals[j])
                        if val > 0:
                            ax.annotate(str(val), (x_vals[j], y_vals[j]),
                                        textcoords="offset points", xytext=(0, 6),
                                        fontsize=max(fs - 3, 5), ha="center",
                                        color=feat_colors.get(feat, "black"))

        # Policy overlay — same color as its feature
        for feat in features:
            if feat in self.policy_map:
                color = feat_colors.get(feat, None)
                ax.axhline(y=self.policy_map[feat], linestyle="--",
                           linewidth=max(lw * 0.8, 0.6), alpha=0.7,
                           color=color,
                           label=f"{feat} MAX={self.policy_map[feat]}")

        # Current time marker
        now_dt = datetime.now()
        ax.axvline(x=now_dt, linestyle="-.", linewidth=0.9, color="red", alpha=0.7)
        ax.annotate("Now", xy=(now_dt, ax.get_ylim()[1]),
                    xytext=(4, -2), textcoords="offset points",
                    fontsize=fs - 1, color="red", fontweight="bold",
                    va="top")

        # Axis formatting
        ax.set_ylabel("Concurrent Licenses", fontsize=fs + 1, fontweight="bold")
        ax.set_xlabel("Time", fontsize=fs + 1, fontweight="bold")
        ax.xaxis.set_major_formatter(DateFormatter(tick_fmt))
        ax.tick_params(axis="both", labelsize=fs)
        self.figure.autofmt_xdate(rotation=45)
        ax.grid(opts["grid"], alpha=0.3)
        ax.legend(loc=opts["legend_loc"], fontsize=max(fs - 2, 6), ncol=2)

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
            fontsize=fs + 3, fontweight="bold",
        )

        self.figure.tight_layout()
        self.canvas.draw()

    # --------------------------------------------------------
    # Helpers
    # --------------------------------------------------------
    def _estimate_interval_minutes(self, df):
        """Estimate the average snapshot interval in minutes from timestamps."""
        if df.empty:
            return 0.0
        timestamps = pd.to_datetime(df["ts"], format="%Y-%m-%d %H:%M:%S", errors="coerce").dropna()
        unique_ts = sorted(timestamps.unique())
        if len(unique_ts) < 2:
            return 0.0
        total_delta = unique_ts[-1] - unique_ts[0]
        avg_interval = total_delta / (len(unique_ts) - 1)
        return avg_interval.total_seconds() / 60.0

    @staticmethod
    def _make_numeric_item(value):
        """Create a QTableWidgetItem that sorts numerically."""
        item = QTableWidgetItem()
        item.setData(Qt.DisplayRole, value)
        return item

    # --------------------------------------------------------
    # Statistics tab
    # --------------------------------------------------------
    def _get_period_hours(self):
        """Calculate total hours in the selected period."""
        start_qd = self.start_date_edit.date()
        end_qd = self.end_date_edit.date()
        start_dt = datetime(start_qd.year(), start_qd.month(), start_qd.day())
        end_dt = datetime(end_qd.year(), end_qd.month(), end_qd.day(), 23, 59, 59)
        return max((end_dt - start_dt).total_seconds() / 3600.0, 1.0)

    def _update_stats(self, df):
        self.stats_table.setSortingEnabled(False)
        self.stats_table.setRowCount(0)

        if df.empty:
            self.stats_table.setSortingEnabled(True)
            return

        df = df.copy()
        df["datetime"] = pd.to_datetime(df["ts"], format="%Y-%m-%d %H:%M:%S", errors="coerce")

        interval_min = self._estimate_interval_minutes(df)
        period_hours = self._get_period_hours()
        total_snapshots = df["ts"].nunique()
        features = sorted(df["feature"].unique())

        for row_idx, feat in enumerate(features):
            fdf = df[df["feature"] == feat]
            total_checkouts = len(fdf)
            unique_users = fdf["user"].nunique()
            active_days = fdf["datetime"].dt.date.nunique()

            # Concurrent per snapshot: count rows per unique ts
            concurrent_per_snap = fdf.groupby("ts").size()
            # Divide by ALL snapshots in the period (not just ones where this feature appears)
            avg_concurrent = float(round(concurrent_per_snap.sum() / total_snapshots, 2)) if total_snapshots > 0 else 0
            peak_concurrent = int(concurrent_per_snap.max()) if not concurrent_per_snap.empty else 0

            # Est. Usage Hours: number of snapshot appearances × interval / 60
            est_usage_hours = round(total_checkouts * interval_min / 60.0, 1) if interval_min > 0 else 0.0

            # First/Last Seen
            valid_dt = fdf["datetime"].dropna()
            first_seen = str(valid_dt.min()) if not valid_dt.empty else "-"
            last_seen = str(valid_dt.max()) if not valid_dt.empty else "-"

            policy_max = self.policy_map.get(feat, None)

            self.stats_table.insertRow(row_idx)
            self.stats_table.setItem(row_idx, 0, QTableWidgetItem(feat))
            self.stats_table.setItem(row_idx, 1, self._make_numeric_item(total_checkouts))
            self.stats_table.setItem(row_idx, 2, self._make_numeric_item(unique_users))
            self.stats_table.setItem(row_idx, 3, self._make_numeric_item(active_days))
            self.stats_table.setItem(row_idx, 4, self._make_numeric_item(avg_concurrent))
            self.stats_table.setItem(row_idx, 5, self._make_numeric_item(peak_concurrent))
            self.stats_table.setItem(row_idx, 6, self._make_numeric_item(est_usage_hours))
            self.stats_table.setItem(row_idx, 7, QTableWidgetItem(first_seen))
            self.stats_table.setItem(row_idx, 8, QTableWidgetItem(last_seen))

            if policy_max is not None:
                self.stats_table.setItem(row_idx, 9, self._make_numeric_item(policy_max))
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
                self.stats_table.setItem(row_idx, 10, util_item)

                # Hours Util. % = est_usage_hours / (policy_max × period_hours) × 100
                if policy_max > 0 and period_hours > 0:
                    capacity_hours = policy_max * period_hours
                    hours_util = est_usage_hours / capacity_hours * 100
                else:
                    hours_util = 0
                hu_item = QTableWidgetItem(f"{hours_util:.1f}%")
                if hours_util >= 60:
                    hu_item.setBackground(QColor(144, 238, 144))  # green
                elif hours_util >= 20:
                    hu_item.setBackground(QColor(255, 255, 153))  # yellow
                else:
                    hu_item.setBackground(QColor(255, 182, 182))  # red
                self.stats_table.setItem(row_idx, 11, hu_item)
            else:
                self.stats_table.setItem(row_idx, 9, QTableWidgetItem("-"))
                no_policy = QTableWidgetItem("No policy")
                no_policy.setBackground(QColor(220, 220, 220))  # gray
                self.stats_table.setItem(row_idx, 10, no_policy)
                no_policy2 = QTableWidgetItem("No policy")
                no_policy2.setBackground(QColor(220, 220, 220))
                self.stats_table.setItem(row_idx, 11, no_policy2)

        self.stats_table.resizeColumnsToContents()
        self.stats_table.setSortingEnabled(True)

    # --------------------------------------------------------
    # User Activity tab
    # --------------------------------------------------------
    def _update_user_activity(self, df):
        self.user_activity_table.setSortingEnabled(False)
        self.user_activity_table.setRowCount(0)

        if df.empty:
            self.user_activity_table.setSortingEnabled(True)
            return

        df = df.copy()
        df["datetime"] = pd.to_datetime(df["ts"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
        interval_min = self._estimate_interval_minutes(df)

        users = sorted(df["user"].unique())
        for row_idx, user in enumerate(users):
            udf = df[df["user"] == user]
            company = udf["company"].iloc[0]
            features_used = udf["feature"].nunique()
            total_checkouts = len(udf)
            est_usage_hours = round(total_checkouts * interval_min / 60.0, 1) if interval_min > 0 else 0.0
            valid_dt = udf["datetime"].dropna()
            active_days = valid_dt.dt.date.nunique() if not valid_dt.empty else 0
            first_active = str(valid_dt.min()) if not valid_dt.empty else "-"
            last_active = str(valid_dt.max()) if not valid_dt.empty else "-"
            avg_hours_day = round(est_usage_hours / active_days, 1) if active_days > 0 else 0.0

            self.user_activity_table.insertRow(row_idx)
            self.user_activity_table.setItem(row_idx, 0, QTableWidgetItem(user))
            self.user_activity_table.setItem(row_idx, 1, QTableWidgetItem(company))
            self.user_activity_table.setItem(row_idx, 2, self._make_numeric_item(features_used))
            self.user_activity_table.setItem(row_idx, 3, self._make_numeric_item(total_checkouts))
            self.user_activity_table.setItem(row_idx, 4, self._make_numeric_item(est_usage_hours))
            self.user_activity_table.setItem(row_idx, 5, self._make_numeric_item(active_days))
            self.user_activity_table.setItem(row_idx, 6, QTableWidgetItem(first_active))
            self.user_activity_table.setItem(row_idx, 7, QTableWidgetItem(last_active))
            self.user_activity_table.setItem(row_idx, 8, self._make_numeric_item(avg_hours_day))

        self.user_activity_table.resizeColumnsToContents()
        self.user_activity_table.setSortingEnabled(True)

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

    # --------------------------------------------------------
    # Export HTML Report
    # --------------------------------------------------------
    def _determine_period_info(self, start_date, end_date):
        """Classify period type and compute ordinal from start of year."""
        delta = (end_date - start_date).days
        year_start = date(start_date.year, 1, 1)

        if delta <= 2:
            period_type = "daily"
            day_of_year = (start_date - year_start).days + 1
            ordinal = f"D{day_of_year:03d}"
        elif delta <= 7:
            period_type = "weekly"
            week_num = ((start_date - year_start).days // 7) + 1
            ordinal = f"W{week_num:02d}"
        elif delta <= 31:
            period_type = "monthly"
            ordinal = f"M{start_date.month:02d}"
        elif delta <= 93:
            period_type = "quarterly"
            quarter = (start_date.month - 1) // 3 + 1
            ordinal = f"Q{quarter}"
        else:
            period_type = "yearly"
            ordinal = f"Y{start_date.year}"

        return period_type, ordinal

    def _render_chart_to_base64(self, df, start_d, end_d, policy_map=None):
        """Render usage trend chart to a base64-encoded PNG string."""
        fig = Figure(figsize=(14, 5), dpi=120)
        ax = fig.add_subplot(111)

        if df.empty:
            ax.text(0.5, 0.5, "No data available", ha="center", va="center",
                    transform=ax.transAxes, fontsize=14, color="gray")
        else:
            agg, granularity, tick_fmt = aggregate_by_time_bin(df, start_d, end_d)

            if not agg.empty:
                # Fill missing time bins with zero
                _, bin_fmt_exp, _ = determine_granularity(start_d, end_d)
                agg = fill_missing_time_bins(agg, start_d, end_d, granularity, bin_fmt_exp)

                if granularity == "weekly":
                    agg["plot_dt"] = agg["time_bin"].apply(
                        lambda s: datetime.strptime(s + "-1", "%G-W%V-%u")
                    )
                elif granularity == "monthly":
                    agg["plot_dt"] = pd.to_datetime(agg["time_bin"] + "-01")
                else:
                    agg["plot_dt"] = pd.to_datetime(agg["time_bin"])

                features = sorted(agg["feature"].unique())
                feat_colors = {}
                for feat in features:
                    fdata = agg[agg["feature"] == feat].sort_values("plot_dt")
                    x, y = fdata["plot_dt"], fdata["concurrent"]
                    line, = ax.plot(x, y, linewidth=1.5, label=feat)
                    ax.fill_between(x, y, alpha=0.15, color=line.get_color())
                    feat_colors[feat] = line.get_color()

                pmap = policy_map if policy_map is not None else self.policy_map
                for feat in features:
                    if feat in pmap:
                        color = feat_colors.get(feat, None)
                        ax.axhline(y=pmap[feat], linestyle="--",
                                   linewidth=1.2, alpha=0.7, color=color,
                                   label=f"{feat} MAX={pmap[feat]}")

                ax.xaxis.set_major_formatter(DateFormatter(tick_fmt))
                fig.autofmt_xdate(rotation=45)

                gran_labels = {
                    "5min": "5-Minute", "hourly": "Hourly", "daily": "Daily",
                    "weekly": "Weekly", "monthly": "Monthly",
                }
                period_label = gran_labels.get(granularity, granularity)
                ax.set_title(
                    f"License Usage \u2014 {period_label} View ({start_d} to {end_d})",
                    fontsize=13, fontweight="bold",
                )
            else:
                ax.text(0.5, 0.5, "No data after aggregation", ha="center",
                        va="center", transform=ax.transAxes, fontsize=14, color="gray")

        ax.set_ylabel("Concurrent Licenses", fontsize=11, fontweight="bold")
        ax.set_xlabel("Time", fontsize=11, fontweight="bold")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best", fontsize=8, ncol=2)
        fig.tight_layout()

        buf = BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode("ascii")
        buf.close()
        return b64

    def _build_stats_rows(self, df, policy_map=None, period_hours=None):
        """Build per-feature statistics as a list of dicts."""
        if df.empty:
            return []

        pmap = policy_map if policy_map is not None else self.policy_map
        df = df.copy()
        df["datetime"] = pd.to_datetime(df["ts"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
        interval_min = self._estimate_interval_minutes(df)
        ph = period_hours if period_hours else 1.0
        total_snapshots = df["ts"].nunique()
        rows = []
        for feat in sorted(df["feature"].unique()):
            fdf = df[df["feature"] == feat]
            total_checkouts = len(fdf)
            unique_users = fdf["user"].nunique()
            active_days = fdf["datetime"].dt.date.nunique()
            concurrent_per_snap = fdf.groupby("ts").size()
            # Divide by ALL snapshots (not just ones where this feature appears)
            avg_conc = round(float(concurrent_per_snap.sum() / total_snapshots), 2) if total_snapshots > 0 else 0
            peak_conc = int(concurrent_per_snap.max()) if not concurrent_per_snap.empty else 0
            est_usage_hours = round(total_checkouts * interval_min / 60.0, 1) if interval_min > 0 else 0.0
            valid_dt = fdf["datetime"].dropna()
            first_seen = str(valid_dt.min()) if not valid_dt.empty else "-"
            last_seen = str(valid_dt.max()) if not valid_dt.empty else "-"
            policy_max = pmap.get(feat)
            util_pct = None
            hours_util = None
            if policy_max and policy_max > 0:
                util_pct = round(avg_conc / policy_max * 100, 1)
                hours_util = round(est_usage_hours / (policy_max * ph) * 100, 1)
            rows.append({
                "feature": feat,
                "total_checkouts": total_checkouts,
                "unique_users": unique_users,
                "active_days": active_days,
                "avg_concurrent": avg_conc,
                "peak_concurrent": peak_conc,
                "est_usage_hours": est_usage_hours,
                "first_seen": first_seen,
                "last_seen": last_seen,
                "policy_max": policy_max,
                "utilization": util_pct,
                "hours_utilization": hours_util,
            })
        return rows

    def _build_overuse_analysis(self, df, policy_map=None):
        """Identify features where concurrent usage exceeded policy_max.

        Returns list of dicts with overuse details per feature, or empty list
        if no policy data or no overuse occurred.
        """
        pmap = policy_map if policy_map is not None else self.policy_map
        if df.empty or not pmap:
            return []

        df = df.copy()
        df["datetime"] = pd.to_datetime(df["ts"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
        results = []

        for feat in sorted(df["feature"].unique()):
            policy_max = pmap.get(feat)
            if policy_max is None:
                continue

            fdf = df[df["feature"] == feat]
            snap_counts = fdf.groupby("ts").agg(
                concurrent=("user", "size"),
                dt=("datetime", "first"),
            )

            over = snap_counts[snap_counts["concurrent"] > policy_max]
            if over.empty:
                continue

            total_snapshots = len(snap_counts)
            over_snapshots = len(over)

            # Estimate duration from snapshot intervals
            all_times = sorted(snap_counts["dt"].dropna())
            if len(all_times) >= 2:
                avg_interval = (all_times[-1] - all_times[0]) / (len(all_times) - 1)
                est_duration = avg_interval * over_snapshots
                dur_str = str(est_duration).split(".")[0]  # drop microseconds
            else:
                dur_str = "N/A"

            over_times = sorted(over["dt"].dropna())
            results.append({
                "feature": feat,
                "policy_max": policy_max,
                "peak_concurrent": int(snap_counts["concurrent"].max()),
                "over_snapshots": over_snapshots,
                "total_snapshots": total_snapshots,
                "over_pct": round(over_snapshots / total_snapshots * 100, 1),
                "est_duration": dur_str,
                "first_over": str(over_times[0]) if over_times else "N/A",
                "last_over": str(over_times[-1]) if over_times else "N/A",
                "max_excess": int(snap_counts["concurrent"].max()) - policy_max,
            })

        return sorted(results, key=lambda r: r["over_pct"], reverse=True)

    def _build_company_breakdown(self, df):
        """Build per-company statistics."""
        if df.empty:
            return []
        interval_min = self._estimate_interval_minutes(df)
        rows = []
        for comp in sorted(df["company"].unique()):
            cdf = df[df["company"] == comp]
            total_checkouts = len(cdf)
            concurrent_per_snap = cdf.groupby("ts").size()
            est_usage_hours = round(total_checkouts * interval_min / 60.0, 1) if interval_min > 0 else 0.0
            rows.append({
                "company": comp,
                "features_used": cdf["feature"].nunique(),
                "total_checkouts": total_checkouts,
                "unique_users": cdf["user"].nunique(),
                "peak_concurrent": int(concurrent_per_snap.max()) if not concurrent_per_snap.empty else 0,
                "est_usage_hours": est_usage_hours,
            })
        return sorted(rows, key=lambda r: r["total_checkouts"], reverse=True)

    def _build_feature_company_matrix(self, df):
        """Build Feature x Company peak-concurrent cross-tab."""
        if df.empty:
            return [], [], {}
        features = sorted(df["feature"].unique())
        companies = sorted(df["company"].unique())
        matrix = {}
        for feat in features:
            matrix[feat] = {}
            for comp in companies:
                sub = df[(df["feature"] == feat) & (df["company"] == comp)]
                if sub.empty:
                    matrix[feat][comp] = 0
                else:
                    per_snap = sub.groupby("ts").size()
                    matrix[feat][comp] = int(per_snap.max())
        return features, companies, matrix

    def _build_top_users(self, df, n=20):
        """Top N users by total checkouts."""
        if df.empty:
            return []
        df = df.copy()
        df["datetime"] = pd.to_datetime(df["ts"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
        interval_min = self._estimate_interval_minutes(df)
        results = []
        user_stats = (
            df.groupby("user")
            .agg(
                company=("company", "first"),
                features_used=("feature", "nunique"),
                total_checkouts=("user", "size"),
            )
            .reset_index()
            .sort_values("total_checkouts", ascending=False)
            .head(n)
        )
        for _, row in user_stats.iterrows():
            udf = df[df["user"] == row["user"]]
            valid_dt = udf["datetime"].dropna()
            active_days = valid_dt.dt.date.nunique() if not valid_dt.empty else 0
            est_hours = round(row["total_checkouts"] * interval_min / 60.0, 1) if interval_min > 0 else 0.0
            first_active = str(valid_dt.min()) if not valid_dt.empty else "-"
            last_active = str(valid_dt.max()) if not valid_dt.empty else "-"
            results.append({
                "user": row["user"],
                "company": row["company"],
                "features_used": row["features_used"],
                "total_checkouts": row["total_checkouts"],
                "est_usage_hours": est_hours,
                "active_days": active_days,
                "first_active": first_active,
                "last_active": last_active,
            })
        return results

    def _build_user_activity(self, df):
        """Build per-user activity as a list of dicts for HTML export."""
        if df.empty:
            return []
        df = df.copy()
        df["datetime"] = pd.to_datetime(df["ts"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
        interval_min = self._estimate_interval_minutes(df)
        results = []
        for user in sorted(df["user"].unique()):
            udf = df[df["user"] == user]
            company = udf["company"].iloc[0]
            features_used = udf["feature"].nunique()
            total_checkouts = len(udf)
            est_hours = round(total_checkouts * interval_min / 60.0, 1) if interval_min > 0 else 0.0
            valid_dt = udf["datetime"].dropna()
            active_days = valid_dt.dt.date.nunique() if not valid_dt.empty else 0
            first_active = str(valid_dt.min()) if not valid_dt.empty else "-"
            last_active = str(valid_dt.max()) if not valid_dt.empty else "-"
            avg_hours_day = round(est_hours / active_days, 1) if active_days > 0 else 0.0
            results.append({
                "user": user,
                "company": company,
                "features_used": features_used,
                "total_checkouts": total_checkouts,
                "est_usage_hours": est_hours,
                "active_days": active_days,
                "first_active": first_active,
                "last_active": last_active,
                "avg_hours_day": avg_hours_day,
            })
        return sorted(results, key=lambda r: r["est_usage_hours"], reverse=True)

    def _generate_html(self, chart_b64, stats, company_breakdown,
                       feat_comp_matrix, top_users, overuse,
                       user_activity, company_tabs, meta):
        """Generate self-contained HTML report string with per-company tabs."""
        features, companies, matrix = feat_comp_matrix
        now_str = meta["generated"]
        period_str = f"{meta['start_date']} to {meta['end_date']}"

        def util_color(val):
            if val is None:
                return "#dcdcdc"
            if val >= 80:
                return "#90ee90"
            if val >= 30:
                return "#ffff99"
            return "#ffb6b6"

        def _stats_table_html(stat_rows):
            """Render a feature-statistics table from a list of stat dicts."""
            parts = []
            parts.append("""<table>
<tr><th>Feature</th><th>Total Checkouts</th><th>Unique Users</th>
<th>Active Days</th><th>Avg Concurrent</th><th>Peak Concurrent</th>
<th>Est. Usage Hours</th><th>First Seen</th><th>Last Seen</th>
<th>Policy Max</th><th>Utilization</th><th>Hours Util. %</th></tr>""")
            for s in stat_rows:
                pm = str(s["policy_max"]) if s["policy_max"] is not None else "-"
                euh = s.get("est_usage_hours", 0.0)
                fs = s.get("first_seen", "-")
                ls = s.get("last_seen", "-")
                if s["utilization"] is not None:
                    uc = util_color(s["utilization"])
                    util_cell = (f'<td><span class="util-cell" style="background:{uc};">'
                                 f'{s["utilization"]:.1f}%</span></td>')
                else:
                    util_cell = '<td><span class="util-cell" style="background:#dcdcdc;">N/A</span></td>'
                hu = s.get("hours_utilization")
                if hu is not None:
                    huc = util_color(hu * 4 / 3)  # scale: 60%→green, 20%→yellow
                    hu_cell = (f'<td><span class="util-cell" style="background:{huc};">'
                               f'{hu:.1f}%</span></td>')
                else:
                    hu_cell = '<td><span class="util-cell" style="background:#dcdcdc;">N/A</span></td>'
                parts.append(
                    f'<tr><td>{s["feature"]}</td><td>{s["total_checkouts"]:,}</td>'
                    f'<td>{s["unique_users"]}</td><td>{s["active_days"]}</td>'
                    f'<td>{s["avg_concurrent"]}</td><td>{s["peak_concurrent"]}</td>'
                    f'<td>{euh}</td><td>{fs}</td><td>{ls}</td>'
                    f'<td>{pm}</td>{util_cell}{hu_cell}</tr>'
                )
            parts.append("</table>")
            return "\n".join(parts)

        def _overuse_html(overuse_rows, stat_rows):
            """Render overuse alerts section."""
            parts = []
            if overuse_rows:
                parts.append("""
<div class="alert-banner">
<h3>&#9888; License Overuse Detected</h3>
<p>The following features exceeded their policy maximum during the reporting period.</p>
</div>
<table>
<tr><th>Feature</th><th>Policy Max</th><th>Peak</th><th>Excess</th>
<th>Overuse Snapshots</th><th>of Total</th><th>Overuse %</th>
<th>Est. Duration</th><th>First Occurred</th><th>Last Occurred</th></tr>""")
                for o in overuse_rows:
                    parts.append(
                        f'<tr class="over-highlight">'
                        f'<td>{o["feature"]}</td><td>{o["policy_max"]}</td>'
                        f'<td>{o["peak_concurrent"]}</td><td>+{o["max_excess"]}</td>'
                        f'<td>{o["over_snapshots"]}</td><td>{o["total_snapshots"]}</td>'
                        f'<td>{o["over_pct"]:.1f}%</td>'
                        f'<td>{o["est_duration"]}</td>'
                        f'<td>{o["first_over"]}</td><td>{o["last_over"]}</td></tr>'
                    )
                parts.append("</table>")
            else:
                has_any_policy = any(s["policy_max"] is not None for s in stat_rows)
                if has_any_policy:
                    parts.append(
                        '<p style="color:#28a745;font-weight:bold;">'
                        '&#10004; No license overuse detected during this period.</p>'
                    )
            return "\n".join(parts)

        def _top_users_html(user_rows):
            """Render top-users table."""
            if not user_rows:
                return ""
            parts = []
            parts.append("""<h2>Top Users by Checkout Volume</h2>
<table>
<tr><th>#</th><th>User</th><th>Company</th><th>Features Used</th>
<th>Total Checkouts</th><th>Est. Usage Hours</th><th>Active Days</th>
<th>First Active</th><th>Last Active</th></tr>""")
            for i, u in enumerate(user_rows, 1):
                parts.append(
                    f'<tr><td>{i}</td><td>{u["user"]}</td><td>{u["company"]}</td>'
                    f'<td>{u["features_used"]}</td><td>{u["total_checkouts"]:,}</td>'
                    f'<td>{u.get("est_usage_hours", 0.0)}</td>'
                    f'<td>{u.get("active_days", 0)}</td>'
                    f'<td>{u.get("first_active", "-")}</td>'
                    f'<td>{u.get("last_active", "-")}</td></tr>'
                )
            parts.append("</table>")
            return "\n".join(parts)

        # --- Build tab IDs ---
        tab_ids = ["overall"] + [f"comp_{i}" for i in range(len(company_tabs))]
        tab_labels = ["Overall"] + list(company_tabs.keys())

        # --- Build HTML ---
        h = []
        h.append(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>License Usage Report — {period_str}</title>
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 20px 40px;
         color: #222; background: #fafafa; }}
  h1 {{ color: #1a3a5c; border-bottom: 3px solid #1a3a5c; padding-bottom: 8px; }}
  h2 {{ color: #2a5a8c; margin-top: 36px; border-bottom: 1px solid #ccc;
        padding-bottom: 4px; }}
  .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                   gap: 12px; margin: 16px 0; }}
  .summary-card {{ background: #fff; border: 1px solid #ddd; border-radius: 6px;
                   padding: 14px; text-align: center; }}
  .summary-card .label {{ font-size: 0.85em; color: #666; }}
  .summary-card .value {{ font-size: 1.6em; font-weight: bold; color: #1a3a5c; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 0.92em; }}
  th {{ background: #1a3a5c; color: #fff; padding: 8px 10px; text-align: left; }}
  td {{ padding: 6px 10px; border-bottom: 1px solid #ddd; }}
  tr:nth-child(even) {{ background: #f4f7fa; }}
  tr:hover {{ background: #e8eef5; }}
  .chart-container {{ text-align: center; margin: 16px 0; }}
  .chart-container img {{ max-width: 100%; border: 1px solid #ccc; border-radius: 4px; }}
  .util-cell {{ font-weight: bold; padding: 4px 8px; border-radius: 3px; text-align: center; }}
  .alert-banner {{ background: #fff3cd; border: 1px solid #ffc107; border-radius: 6px;
                   padding: 12px 16px; margin: 16px 0; color: #856404; }}
  .alert-banner h3 {{ margin: 0 0 6px 0; color: #856404; }}
  .over-highlight {{ background: #ffe0e0; font-weight: bold; }}
  .tab-bar {{ display: flex; flex-wrap: wrap; gap: 0; margin-top: 24px;
              border-bottom: 3px solid #1a3a5c; }}
  .tab-btn {{ padding: 10px 22px; cursor: pointer; background: #e8eef5;
              border: 1px solid #ccc; border-bottom: none; border-radius: 6px 6px 0 0;
              font-size: 0.95em; font-weight: bold; color: #1a3a5c;
              margin-right: 2px; transition: background 0.15s; }}
  .tab-btn:hover {{ background: #d0dced; }}
  .tab-btn.active {{ background: #1a3a5c; color: #fff; border-color: #1a3a5c; }}
  .tab-content {{ display: none; padding: 16px 0; }}
  .tab-content.active {{ display: block; }}
  .footer {{ margin-top: 40px; padding-top: 10px; border-top: 1px solid #ccc;
             font-size: 0.82em; color: #888; }}
  @media print {{
    body {{ margin: 10px; }}
    .summary-card {{ break-inside: avoid; }}
    table {{ page-break-inside: auto; }}
    tr {{ page-break-inside: avoid; }}
    .tab-bar {{ display: none; }}
    .tab-content {{ display: block !important; page-break-before: always; }}
  }}
</style>
</head>
<body>
<h1>License Usage Audit Report</h1>
<p style="color:#555;">Generated: {now_str} &nbsp;|&nbsp; Period: {period_str}
   &nbsp;|&nbsp; Type: {meta['period_type'].capitalize()} ({meta['ordinal']})</p>
""")

        # --- Tab bar ---
        h.append('<div class="tab-bar">')
        for idx, label in enumerate(tab_labels):
            active = " active" if idx == 0 else ""
            h.append(f'<div class="tab-btn{active}" onclick="switchTab(\'{tab_ids[idx]}\')">{label}</div>')
        h.append("</div>")

        # ===================== OVERALL TAB =====================
        h.append('<div id="overall" class="tab-content active">')

        # Executive Summary
        h.append('<h2>Executive Summary</h2><div class="summary-grid">')
        for label, value in [
            ("Period", period_str),
            ("Total Checkouts", f"{meta['total_records']:,}"),
            ("Features", meta["unique_features"]),
            ("Companies", meta["unique_companies"]),
            ("Unique Users", meta["unique_users"]),
        ]:
            h.append(
                f'<div class="summary-card"><div class="label">{label}</div>'
                f'<div class="value">{value}</div></div>'
            )
        h.append("</div>")

        # Chart
        h.append(f'<h2>Usage Trend</h2><div class="chart-container">'
                 f'<img src="data:image/png;base64,{chart_b64}" alt="Usage Trend Chart"/></div>')

        # Stats
        h.append("<h2>Feature Statistics</h2>")
        h.append(_stats_table_html(stats))

        # Overuse
        h.append(_overuse_html(overuse, stats))

        # Company Breakdown
        h.append("""<h2>Company Breakdown</h2>
<table>
<tr><th>Company</th><th>Features Used</th><th>Total Checkouts</th>
<th>Unique Users</th><th>Peak Concurrent</th><th>Est. Usage Hours</th></tr>""")
        for c in company_breakdown:
            h.append(
                f'<tr><td>{c["company"]}</td><td>{c["features_used"]}</td>'
                f'<td>{c["total_checkouts"]:,}</td><td>{c["unique_users"]}</td>'
                f'<td>{c["peak_concurrent"]}</td><td>{c.get("est_usage_hours", 0.0)}</td></tr>'
            )
        h.append("</table>")

        # Feature x Company Matrix
        if features and companies:
            h.append('<h2>Feature &times; Company Matrix (Peak Concurrent)</h2>'
                     '<table><tr><th>Feature</th>')
            for comp in companies:
                h.append(f"<th>{comp}</th>")
            h.append("<th>Total</th></tr>")
            for feat in features:
                h.append(f'<tr><td><b>{feat}</b></td>')
                row_total = 0
                for comp in companies:
                    val = matrix[feat][comp]
                    row_total += val
                    h.append(f'<td>{val if val > 0 else "-"}</td>')
                h.append(f"<td><b>{row_total}</b></td></tr>")
            h.append("<tr><td><b>Total</b></td>")
            grand = 0
            for comp in companies:
                col_sum = sum(matrix[f][comp] for f in features)
                grand += col_sum
                h.append(f"<td><b>{col_sum}</b></td>")
            h.append(f"<td><b>{grand}</b></td></tr></table>")

        # Top Users
        h.append(_top_users_html(top_users))

        # User Activity
        if user_activity:
            h.append("""<h2>User Activity</h2>
<table>
<tr><th>User</th><th>Company</th><th>Features Used</th><th>Total Checkouts</th>
<th>Est. Usage Hours</th><th>Active Days</th><th>First Active</th>
<th>Last Active</th><th>Avg Hours/Day</th></tr>""")
            for ua in user_activity:
                h.append(
                    f'<tr><td>{ua["user"]}</td><td>{ua["company"]}</td>'
                    f'<td>{ua["features_used"]}</td><td>{ua["total_checkouts"]:,}</td>'
                    f'<td>{ua["est_usage_hours"]}</td><td>{ua["active_days"]}</td>'
                    f'<td>{ua["first_active"]}</td><td>{ua["last_active"]}</td>'
                    f'<td>{ua["avg_hours_day"]}</td></tr>'
                )
            h.append("</table>")

        h.append("</div>")  # end overall tab

        # ===================== COMPANY TABS =====================
        for idx, (comp_name, cdata) in enumerate(company_tabs.items()):
            tab_id = f"comp_{idx}"
            h.append(f'<div id="{tab_id}" class="tab-content">')
            h.append(f"<h2>{comp_name} — Summary</h2>")

            # Mini summary cards
            h.append('<div class="summary-grid">')
            for label, value in [
                ("Company", comp_name),
                ("Total Checkouts", f"{cdata['total_records']:,}"),
                ("Features Used", cdata["unique_features"]),
                ("Unique Users", cdata["unique_users"]),
            ]:
                h.append(
                    f'<div class="summary-card"><div class="label">{label}</div>'
                    f'<div class="value">{value}</div></div>'
                )
            h.append("</div>")

            # Company chart
            h.append(f'<h2>{comp_name} — Usage Trend</h2><div class="chart-container">'
                     f'<img src="data:image/png;base64,{cdata["chart_b64"]}" '
                     f'alt="{comp_name} Usage Trend"/></div>')

            # Company stats
            h.append(f"<h2>{comp_name} — Feature Statistics</h2>")
            h.append(_stats_table_html(cdata["stats"]))

            # Company overuse
            h.append(_overuse_html(cdata["overuse"], cdata["stats"]))

            # Company top users
            h.append(_top_users_html(cdata["top_users"]))

            h.append("</div>")  # end company tab

        # ===================== FOOTER & JS =====================
        h.append(f"""
<div class="footer">
License Monitor Audit Report &mdash; Generated {now_str}<br>
Source: {str(BASE_DIR)}
</div>
<script>
function switchTab(tabId) {{
  document.querySelectorAll('.tab-content').forEach(function(el) {{
    el.classList.remove('active');
  }});
  document.querySelectorAll('.tab-btn').forEach(function(el) {{
    el.classList.remove('active');
  }});
  document.getElementById(tabId).classList.add('active');
  var btns = document.querySelectorAll('.tab-btn');
  var ids = {str(tab_ids)};
  for (var i = 0; i < ids.length; i++) {{
    if (ids[i] === tabId) {{ btns[i].classList.add('active'); break; }}
  }}
}}
</script>
</body></html>""")

        return "\n".join(h)

    def _export_html(self):
        """Export a self-contained HTML audit report."""
        if self.filtered_data is None or self.filtered_data.empty:
            QMessageBox.warning(self, "No Data", "Nothing to export. Run Analyze first.")
            return

        start_qd = self.start_date_edit.date()
        end_qd = self.end_date_edit.date()
        start_d = date(start_qd.year(), start_qd.month(), start_qd.day())
        end_d = date(end_qd.year(), end_qd.month(), end_qd.day())

        period_type, ordinal = self._determine_period_info(start_d, end_d)

        # Build filename
        now = datetime.now()
        ts_prefix = now.strftime("%Y%m%d_%H%M%S")
        filename = f"{ts_prefix}_{ordinal}_{period_type}.html"

        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        export_path = EXPORT_DIR / filename

        self.status_bar.showMessage("Generating HTML report...")
        QApplication.processEvents()

        try:
            df = self.filtered_data

            # --- Overall data (policy scoped to filtered users) ---
            period_hours = self._get_period_hours()
            all_users = set(df["user"].unique())
            overall_policy = self._policy_map_for_users(all_users)
            chart_b64 = self._render_chart_to_base64(df, start_d, end_d, overall_policy)
            stats = self._build_stats_rows(df, overall_policy, period_hours)
            overuse = self._build_overuse_analysis(df, overall_policy)
            company_bd = self._build_company_breakdown(df)
            feat_comp = self._build_feature_company_matrix(df)
            top_users = self._build_top_users(df)
            user_activity = self._build_user_activity(df)

            meta = {
                "generated": now.strftime("%Y-%m-%d %H:%M:%S"),
                "start_date": str(start_d),
                "end_date": str(end_d),
                "period_type": period_type,
                "ordinal": ordinal,
                "total_records": len(df),
                "unique_features": df["feature"].nunique(),
                "unique_companies": df["company"].nunique(),
                "unique_users": df["user"].nunique(),
            }

            # --- Per-company data (policy scoped to company users) ---
            company_tabs = {}
            for comp in sorted(df["company"].unique()):
                cdf = df[df["company"] == comp]
                comp_users = set(cdf["user"].unique())
                comp_policy = self._policy_map_for_users(comp_users)
                company_tabs[comp] = {
                    "chart_b64": self._render_chart_to_base64(cdf, start_d, end_d, comp_policy),
                    "stats": self._build_stats_rows(cdf, comp_policy, period_hours),
                    "overuse": self._build_overuse_analysis(cdf, comp_policy),
                    "top_users": self._build_top_users(cdf),
                    "total_records": len(cdf),
                    "unique_features": cdf["feature"].nunique(),
                    "unique_users": cdf["user"].nunique(),
                }
                self.status_bar.showMessage(f"Generating report... ({comp})")
                QApplication.processEvents()

            html = self._generate_html(chart_b64, stats, company_bd,
                                       feat_comp, top_users, overuse,
                                       user_activity, company_tabs, meta)

            with open(export_path, "w", encoding="utf-8") as f:
                f.write(html)

            self.status_bar.showMessage(f"HTML report exported: {export_path}")
            QMessageBox.information(
                self, "Export Complete",
                f"HTML audit report saved to:\n{export_path}"
            )
        except Exception as e:
            self.status_bar.showMessage(f"Export error: {e}")
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
