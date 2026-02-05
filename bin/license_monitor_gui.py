#!/usr/local/python-3.12.2/bin/python3.12
"""
License Monitor GUI Dashboard
================================================================================
Interactive dashboard for visualizing license usage with:
- Date range / period selection (week/month/quarter/year)
- Feature, company, user filtering
- Time-series line graphs with policy overlays
- Utilization metrics and statistics
- Export capabilities
================================================================================
"""

import sys
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QDateEdit, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QTabWidget, QSpinBox, QCheckBox, QGroupBox, QGridLayout, QMessageBox,
    QFileDialog, QProgressBar, QStatusBar, QSplitter, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt, QDate, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QFont

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.dates import DateFormatter, MonthLocator, WeekdayLocator
import matplotlib.dates as mdates

import pandas as pd
import numpy as np


# ============================================================
# Configuration
# ============================================================

# Try to read from environment, fallback to defaults
BASE_DIR = Path(os.environ.get(
    "LICENSE_MONITOR_HOME",
    Path(__file__).parent.parent
))
DB_PATH = BASE_DIR / "db" / "license_monitor.db"
REPORTS_DIR = BASE_DIR / "reports"


# ============================================================
# Database Helper
# ============================================================

class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path

    def get_connection(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def get_features(self):
        """Get all unique features"""
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT feature FROM lmstat_snapshot ORDER BY feature")
        features = [row[0] for row in cur.fetchall()]
        conn.close()
        return features

    def get_companies(self):
        """Get all unique companies"""
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT substr(user, 1, instr(user, '-') - 1) as company
            FROM lmstat_snapshot
            WHERE user LIKE '%-%'
            ORDER BY company
        """)
        companies = [row[0] for row in cur.fetchall()]
        conn.close()
        return companies

    def get_users(self, company=None):
        """Get users, optionally filtered by company"""
        conn = self.get_connection()
        cur = conn.cursor()
        if company:
            cur.execute(
                "SELECT DISTINCT user FROM lmstat_snapshot WHERE user LIKE ? ORDER BY user",
                (f"{company}-%",)
            )
        else:
            cur.execute("SELECT DISTINCT user FROM lmstat_snapshot ORDER BY user")
        users = [row[0] for row in cur.fetchall()]
        conn.close()
        return users

    def get_date_range(self):
        """Get min and max dates in database"""
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT
              MIN(datetime(substr(ts,1,4) || '-' || substr(ts,6,2) || '-' || substr(ts,9,2))) as min_ts,
              MAX(datetime(substr(ts,1,4) || '-' || substr(ts,6,2) || '-' || substr(ts,9,2))) as max_ts
            FROM lmstat_snapshot
        """)
        result = cur.fetchone()
        conn.close()
        if result[0] and result[1]:
            return datetime.fromisoformat(result[0]), datetime.fromisoformat(result[1])
        return datetime.now() - timedelta(days=30), datetime.now()

    def query_usage_data(self, start_date, end_date, features=None, companies=None, users=None, raw_snapshots=False):
        """Query time-series usage data with optional filters
        
        Args:
            raw_snapshots: If True, return raw snapshots for minute-by-minute (no aggregation).
                          If False, return aggregated data for hourly/daily views.
        """
        conn = self.get_connection()
        cur = conn.cursor()

        if raw_snapshots:
            # For minute-by-minute: Return all individual snapshots as collected
            query = """
                SELECT
                  ts,
                  substr(user, 1, instr(user, '-') - 1) as company,
                  feature,
                  user,
                  1 as snapshot_count,
                  1 as active_users,
                  ROUND(5 / 60.0, 2) as usage_hours
                FROM lmstat_snapshot
                WHERE
                  substr(ts, 1, 10) BETWEEN ? AND ?
            """
        else:
            # For hourly/daily: Aggregate snapshots
            query = """
                SELECT
                  ts,
                  substr(user, 1, instr(user, '-') - 1) as company,
                  feature,
                  user,
                  COUNT(*) as snapshot_count,
                  COUNT(DISTINCT user) as active_users,
                  ROUND(COUNT(*) * 5 / 60.0, 2) as usage_hours
                FROM lmstat_snapshot
                WHERE
                  substr(ts, 1, 10) BETWEEN ? AND ?
            """

        params = [start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")]

        if features and len(features) > 0:
            placeholders = ",".join("?" * len(features))
            query += f" AND feature IN ({placeholders})"
            params.extend(features)

        if companies and len(companies) > 0:
            company_pattern = " OR ".join([f"user LIKE ?" for _ in companies])
            query += f" AND ({company_pattern})"
            for company in companies:
                params.append(f"{company}-%")

        if users and len(users) > 0:
            placeholders = ",".join("?" * len(users))
            query += f" AND user IN ({placeholders})"
            params.extend(users)

        if not raw_snapshots:
            query += " GROUP BY ts, company, feature, user"
        
        query += " ORDER BY ts, feature"

        cur.execute(query, params)
        rows = cur.fetchall()
        conn.close()

        return pd.DataFrame([dict(row) for row in rows])

    def get_summary_stats(self, start_date, end_date, features=None, companies=None):
        """Get summary statistics for the selected period.

        Computes proper avg_concurrent and peak_concurrent by counting
        concurrent checkouts per snapshot, then aggregating.
        Also fetches policy_max for utilization_pct calculation.
        """
        conn = self.get_connection()
        cur = conn.cursor()

        # Build WHERE clause for filters
        where_clauses = ["substr(ts, 1, 10) BETWEEN ? AND ?"]
        params = [start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")]

        if features and len(features) > 0:
            placeholders = ",".join("?" * len(features))
            where_clauses.append(f"feature IN ({placeholders})")
            params.extend(features)

        if companies and len(companies) > 0:
            company_pattern = " OR ".join([f"user LIKE ?" for _ in companies])
            where_clauses.append(f"({company_pattern})")
            for company in companies:
                params.append(f"{company}-%")

        where_sql = " AND ".join(where_clauses)

        # Step 1: Get basic per-feature stats
        query_basic = f"""
            SELECT
              feature,
              COUNT(*) as total_snapshots,
              COUNT(DISTINCT user) as unique_users,
              COUNT(DISTINCT date(substr(ts,1,10))) as active_days
            FROM lmstat_snapshot
            WHERE {where_sql}
            GROUP BY feature ORDER BY feature
        """

        # Step 2: Get concurrent counts per snapshot per feature,
        # then compute avg and peak concurrent
        query_concurrent = f"""
            SELECT
              feature,
              ROUND(AVG(concurrent_count), 2) as avg_concurrent,
              MAX(concurrent_count) as peak_concurrent
            FROM (
              SELECT
                ts, feature,
                COUNT(*) as concurrent_count
              FROM lmstat_snapshot
              WHERE {where_sql}
              GROUP BY ts, feature
            )
            GROUP BY feature
        """

        cur.execute(query_basic, params)
        basic_rows = cur.fetchall()
        basic_df = pd.DataFrame([dict(row) for row in basic_rows])

        cur.execute(query_concurrent, params)
        conc_rows = cur.fetchall()
        conc_df = pd.DataFrame([dict(row) for row in conc_rows])

        # Step 3: Get policy_max per feature (across all companies)
        policy_query = """
            SELECT feature, MAX(policy_max) as policy_max
            FROM license_policy
            GROUP BY feature
        """
        cur.execute(policy_query)
        policy_rows = cur.fetchall()
        policy_df = pd.DataFrame([dict(row) for row in policy_rows])

        conn.close()

        if basic_df.empty:
            return basic_df

        # Merge basic + concurrent
        result = basic_df.merge(conc_df, on='feature', how='left')

        # Merge policy
        if not policy_df.empty:
            result = result.merge(policy_df, on='feature', how='left')
        else:
            result['policy_max'] = None

        # Compute utilization_pct
        result['utilization_pct'] = result.apply(
            lambda r: round(r['avg_concurrent'] / r['policy_max'] * 100, 1)
            if pd.notna(r.get('policy_max')) and r.get('policy_max', 0) > 0
            else None,
            axis=1
        )

        return result


# ============================================================
# Data Loading Thread (non-blocking)
# ============================================================

class DataLoaderThread(QThread):
    data_loaded = pyqtSignal(object)
    error_occurred = pyqtSignal(str)

    def __init__(self, db_manager, start_date, end_date, features, companies, users, timeline="Daily"):
        super().__init__()
        self.db_manager = db_manager
        self.start_date = start_date
        self.end_date = end_date
        self.features = features
        self.companies = companies
        self.users = users
        self.timeline = timeline

    def run(self):
        try:
            # For minute-by-minute, fetch raw snapshots; otherwise aggregate
            raw_snapshots = (self.timeline == "Minute-by-Minute")
            data = self.db_manager.query_usage_data(
                self.start_date, self.end_date, self.features, self.companies, self.users,
                raw_snapshots=raw_snapshots
            )
            self.data_loaded.emit(data)
        except Exception as e:
            self.error_occurred.emit(str(e))


# ============================================================
# Main GUI Application
# ============================================================

class LicenseMonitorGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("License Monitor Dashboard")
        self.setGeometry(100, 100, 1400, 900)

        self.db_manager = DatabaseManager(DB_PATH)
        self.current_data = None
        self.data_loader_thread = None

        self.init_ui()
        self.load_filter_options()
        self.apply_filters()

    def init_ui(self):
        """Initialize UI components"""
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout()

        # ============================================================
        # FILTER PANEL
        # ============================================================
        filter_group = QGroupBox("Filters & Options")
        filter_layout = QGridLayout()

        # Date range
        filter_layout.addWidget(QLabel("Start Date:"), 0, 0)
        self.start_date_edit = QDateEdit()
        min_date, max_date = self.db_manager.get_date_range()
        self.start_date_edit.setDate(QDate(min_date.year, min_date.month, min_date.day))
        filter_layout.addWidget(self.start_date_edit, 0, 1)

        filter_layout.addWidget(QLabel("End Date:"), 0, 2)
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setDate(QDate(max_date.year, max_date.month, max_date.day))
        filter_layout.addWidget(self.end_date_edit, 0, 3)

        # Period preset buttons
        filter_layout.addWidget(QLabel("Period:"), 0, 4)
        self.period_combo = QComboBox()
        self.period_combo.addItems(["Custom", "Last 7 Days", "Last 30 Days", "Last 90 Days", "Year-to-Date"])
        self.period_combo.currentTextChanged.connect(self.on_period_changed)
        filter_layout.addWidget(self.period_combo, 0, 5)

        # Timeline granularity selector
        filter_layout.addWidget(QLabel("Timeline:"), 0, 6)
        self.timeline_combo = QComboBox()
        self.timeline_combo.addItems(["Daily", "Hourly", "Minute-by-Minute"])
        self.timeline_combo.currentTextChanged.connect(self.on_timeline_changed)
        filter_layout.addWidget(self.timeline_combo, 0, 7)

        # Feature selection
        filter_layout.addWidget(QLabel("Features:"), 1, 0)
        self.feature_list = QListWidget()
        self.feature_list.setMaximumHeight(80)
        self.feature_list.itemSelectionChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.feature_list, 1, 1, 1, 2)

        # Company selection
        filter_layout.addWidget(QLabel("Companies:"), 1, 3)
        self.company_list = QListWidget()
        self.company_list.setMaximumHeight(80)
        self.company_list.itemSelectionChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.company_list, 1, 4, 1, 2)

        # User selection
        filter_layout.addWidget(QLabel("Users:"), 2, 0)
        self.user_list = QListWidget()
        self.user_list.setMaximumHeight(80)
        self.user_list.itemSelectionChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.user_list, 2, 1, 1, 2)

        # Action buttons
        filter_layout.addWidget(QLabel("Actions:"), 2, 3)
        self.apply_btn = QPushButton("Apply Filters")
        self.apply_btn.clicked.connect(self.apply_filters)
        filter_layout.addWidget(self.apply_btn, 2, 4)

        self.export_btn = QPushButton("Export CSV")
        self.export_btn.clicked.connect(self.export_data)
        filter_layout.addWidget(self.export_btn, 2, 5)

        filter_group.setLayout(filter_layout)
        main_layout.addWidget(filter_group)

        # ============================================================
        # PROGRESS BAR
        # ============================================================
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # ============================================================
        # TABS
        # ============================================================
        tabs = QTabWidget()

        # TAB 1: Time Series Chart
        self.chart_widget = QWidget()
        chart_layout = QVBoxLayout()
        self.figure = Figure(figsize=(12, 6), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        chart_layout.addWidget(self.canvas)
        self.chart_widget.setLayout(chart_layout)
        tabs.addTab(self.chart_widget, "📈 Usage Trend")

        # TAB 2: Summary Statistics
        self.stats_table = QTableWidget()
        self.stats_table.setColumnCount(8)
        self.stats_table.setHorizontalHeaderLabels([
            "Feature", "Total Snapshots", "Unique Users", "Active Days",
            "Avg Concurrent", "Peak Concurrent", "Policy Max", "Utilization %"
        ])
        tabs.addTab(self.stats_table, "📊 Statistics")

        # TAB 3: Detailed Usage
        self.detail_table = QTableWidget()
        self.detail_table.setColumnCount(7)
        self.detail_table.setHorizontalHeaderLabels([
            "Timestamp", "Company", "Feature", "User", "Snapshots", "Active Users", "Usage Hours"
        ])
        tabs.addTab(self.detail_table, "📋 Details")

        main_layout.addWidget(tabs)

        # ============================================================
        # STATUS BAR
        # ============================================================
        self.status_label = QStatusBar()
        self.setStatusBar(self.status_label)

        main_widget.setLayout(main_layout)

    def load_filter_options(self):
        """Load available filters from database"""
        # Load features
        features = self.db_manager.get_features()
        self.feature_list.clear()
        for feature in features:
            item = self.feature_list.addItem(feature)
        self.feature_list.selectAll()

        # Load companies
        companies = self.db_manager.get_companies()
        self.company_list.clear()
        for company in companies:
            self.company_list.addItem(company)
        self.company_list.selectAll()

        # Load users
        users = self.db_manager.get_users()
        self.user_list.clear()
        for user in users:
            self.user_list.addItem(user)
        self.user_list.selectAll()

    def on_period_changed(self, period_text):
        """Handle period preset selection"""
        today = datetime.now()
        if period_text == "Last 7 Days":
            start = today - timedelta(days=7)
            self.start_date_edit.setDate(QDate(start.year, start.month, start.day))
            self.end_date_edit.setDate(QDate(today.year, today.month, today.day))
        elif period_text == "Last 30 Days":
            start = today - timedelta(days=30)
            self.start_date_edit.setDate(QDate(start.year, start.month, start.day))
            self.end_date_edit.setDate(QDate(today.year, today.month, today.day))
        elif period_text == "Last 90 Days":
            start = today - timedelta(days=90)
            self.start_date_edit.setDate(QDate(start.year, start.month, start.day))
            self.end_date_edit.setDate(QDate(today.year, today.month, today.day))
        elif period_text == "Year-to-Date":
            start = datetime(today.year, 1, 1)
            self.start_date_edit.setDate(QDate(start.year, start.month, start.day))
            self.end_date_edit.setDate(QDate(today.year, today.month, today.day))

    def on_timeline_changed(self, timeline_text):
        """Handle timeline granularity selection change - reload data with appropriate granularity"""
        # Reload data instead of just redrawing, because we need different data for different timelines
        # (raw snapshots for minute-by-minute, aggregated for daily/hourly)
        self.apply_filters()

    def get_selected_filters(self):
        """Get currently selected filters"""
        features = [item.text() for item in self.feature_list.selectedItems()]
        companies = [item.text() for item in self.company_list.selectedItems()]
        users = [item.text() for item in self.user_list.selectedItems()]
        
        start_date = self.start_date_edit.date().toPyDate()
        end_date = self.end_date_edit.date().toPyDate()
        start_date = datetime.combine(start_date, datetime.min.time())
        end_date = datetime.combine(end_date, datetime.max.time())

        return start_date, end_date, features, companies, users

    def apply_filters(self):
        """Apply filters and load data"""
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.showMessage("Loading data...")

        start_date, end_date, features, companies, users = self.get_selected_filters()
        timeline = self.timeline_combo.currentText()

        # Load data in background thread
        self.data_loader_thread = DataLoaderThread(
            self.db_manager, start_date, end_date, features, companies, users, timeline
        )
        self.data_loader_thread.data_loaded.connect(self.on_data_loaded)
        self.data_loader_thread.error_occurred.connect(self.on_data_error)
        self.data_loader_thread.start()

    def on_data_loaded(self, data):
        """Handle loaded data"""
        self.current_data = data
        self.progress_bar.setValue(50)

        self.update_chart(data)
        self.progress_bar.setValue(75)

        self.update_stats_table(data)
        self.progress_bar.setValue(85)

        self.update_detail_table(data)
        self.progress_bar.setValue(100)

        self.status_label.showMessage(f"Loaded {len(data)} records")
        self.progress_bar.setVisible(False)

    def on_data_error(self, error_msg):
        """Handle data loading error"""
        self.status_label.showMessage(f"Error: {error_msg}")
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Error", f"Failed to load data:\n{error_msg}")

    def update_chart(self, data):
        """Update the time-series chart with selectable timeline granularity"""
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        if data.empty:
            ax.text(0.5, 0.5, 'No data available', ha='center', va='center',
                    transform=ax.transAxes, fontsize=14)
            self.canvas.draw()
            return

        # Get selected timeline granularity
        timeline = self.timeline_combo.currentText()
        
        # Parse timestamps
        data_copy = data.copy()
        # Handle timestamp format: 2026-01-28_10-04-22
        data_copy['datetime'] = pd.to_datetime(
            data_copy['ts'].str.replace('_', ' ').str.replace('-', ' ').str.replace('  ', ' '),
            format='%Y %m %d %H %M %S', errors='coerce'
        )
        
        # For minute-by-minute: plot raw snapshots directly without aggregation
        if timeline == "Minute-by-Minute":
            x_label = 'Time (Minute)'
            # Sort by datetime for continuous line
            data_copy = data_copy.sort_values('datetime')
            
            # Plot lines for each feature
            for feature in data_copy['feature'].unique():
                feature_data = data_copy[data_copy['feature'] == feature]
                feature_data = feature_data.sort_values('datetime')
                ax.plot(feature_data['datetime'], feature_data['usage_hours'],
                       marker='o', label=feature, linewidth=2, markersize=4)
        else:
            # For Daily/Hourly: aggregate by time bin
            if timeline == "Hourly":
                data_copy['time_bin'] = data_copy['datetime'].dt.strftime('%Y-%m-%d %H:00')
                x_label = 'Time (Hour)'
            else:  # Daily (default)
                data_copy['time_bin'] = data_copy['datetime'].dt.strftime('%Y-%m-%d')
                x_label = 'Date (Day)'
            
            # Aggregate by time bin and feature
            by_time_feature = data_copy.groupby(['time_bin', 'feature'])['usage_hours'].sum().reset_index()
            by_time_feature['datetime'] = pd.to_datetime(by_time_feature['time_bin'])
            
            # Plot lines for each feature
            for feature in by_time_feature['feature'].unique():
                feature_data = by_time_feature[by_time_feature['feature'] == feature]
                feature_data = feature_data.sort_values('datetime')
                ax.plot(feature_data['datetime'], feature_data['usage_hours'],
                       marker='o', label=feature, linewidth=2, markersize=4)

        ax.set_xlabel(x_label, fontsize=11, fontweight='bold')
        ax.set_ylabel('Usage (Hours)', fontsize=11, fontweight='bold')
        ax.set_title(f'License Usage Over Time ({timeline} Timeline)', fontsize=13, fontweight='bold')
        ax.legend(loc='best', fontsize=9)
        ax.grid(True, alpha=0.3)
        if timeline == "Daily":
            ax.xaxis.set_major_formatter(DateFormatter("%Y-%m-%d"))
        else:
            ax.xaxis.set_major_formatter(DateFormatter("%Y-%m-%d %H:%M"))
        self.figure.autofmt_xdate(rotation=45)
        self.figure.tight_layout()
        self.canvas.draw()

    def update_stats_table(self, data):
        """Update statistics table"""
        self.stats_table.setRowCount(0)

        if data.empty:
            return

        stats = self.db_manager.get_summary_stats(
            self.start_date_edit.date().toPyDate(),
            self.end_date_edit.date().toPyDate(),
            [item.text() for item in self.feature_list.selectedItems()],
            [item.text() for item in self.company_list.selectedItems()]
        )

        for idx, row in stats.iterrows():
            self.stats_table.insertRow(idx)
            self.stats_table.setItem(idx, 0, QTableWidgetItem(str(row['feature'])))
            self.stats_table.setItem(idx, 1, QTableWidgetItem(str(row['total_snapshots'])))
            self.stats_table.setItem(idx, 2, QTableWidgetItem(str(row['unique_users'])))
            self.stats_table.setItem(idx, 3, QTableWidgetItem(str(row['active_days'])))
            self.stats_table.setItem(idx, 4, QTableWidgetItem(str(row['avg_concurrent'])))

            peak = row.get('peak_concurrent', '')
            self.stats_table.setItem(idx, 5, QTableWidgetItem(str(peak if pd.notna(peak) else '')))

            policy_max = row.get('policy_max', '')
            self.stats_table.setItem(idx, 6, QTableWidgetItem(str(int(policy_max) if pd.notna(policy_max) else 'N/A')))

            utilization_pct = row.get('utilization_pct')
            if pd.notna(utilization_pct):
                util_item = QTableWidgetItem(f"{utilization_pct:.1f}%")
                if utilization_pct >= 80:
                    util_item.setBackground(QColor(144, 238, 144))  # Light green
                elif utilization_pct >= 30:
                    util_item.setBackground(QColor(255, 255, 153))  # Light yellow
                else:
                    util_item.setBackground(QColor(255, 182, 182))  # Light red
            else:
                util_item = QTableWidgetItem("N/A")
            self.stats_table.setItem(idx, 7, util_item)

        self.stats_table.resizeColumnsToContents()

    def update_detail_table(self, data):
        """Update detailed usage table"""
        self.detail_table.setRowCount(0)

        if data.empty:
            return

        for idx, row in data.iterrows():
            self.detail_table.insertRow(idx)
            self.detail_table.setItem(idx, 0, QTableWidgetItem(str(row['ts'])))
            self.detail_table.setItem(idx, 1, QTableWidgetItem(str(row['company'])))
            self.detail_table.setItem(idx, 2, QTableWidgetItem(str(row['feature'])))
            self.detail_table.setItem(idx, 3, QTableWidgetItem(str(row['user'])))
            self.detail_table.setItem(idx, 4, QTableWidgetItem(str(row['snapshot_count'])))
            self.detail_table.setItem(idx, 5, QTableWidgetItem(str(row['active_users'])))
            self.detail_table.setItem(idx, 6, QTableWidgetItem(str(row['usage_hours'])))

        self.detail_table.resizeColumnsToContents()

    def export_data(self):
        """Export current data to CSV"""
        if self.current_data is None or self.current_data.empty:
            QMessageBox.warning(self, "Warning", "No data to export")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Data", "", "CSV Files (*.csv);;All Files (*)"
        )

        if file_path:
            try:
                self.current_data.to_csv(file_path, index=False)
                QMessageBox.information(self, "Success", f"Data exported to:\n{file_path}")
                self.status_label.showMessage(f"Exported to {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export:\n{str(e)}")


def main():
    app = QApplication(sys.argv)
    gui = LicenseMonitorGUI()
    gui.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
