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
from datetime import datetime, date, timedelta
import calendar
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QDateEdit, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QTabWidget, QGroupBox, QGridLayout, QMessageBox,
    QFileDialog, QProgressBar, QStatusBar, QListWidget, QListWidgetItem,
    QAbstractItemView, QFrame, QCheckBox, QComboBox,
    QSplitter, QLineEdit,
)
from PyQt5.QtCore import Qt, QDate, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QColor

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.dates import DateFormatter
import matplotlib.dates as mdates

import pandas as pd

import hashlib
import hmac as _hmac
import uuid
import json
import platform
import urllib.request
import urllib.error
from cryptography.fernet import Fernet


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
SNAPSHOT_INTERVAL_MIN = None       # auto-detected from data via median gap


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

                        if user_company_map and user in user_company_map:
                            company = user_company_map[user]
                        elif "-" in user:
                            company = user.split("-")[0]
                        else:
                            company = "unknown"

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
# LicenseManager — key-based authorization with trial
# ============================================================

_LICENSE_SECRET = b"lmon-monitor-secret-2026"   # embedded signing key
_LICENSE_SERVER_URL = ""                          # set to your validation endpoint URL
_TRIAL_DAYS = 14
_STATE_PATH = Path.home() / ".license_monitor_state.json"

def _get_encryption_key(machine_id):
    """Derive a Fernet encryption key from machine ID."""
    hash_obj = hashlib.sha256(machine_id.encode())
    return base64.urlsafe_b64encode(hash_obj.digest())

class LicenseManager:
    """Manages trial period and license key validation."""

    def __init__(self):
        self.state = self.load_state()

    def get_machine_id(self):
        """Generate stable machine fingerprint from hostname, processor, and MAC address."""
        try:
            parts = [
                platform.node(),                    # hostname
                platform.processor() or "generic",  # CPU info
                str(uuid.getnode()),                # MAC address as int
            ]
            fingerprint = ":".join(parts)
            return hashlib.sha256(fingerprint.encode()).hexdigest()
        except Exception:
            return hashlib.sha256(b"unknown_machine").hexdigest()

    def get_machine_short(self, machine_id=None):
        """Return first 8 uppercase hex chars of machine_id."""
        if machine_id is None:
            machine_id = self.get_machine_id()
        return machine_id[:8].upper()

    def load_state(self):
        """Load and decrypt state from ~/.license_monitor_state.json, creating if necessary."""
        machine_id = self.get_machine_id()
        key = _get_encryption_key(machine_id)
        cipher = Fernet(key)

        if _STATE_PATH.exists():
            try:
                # Try to decrypt the file (new format)
                with open(_STATE_PATH, 'rb') as f:
                    encrypted_data = f.read()
                decrypted = cipher.decrypt(encrypted_data)
                return json.loads(decrypted)
            except Exception:
                pass

            try:
                # Fall back to plain JSON (old format)
                with open(_STATE_PATH, encoding="utf-8") as f:
                    state = json.load(f)
                # Re-save in encrypted format
                self.save_state(state)
                return state
            except Exception:
                pass

        # First run: create initial state
        state = {
            "first_run": str(date.today()),
            "machine_id": machine_id,
            "activated": False,
            "key": None,
            "key_expiry": None,
            "activation_date": None,
        }
        self.save_state(state)
        return state

    def save_state(self, state=None):
        """Encrypt and write state dict to ~/.license_monitor_state.json."""
        if state is None:
            state = self.state
        try:
            _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

            # Encrypt the JSON data
            json_data = json.dumps(state, indent=2).encode()
            key = _get_encryption_key(state.get("machine_id", self.get_machine_id()))
            cipher = Fernet(key)
            encrypted_data = cipher.encrypt(json_data)

            # Write encrypted bytes
            with open(_STATE_PATH, 'wb') as f:
                f.write(encrypted_data)
        except Exception:
            pass

    def check(self):
        """Check license status. Returns (status_str, message_str).

        Status values:
          'ok' → fully activated, not expiring
          'trial' → in trial period
          'trial_expiring' → trial about to expire (< 7 days left)
          'expired' → trial or key expired
        """
        today = date.today()

        # Check if activated with a key
        if self.state.get("activated") and self.state.get("key_expiry"):
            try:
                expiry = datetime.strptime(self.state["key_expiry"], "%Y-%m-%d").date()
                if today > expiry:
                    return ("expired", f"License key expired on {expiry}. Please enter a new key.")
                days_left = (expiry - today).days
                if days_left <= 7:
                    return ("trial_expiring", f"License expires in {days_left} days. Please renew.")
                return ("ok", f"Activated until {expiry}")
            except Exception:
                pass

        # Check trial period
        try:
            first_run = datetime.strptime(self.state["first_run"], "%Y-%m-%d").date()
            days_used = (today - first_run).days
            days_remaining = _TRIAL_DAYS - days_used

            if days_remaining <= 0:
                return ("expired", "Trial period expired. Please enter a license key to continue.")
            if days_remaining <= 7:
                return ("trial_expiring", f"Trial expires in {days_remaining} days. Enter a license key to continue.")
            return ("trial", f"Trial — {days_remaining} days remaining")
        except Exception:
            return ("expired", "Error reading trial state. Please enter a license key.")

    def get_expiry_info(self):
        """Return (expiry_date: date | None, days_remaining: int | None).
        Works for both trial and activated states.
        """
        today = date.today()
        if self.state.get("activated") and self.state.get("key_expiry"):
            try:
                expiry = datetime.strptime(self.state["key_expiry"], "%Y-%m-%d").date()
                return (expiry, (expiry - today).days)
            except Exception:
                pass
        # Trial
        try:
            first_run = datetime.strptime(self.state["first_run"], "%Y-%m-%d").date()
            expiry = first_run + timedelta(days=_TRIAL_DAYS)
            return (expiry, (_TRIAL_DAYS - (today - first_run).days))
        except Exception:
            return (None, None)

    def validate_key_local(self, key):
        """Validate key using local HMAC check. Returns (valid, message)."""
        try:
            # Parse key: LMON-EXPIRY8-MACHINESIG8-VERIFYSIG8
            parts = key.strip().upper().split("-")
            if len(parts) != 4 or parts[0] != "LMON":
                return (False, "Invalid key format (expected LMON-XXXXXXXX-XXXXXXXX-XXXXXXXX)")

            expiry_str = parts[1]  # YYYYMMDD
            machine_sig = parts[2]
            verify_sig = parts[3]

            # Parse and validate expiry date
            try:
                expiry = datetime.strptime(expiry_str, "%Y%m%d").date()
            except ValueError:
                return (False, "Invalid expiry date in key")

            if date.today() > expiry:
                return (False, f"Key expired on {expiry}")

            # Validate machine signature
            current_machine_id = self.get_machine_id()
            current_machine_short = self.get_machine_short(current_machine_id)

            if machine_sig != current_machine_short:
                return (False, "Key is locked to a different machine")

            # Validate HMAC signature
            sig_data = f"{expiry_str}:{machine_sig}".encode()
            expected_sig = _hmac.new(_LICENSE_SECRET, sig_data, hashlib.sha256).hexdigest()[:8].upper()

            if verify_sig != expected_sig:
                return (False, "Invalid key signature (tampered key?)")

            return (True, f"Key valid until {expiry}")
        except Exception as e:
            return (False, f"Error validating key: {str(e)}")

    def validate_key_server(self, key):
        """Validate key via server API. Returns (valid, message, expiry_str|None).

        Only attempts if LICENSE_SERVER_URL is set and reachable.
        Falls back silently to local validation on error.
        """
        if not _LICENSE_SERVER_URL:
            return (None, "", None)  # Skip server check

        try:
            machine_id = self.get_machine_id()
            payload = json.dumps({
                "key": key,
                "machine_id": machine_id,
                "product": "LMON",
            }).encode("utf-8")

            req = urllib.request.Request(
                _LICENSE_SERVER_URL,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
                return (data.get("valid", False), data.get("message", ""), data.get("expiry"))
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, Exception):
            return (None, "", None)  # Fall back to local validation

    def validate_key(self, key):
        """Validate key via server (if available), then local. Returns (valid, message, expiry_str|None)."""
        # Try server first
        server_valid, server_msg, server_expiry = self.validate_key_server(key)
        if server_valid is not None:  # Server responded
            return (server_valid, server_msg, server_expiry)

        # Fall back to local validation
        local_valid, local_msg = self.validate_key_local(key)
        if local_valid:
            # Extract expiry from key for consistency
            try:
                parts = key.strip().upper().split("-")
                if len(parts) >= 2:
                    expiry_str = parts[1]
                    expiry = datetime.strptime(expiry_str, "%Y%m%d").date()
                    return (True, local_msg, expiry.isoformat())
            except Exception:
                pass
        return (local_valid, local_msg, None)

    def activate(self, key):
        """Validate and activate a key. Returns (success, message)."""
        valid, msg, expiry_str = self.validate_key(key)
        if not valid:
            return (False, msg)

        # Update state
        self.state["activated"] = True
        self.state["key"] = key
        self.state["key_expiry"] = expiry_str or date.today().isoformat()
        self.state["activation_date"] = str(date.today())
        self.save_state(self.state)

        return (True, f"License activated successfully. Expires: {self.state['key_expiry']}")


# ============================================================
# LicenseDialog — authorization/trial dialog
# ============================================================

from PyQt5.QtWidgets import QDialog

class LicenseDialog(QDialog):
    """Dialog for trial countdown and license key activation."""

    def __init__(self, parent, license_manager, allow_skip=True):
        super().__init__(parent)
        self.setWindowTitle("License Monitor — Authorization")
        self.setModal(True)
        self.setGeometry(100, 100, 500, 400)
        self.license_manager = license_manager
        self.allow_skip = allow_skip

        # Get current status for display
        status, msg = license_manager.check()
        machine_short = license_manager.get_machine_short()

        # Layout
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("License Monitor Authorization")
        title.setStyleSheet("font-weight: bold; font-size: 14pt;")
        layout.addWidget(title)

        # Status message
        status_label = QLabel(msg)
        status_label.setStyleSheet("color: #1a5c8c; font-size: 11pt;")
        status_label.setWordWrap(True)
        layout.addWidget(status_label)

        # Expiry info block
        layout.addSpacing(6)
        expiry_date, days_left = license_manager.get_expiry_info()

        info_frame = QFrame()
        info_frame.setFrameShape(QFrame.StyledPanel)
        info_frame.setStyleSheet("background-color: #f5f5f5; border-radius: 6px; padding: 8px;")
        info_layout = QVBoxLayout(info_frame)
        info_layout.setSpacing(4)

        if expiry_date:
            date_row = QHBoxLayout()
            date_row.addWidget(QLabel("Expires:"))
            date_val = QLabel(str(expiry_date))
            date_val.setStyleSheet("font-weight: bold; color: #1a5c8c;")
            date_row.addWidget(date_val)
            date_row.addStretch()
            info_layout.addLayout(date_row)

        if days_left is not None:
            days_label = QLabel()
            if days_left > 0:
                days_label.setText(f"{days_left} day{'s' if days_left != 1 else ''} remaining")
                color = "#2e7d32" if days_left > 14 else ("#e65100" if days_left > 7 else "#c62828")
            else:
                days_label.setText("Expired")
                color = "#c62828"
            days_label.setStyleSheet(f"font-size: 13pt; font-weight: bold; color: {color};")
            info_layout.addWidget(days_label)

        layout.addWidget(info_frame)

        # Machine ID info
        layout.addSpacing(8)
        machine_label = QLabel("Machine ID (share with vendor for key generation):")
        machine_label.setStyleSheet("font-weight: bold; font-size: 10pt;")
        layout.addWidget(machine_label)

        machine_id_field = QLineEdit()
        machine_id_field.setText(f"LMON-{machine_short}")
        machine_id_field.setReadOnly(True)
        machine_id_field.setStyleSheet("background-color: #f0f0f0; padding: 4px;")
        layout.addWidget(machine_id_field)

        # Key entry
        layout.addSpacing(12)
        key_label = QLabel("Enter License Key:")
        key_label.setStyleSheet("font-weight: bold; font-size: 10pt;")
        layout.addWidget(key_label)

        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("LMON-XXXXXXXX-XXXXXXXX-XXXXXXXX")
        self.key_input.textChanged.connect(self._auto_uppercase)
        layout.addWidget(self.key_input)

        # Buttons
        layout.addSpacing(12)
        button_layout = QHBoxLayout()

        activate_btn = QPushButton("Activate")
        activate_btn.setStyleSheet("background-color: #4CAF50; color: white; padding: 8px; border-radius: 4px;")
        activate_btn.clicked.connect(self._on_activate)
        button_layout.addWidget(activate_btn)

        if allow_skip:
            continue_btn = QPushButton("Continue Trial")
            continue_btn.setStyleSheet("background-color: #2196F3; color: white; padding: 8px; border-radius: 4px;")
            continue_btn.clicked.connect(self.accept)
            button_layout.addWidget(continue_btn)

        exit_btn = QPushButton("Exit Application")
        exit_btn.setStyleSheet("background-color: #999; color: white; padding: 8px; border-radius: 4px;")
        exit_btn.clicked.connect(self.reject)
        button_layout.addWidget(exit_btn)

        layout.addLayout(button_layout)
        layout.addStretch()

        self.setLayout(layout)

    def _auto_uppercase(self):
        """Auto-uppercase key input."""
        cursor_pos = self.key_input.cursorPosition()
        self.key_input.blockSignals(True)
        self.key_input.setText(self.key_input.text().upper())
        self.key_input.setCursorPosition(cursor_pos)
        self.key_input.blockSignals(False)

    def _on_activate(self):
        """Attempt to activate key."""
        key = self.key_input.text().strip()
        if not key:
            QMessageBox.warning(self, "Empty Key", "Please enter a license key.")
            return

        success, msg = self.license_manager.activate(key)
        if success:
            QMessageBox.information(self, "Activation Success", msg)
            self.accept()
        else:
            QMessageBox.warning(self, "Activation Failed", msg)


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
# IngestThread — run ingest scripts in background
# ============================================================

class IngestThread(QThread):
    """Background thread that runs an ingest Python script."""

    ingest_complete = pyqtSignal(str)   # success message
    error_occurred = pyqtSignal(str)

    def __init__(self, script_path, env_vars, label, args=None):
        super().__init__()
        self.script_path = script_path
        self.env_vars = env_vars
        self.label = label
        self.args = args or []

    def run(self):
        try:
            env = os.environ.copy()
            env.update(self.env_vars)
            cmd = [sys.executable, self.script_path] + self.args
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300, env=env
            )
            if result.returncode != 0:
                err = result.stderr.strip() or result.stdout.strip() or "Unknown error"
                self.error_occurred.emit(f"{self.label} failed:\n{err[:500]}")
                return
            self.ingest_complete.emit(f"{self.label} completed successfully.")
        except subprocess.TimeoutExpired:
            self.error_occurred.emit(f"{self.label} timed out (300s).")
        except Exception as e:
            self.error_occurred.emit(f"{self.label} error: {e}")


# ============================================================
# Helper: time-bin aggregation and X-axis scaling
# ============================================================

def determine_granularity(start_date, end_date):
    """Return (granularity_label, strftime_fmt, tick_format) based on period length."""
    delta = (end_date - start_date).days
    if delta <= 7:
        return "5min", "%Y-%m-%d %H:%M", "%m-%d %H:%M"
    elif delta <= 31:
        return "hourly", "%Y-%m-%d %H:00", "%m-%d %H:00"
    elif delta <= 93:
        return "daily", "%Y-%m-%d", "%Y-%m-%d"
    elif delta <= 365:
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


def aggregate_by_time_bin(df, start_date, end_date, override_granularity=None):
    """Group df by time bin and feature, counting concurrent licenses.

    Returns (aggregated_df, granularity_label, tick_format).
    """
    if df.empty:
        return df, "daily", "%Y-%m-%d"

    if override_granularity:
        gran_formats = {
            "5min": ("%Y-%m-%d %H:%M", "%m-%d %H:%M"),
            "hourly": ("%Y-%m-%d %H:00", "%m-%d %H:00"),
            "daily": ("%Y-%m-%d", "%Y-%m-%d"),
            "weekly": (None, "%G-W%V"),
            "monthly": ("%Y-%m", "%Y-%m"),
        }
        granularity = override_granularity
        bin_fmt, tick_fmt = gran_formats.get(granularity, ("%Y-%m-%d", "%Y-%m-%d"))
    else:
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
    """Generate a complete list of time-bin strings covering [start_date, end_date].

    Stops at current time if end_date is today or in the future to prevent
    chart area extending past 'Now'.
    """
    start_dt = datetime(start_date.year, start_date.month, start_date.day)
    end_of_day = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59)
    now = datetime.now()
    # Don't generate time bins beyond current time
    end_dt = min(end_of_day, now)

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
# Custom table item for numeric sorting with formatted display
# ============================================================

class NumericSortItem(QTableWidgetItem):
    """QTableWidgetItem that displays formatted text but sorts numerically."""
    def __init__(self, display_text, sort_value):
        super().__init__(display_text)
        self._sort_value = sort_value

    def __lt__(self, other):
        if isinstance(other, NumericSortItem):
            return self._sort_value < other._sort_value
        return super().__lt__(other)


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
        self.ingest_thread = None
        self._collect_then_analyze = False
        self.policy_rows = []         # [(user, company, feature, policy_max), ...]
        self.policy_map = {}          # {feature: policy_max} — computed per filter
        self.user_company_map = {}    # {user: company} — from policy
        self.config = {}              # parsed from conf/license_monitor.conf.csh
        self.last_exported_html = None  # track last exported HTML file path

        self._init_ui()
        self._load_policy()
        self._load_config()
        self._check_existing_exports()  # Enable View button if exports exist
        self._update_license_status_bar()  # Show expiry date in status bar

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

        custom_row = QHBoxLayout()
        custom_row.addWidget(QLabel("Period:"))
        custom_row.addWidget(QLabel("Start"))
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDate(QDate.currentDate().addDays(-7))
        self.start_date_edit.dateChanged.connect(self._on_custom_date_changed)
        custom_row.addWidget(self.start_date_edit)
        custom_row.addWidget(QLabel("End"))
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDate(QDate.currentDate())
        self.end_date_edit.dateChanged.connect(self._on_custom_date_changed)
        custom_row.addWidget(self.end_date_edit)
        custom_row.addStretch()
        period_layout.addLayout(custom_row)

        # Quick period selector: granularity combo + period combo
        quick_row = QHBoxLayout()
        quick_row.addWidget(QLabel("Quick:"))
        self.quick_granularity = QComboBox()
        self.quick_granularity.addItems(["(None)", "Weekly", "Monthly", "Quarterly", "Yearly"])
        self.quick_granularity.currentTextChanged.connect(self._on_quick_granularity_changed)
        quick_row.addWidget(self.quick_granularity)
        self.quick_period_combo = QComboBox()
        self.quick_period_combo.setMinimumWidth(140)
        self.quick_period_combo.setEnabled(False)
        self.quick_period_combo.currentTextChanged.connect(self._on_quick_period_changed)
        quick_row.addWidget(self.quick_period_combo)
        quick_row.addStretch()
        period_layout.addLayout(quick_row)

        period_group.setLayout(period_layout)
        top_bar.addWidget(period_group, stretch=7)

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
        self._analyze_btn_default_style = "background-color: #2196F3; color: white;"
        self._analyze_btn_running_style = "background-color: #FFA500; color: white;"
        self._analyze_btn_done_style = "background-color: #4CAF50; color: white;"
        self._analyze_btn_error_style = "background-color: #F44336; color: white;"
        self.analyze_btn.setStyleSheet(self._analyze_btn_default_style)
        self._analyze_anim_timer = QTimer(self)
        self._analyze_anim_timer.setInterval(150)
        self._analyze_anim_dots = 0
        self._analyze_anim_timer.timeout.connect(self._on_analyze_anim_tick)
        self.analyze_btn.clicked.connect(self._run_analyze)
        action_row2.addWidget(self.analyze_btn)
        self.export_btn = QPushButton("Export CSV")
        self.export_btn.clicked.connect(self._export_csv)
        action_row2.addWidget(self.export_btn)
        self.export_html_btn = QPushButton("Export HTML")
        self._export_html_default_style = "background-color: #2196F3; color: white;"
        self._export_html_running_style = "background-color: #FFA500; color: white;"
        self._export_html_done_style = "background-color: #4CAF50; color: white;"
        self._export_html_error_style = "background-color: #F44336; color: white;"
        self.export_html_btn.setStyleSheet(self._export_html_default_style)
        self._export_html_anim_timer = QTimer(self)
        self._export_html_anim_timer.setInterval(150)
        self._export_html_anim_idx = 0
        self._export_html_anim_timer.timeout.connect(self._on_export_html_anim_tick)
        self.export_html_btn.clicked.connect(self._export_html)
        action_row2.addWidget(self.export_html_btn)
        self.view_html_btn = QPushButton("View HTML")
        self.view_html_btn.setToolTip("Open an exported HTML report in your default browser (shows file selection if multiple reports exist)")
        self.view_html_btn.setEnabled(False)  # Disabled until exports exist
        self.view_html_btn.clicked.connect(self._view_html)
        action_row2.addWidget(self.view_html_btn)
        action_layout.addLayout(action_row2)

        action_row3 = QHBoxLayout()
        self.ingest_lmstat_btn = QPushButton("Ingest Lmstat")
        self.ingest_lmstat_btn.setToolTip("Run ingest_lmstat.py to load raw lmstat files into the database")
        self.ingest_lmstat_btn.clicked.connect(self._run_ingest_lmstat)
        action_row3.addWidget(self.ingest_lmstat_btn)
        self.ingest_policy_btn = QPushButton("Ingest Policy")
        self.ingest_policy_btn.setToolTip("Run ingest_policy.py to reload policy from options.opt into the database")
        self.ingest_policy_btn.clicked.connect(self._run_ingest_policy)
        action_row3.addWidget(self.ingest_policy_btn)

        self.manage_license_btn = QPushButton("Manage License")
        self.manage_license_btn.setToolTip("View license status or activate a license key")
        self.manage_license_btn.clicked.connect(self._manage_license)
        action_row3.addWidget(self.manage_license_btn)

        action_layout.addLayout(action_row3)

        action_group.setLayout(action_layout)
        top_bar.addWidget(action_group, stretch=3)

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

        # -- Companies (50%) --
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
        left_layout.addWidget(self.company_list, stretch=5)

        # -- Features (40%) --
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
        left_layout.addWidget(self.feature_list, stretch=4)

        # -- Users (10%) --
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
        left_layout.addWidget(self.user_list, stretch=1)

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
        self.chart_type_cb.addItems(["Area", "Bar", "Line", "Step"])
        self.chart_type_cb.setCurrentIndex(0)  # Area
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

        chart_opts.addWidget(QLabel("Scale:"))
        self.granularity_cb = QComboBox()
        self.granularity_cb.addItems(["Auto", "5min", "Hourly", "Daily", "Weekly", "Monthly"])
        self.granularity_cb.currentIndexChanged.connect(self._on_chart_option_changed)
        chart_opts.addWidget(self.granularity_cb)

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
            "Avg When Active", "Peak Concurrent", "Usage Hours",
            "First Seen", "Last Seen",
            "Policy Max", "Active Util. %", "Period Util. %",
        ])
        # Add tooltips to explain metrics
        header = self.stats_table.horizontalHeader()
        self.stats_table.horizontalHeaderItem(4).setToolTip(
            "Average concurrent licenses during active snapshots only\n"
            "(excludes zero-usage periods)")
        self.stats_table.horizontalHeaderItem(10).setToolTip(
            "Avg When Active / Policy Max × 100%\n"
            "Shows how much of the policy limit is used when feature is active")
        self.stats_table.horizontalHeaderItem(11).setToolTip(
            "Usage Hours / (Policy Max × Period Hours) × 100%\n"
            "Overall utilization across the entire time period")
        header.setStretchLastSection(True)
        self.stats_table.setSortingEnabled(True)
        self.tabs.addTab(self.stats_table, "Statistics")

        # Tab 3: User Activity table
        self.user_activity_table = QTableWidget()
        self.user_activity_table.setColumnCount(12)
        self.user_activity_table.setHorizontalHeaderLabels([
            "User", "Company", "Features Used", "Total Checkouts",
            "Usage Hours", "Active Days", "First Active", "Last Active",
            "Avg Hrs/Day", "Avg Hrs/Day/Copy", "Sessions", "Avg Session Hrs",
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
        # Build company → features and company → users mappings from policy
        self.company_features_map = {}  # {company: set(features)}
        self.company_users_map = {}     # {company: set(users)}
        for user, company, feature, _ in self.policy_rows:
            self.company_features_map.setdefault(company, set()).add(feature)
            self.company_users_map.setdefault(company, set()).add(user)

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
    # Ingest lmstat / policy
    # --------------------------------------------------------
    def _run_ingest_lmstat(self):
        """Run ingest_lmstat.py to load raw files into the database."""
        self.ingest_lmstat_btn.setEnabled(False)
        self.ingest_policy_btn.setEnabled(False)
        self.status_bar.showMessage("Ingesting lmstat data...")

        script = str(BASE_DIR / "bin" / "ingest_lmstat.py")
        env = {
            "RAW_LMSTAT_DIR": str(RAW_DIR),
            "DB_DIR": str(DB_PATH.parent),
        }
        self.ingest_thread = IngestThread(script, env, "Ingest Lmstat")
        self.ingest_thread.ingest_complete.connect(self._on_ingest_complete)
        self.ingest_thread.error_occurred.connect(self._on_ingest_error)
        self.ingest_thread.start()

    def _run_ingest_policy(self):
        """Run ingest_policy.py to reload policy from options.opt."""
        self.ingest_lmstat_btn.setEnabled(False)
        self.ingest_policy_btn.setEnabled(False)
        self.status_bar.showMessage("Ingesting policy...")

        script = str(BASE_DIR / "bin" / "ingest_policy.py")
        env = {
            "LICENSE_MONITOR_HOME": str(BASE_DIR),
        }
        args = [str(BASE_DIR / "bin" / "options.opt")]
        self.ingest_thread = IngestThread(script, env, "Ingest Policy", args=args)
        self.ingest_thread.ingest_complete.connect(self._on_ingest_complete)
        self.ingest_thread.error_occurred.connect(self._on_ingest_error)
        self.ingest_thread.start()

    def _on_ingest_complete(self, msg):
        self.ingest_lmstat_btn.setEnabled(True)
        self.ingest_policy_btn.setEnabled(True)
        self.status_bar.showMessage(msg)
        self._load_policy()

    def _on_ingest_error(self, msg):
        self.ingest_lmstat_btn.setEnabled(True)
        self.ingest_policy_btn.setEnabled(True)
        self.status_bar.showMessage(f"Ingest error: {msg[:100]}")
        QMessageBox.warning(self, "Ingest Error", msg)

    def _manage_license(self):
        """Open the license management dialog."""
        lm = LicenseManager()
        dlg = LicenseDialog(self, lm, allow_skip=True)
        dlg.exec_()

    def _update_license_status_bar(self):
        """Update Manage License button to show license/trial expiry date."""
        try:
            lm = LicenseManager()
            expiry_date, days_left = lm.get_expiry_info()

            if expiry_date and days_left is not None:
                if days_left > 0:
                    self.manage_license_btn.setText(f"Expires: {expiry_date}")
                    self.manage_license_btn.setStyleSheet(
                        "background-color: #e1bee7; color: black; padding: 4px 8px; border-radius: 3px;"
                    )
                else:
                    self.manage_license_btn.setText("Manage License\n(Expired)")
                    self.manage_license_btn.setStyleSheet("")
            else:
                self.manage_license_btn.setText("Manage License")
                self.manage_license_btn.setStyleSheet("")
        except Exception:
            pass  # Silently fail if license info unavailable

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
    # Analyze button animation
    # --------------------------------------------------------
    _SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def _start_analyze_anim(self):
        self._analyze_anim_idx = 0
        self._analyze_anim_timer.start()

    def _stop_analyze_anim(self):
        self._analyze_anim_timer.stop()

    def _on_analyze_anim_tick(self):
        frame = self._SPINNER_FRAMES[self._analyze_anim_idx % len(self._SPINNER_FRAMES)]
        self.analyze_btn.setText(f"{frame}  Analyzing")
        self._analyze_anim_idx += 1

    # --------------------------------------------------------
    # Export HTML button animation
    # --------------------------------------------------------
    def _start_export_html_anim(self):
        self._export_html_anim_idx = 0
        self.export_html_btn.setStyleSheet(self._export_html_running_style)
        self.export_html_btn.setEnabled(False)
        self._export_html_anim_timer.start()

    def _stop_export_html_anim(self, success=True):
        self._export_html_anim_timer.stop()
        self.export_html_btn.setEnabled(True)
        self.export_html_btn.setText("Export HTML")
        if success:
            self.export_html_btn.setStyleSheet(self._export_html_done_style)
        else:
            self.export_html_btn.setStyleSheet(self._export_html_error_style)

    def _on_export_html_anim_tick(self):
        frame = self._SPINNER_FRAMES[self._export_html_anim_idx % len(self._SPINNER_FRAMES)]
        self.export_html_btn.setText(f"{frame}  Exporting")
        self._export_html_anim_idx += 1

    # --------------------------------------------------------
    # Quick period selector
    # --------------------------------------------------------
    def _on_custom_date_changed(self):
        """User manually changed a date picker — deactivate Quick selector."""
        if self.quick_granularity.currentText() != "(None)":
            self.quick_granularity.blockSignals(True)
            self.quick_granularity.setCurrentText("(None)")
            self.quick_granularity.blockSignals(False)
            self.quick_period_combo.blockSignals(True)
            self.quick_period_combo.clear()
            self.quick_period_combo.setEnabled(False)
            self.quick_period_combo.blockSignals(False)
            self.start_date_edit.setEnabled(True)
            self.end_date_edit.setEnabled(True)

    def _on_quick_granularity_changed(self, granularity):
        """Populate the period combo with specific periods for the chosen granularity."""
        is_quick = granularity != "(None)"
        self.start_date_edit.setEnabled(not is_quick)
        self.end_date_edit.setEnabled(not is_quick)

        self.quick_period_combo.blockSignals(True)
        self.quick_period_combo.clear()

        if not is_quick:
            self.quick_period_combo.setEnabled(False)
            self.quick_period_combo.blockSignals(False)
            return

        self.quick_period_combo.setEnabled(True)
        self.analyze_btn.setStyleSheet(self._analyze_btn_default_style)
        self.analyze_btn.setText("Analyze")
        today = date.today()
        year = today.year

        # Add placeholder prompt as first item
        self.quick_period_combo.addItem(f"-- Select {granularity} --")

        if granularity == "Weekly":
            # ISO weeks 01..current week
            current_week = today.isocalendar()[1]
            for w in range(1, current_week + 1):
                self.quick_period_combo.addItem(f"Week-{w:02d}")
        elif granularity == "Monthly":
            for m in range(1, today.month + 1):
                self.quick_period_combo.addItem(f"Month-{m:02d}")
        elif granularity == "Quarterly":
            current_q = (today.month - 1) // 3 + 1
            for q in range(1, current_q + 1):
                self.quick_period_combo.addItem(f"Quarter-{q:02d}")
        elif granularity == "Yearly":
            # Show current year and previous year
            for y in range(year - 1, year + 1):
                self.quick_period_combo.addItem(f"Year-{y}")

        # Start on placeholder so user must explicitly pick an item
        self.quick_period_combo.setCurrentIndex(0)

        self.quick_period_combo.blockSignals(False)

    def _on_quick_period_changed(self, period_text):
        """Compute exact start/end dates from the chosen period and run Analyze."""
        if not period_text or period_text.startswith("-- "):
            return
        granularity = self.quick_granularity.currentText()
        if granularity == "(None)":
            return

        today = date.today()
        year = today.year

        if granularity == "Weekly":
            week = int(period_text.split("-")[1])
            # ISO week: Monday of that week
            jan4 = date(year, 1, 4)  # Jan 4 is always in ISO week 1
            start = jan4 - timedelta(days=jan4.weekday()) + timedelta(weeks=week - 1)
            end = start + timedelta(days=6)
        elif granularity == "Monthly":
            month = int(period_text.split("-")[1])
            start = date(year, month, 1)
            last_day = calendar.monthrange(year, month)[1]
            end = date(year, month, last_day)
        elif granularity == "Quarterly":
            q = int(period_text.split("-")[1])
            start_month = (q - 1) * 3 + 1
            end_month = start_month + 2
            start = date(year, start_month, 1)
            last_day = calendar.monthrange(year, end_month)[1]
            end = date(year, end_month, last_day)
        elif granularity == "Yearly":
            y = int(period_text.split("-")[1])
            start = date(y, 1, 1)
            end = date(y, 12, 31)
        else:
            return

        # Cap end date to today if in the future
        if end > today:
            end = today

        # Block date signals so setting dates doesn't reset Quick
        self.start_date_edit.blockSignals(True)
        self.end_date_edit.blockSignals(True)
        self.start_date_edit.setDate(QDate(start.year, start.month, start.day))
        self.end_date_edit.setDate(QDate(end.year, end.month, end.day))
        self.start_date_edit.blockSignals(False)
        self.end_date_edit.blockSignals(False)
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
        self.analyze_btn.setStyleSheet(self._analyze_btn_running_style)
        self._start_analyze_anim()
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
        self._cached_interval = None   # reset so interval is re-detected
        self._stop_analyze_anim()
        self.analyze_btn.setEnabled(True)
        self.analyze_btn.setText("Analyze")
        self.analyze_btn.setStyleSheet(self._analyze_btn_done_style)
        self.progress_bar.setVisible(False)

        # Compute policy map before populating filters (so policy features appear)
        self._compute_policy_map(None)

        # Populate filter lists — all selected by default
        self._populate_filters(df)

        # Apply filters (initially everything selected) → draw chart + tables
        self._apply_and_refresh()

        interval = self._snapshot_interval_minutes()
        start_str = self.start_date_edit.date().toString("yyyy-MM-dd")
        end_str = self.end_date_edit.date().toString("yyyy-MM-dd")
        rec_count = len(df)
        self.status_bar.showMessage(
            f"Analyzed {file_count} files, {rec_count} records  |  "
            f"Period: {start_str} to {end_str}  |  "
            f"Interval: {interval} min"
        )

    def _on_analysis_error(self, msg):
        self._stop_analyze_anim()
        self.analyze_btn.setEnabled(True)
        self.analyze_btn.setText("Analyze")
        self.analyze_btn.setStyleSheet(self._analyze_btn_error_style)
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
            # Merge features from data with features from policy_map
            data_features = set(df["feature"].unique())
            policy_features = set(self.policy_map.keys())
            all_features = sorted(data_features | policy_features)
            for feat in all_features:
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
        """When company selection changes, auto-select related users and features from policy."""
        if self.raw_data is None or self.raw_data.empty:
            return

        sel_companies = self._get_selected(self.company_list)

        # --- Auto-select users for selected companies ---
        # Merge users from data + policy for the selected companies
        data_users = set()
        policy_users = set()
        if sel_companies:
            data_users = set(
                self.raw_data[self.raw_data["company"].isin(sel_companies)]["user"].unique()
            )
            for comp in sel_companies:
                policy_users |= self.company_users_map.get(comp, set())
        related_users = sorted(data_users | policy_users)

        self.user_list.blockSignals(True)
        self.user_list.clear()
        for usr in related_users:
            item = QListWidgetItem(usr)
            self.user_list.addItem(item)
            item.setSelected(True)
        self.user_list.blockSignals(False)

        # --- Auto-select features for selected companies ---
        # Collect features from policy for selected companies
        policy_features = set()
        for comp in sel_companies:
            policy_features |= self.company_features_map.get(comp, set())

        self.feature_list.blockSignals(True)
        for i in range(self.feature_list.count()):
            item = self.feature_list.item(i)
            item.setSelected(item.text() in policy_features)
        self.feature_list.blockSignals(False)

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

        # Check if user selected a specific granularity or Auto
        user_gran = self.granularity_cb.currentText()
        if user_gran == "Auto":
            agg, granularity, tick_fmt = aggregate_by_time_bin(df, start_d, end_d)
        else:
            # Map user selection to granularity
            display_to_gran = {
                "5min": "5min", "Hourly": "hourly", "Daily": "daily",
                "Weekly": "weekly", "Monthly": "monthly"
            }
            gran_formats = {
                "5min": "%m-%d %H:%M", "hourly": "%m-%d %H:00",
                "daily": "%Y-%m-%d", "weekly": "%G-W%V", "monthly": "%Y-%m"
            }
            granularity = display_to_gran.get(user_gran, "daily")
            tick_fmt = gran_formats.get(granularity, "%Y-%m-%d")
            agg, _, _ = aggregate_by_time_bin(df, start_d, end_d, override_granularity=granularity)

        if agg.empty:
            ax.text(0.5, 0.5, "No data after aggregation", ha="center", va="center",
                    transform=ax.transAxes, fontsize=14, color="gray")
            self.canvas.draw()
            return

        # Fill missing time bins with zero
        gran_bin_fmt = {
            "5min": "%Y-%m-%d %H:%M",
            "hourly": "%Y-%m-%d %H:00",
            "daily": "%Y-%m-%d",
            "weekly": None,
            "monthly": "%Y-%m",
        }
        bin_fmt = gran_bin_fmt.get(granularity)
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

        # Calculate period span in days for bar width scaling
        period_days = (end_d - start_d).days + 1

        if ct == "bar":
            n_feat = max(len(features), 1)
            # Calculate bar width based on granularity and period span
            # Width should be proportional to the time unit, scaled for visibility
            granularity_days = {
                "5min": 5 / 1440,      # 5 minutes in days
                "hourly": 1 / 24,      # 1 hour in days
                "daily": 1,            # 1 day
                "weekly": 7,           # 7 days
                "monthly": 30,         # ~30 days
            }
            unit_days = granularity_days.get(granularity, 1)
            # Scale bar width: 80% of unit width, divided by number of features
            base_w = unit_days * 0.8
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
                                    linestyle=ls, label=feat,
                                    drawstyle="steps-post")
                    ax.fill_between(x, y, alpha=0.15, color=line.get_color(),
                                    step="post")
                elif ct == "step":
                    line, = ax.step(x, y, where="post", linewidth=lw,
                                    linestyle=ls, label=feat)
                    if mk:
                        ax.plot(x, y, marker=mk, linewidth=0, markersize=4,
                                color=line.get_color())
                else:  # line
                    line, = ax.plot(x, y, marker=mk, linewidth=lw, markersize=4,
                                    linestyle=ls, label=feat,
                                    drawstyle="steps-post")
                feat_colors[feat] = line.get_color()

        # Policy overlay — same color as its feature, or default for zero-usage
        for feat in self.policy_map:
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

        # Add 0.1x padding based on period span
        start_num = mdates.date2num(datetime.combine(start_d, datetime.min.time()))
        end_num = mdates.date2num(datetime.combine(end_d, datetime.max.time()))
        period_span = end_num - start_num
        pad = period_span * 0.1  # 0.1x of total period

        # Set x-axis limits: full period with 0.1x padding on each side
        left_limit = start_num - pad
        right_limit = end_num + pad

        ax.set_xlim(left=left_limit, right=right_limit)

        # Axis formatting
        ax.set_ylabel("Concurrent Licenses", fontsize=fs + 1, fontweight="bold")
        ax.set_xlabel("Time", fontsize=fs + 1, fontweight="bold")
        ax.xaxis.set_major_formatter(DateFormatter(tick_fmt))
        ax.tick_params(axis="both", labelsize=fs)
        self.figure.autofmt_xdate(rotation=45)
        if opts["grid"]:
            ax.grid(True, alpha=0.3)
        else:
            ax.grid(False)
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
    def _snapshot_interval_minutes(self):
        """Return the lmstat collection interval in minutes.

        Uses median gap between consecutive snapshots in the current dataset,
        which is robust against ad-hoc collections (GUI 'Collect Now' etc.).
        Falls back to 5 minutes if insufficient data.
        """
        if getattr(self, '_cached_interval', None) is not None:
            return self._cached_interval
        if self.raw_data is None or self.raw_data.empty:
            return SNAPSHOT_INTERVAL_MIN or 5
        timestamps = pd.to_datetime(
            self.raw_data["ts"], format="%Y-%m-%d %H:%M:%S", errors="coerce"
        ).dropna()
        unique_ts = sorted(timestamps.unique())
        if len(unique_ts) < 2:
            return SNAPSHOT_INTERVAL_MIN or 5
        gaps = [(unique_ts[i] - unique_ts[i - 1]).total_seconds() / 60.0
                for i in range(1, len(unique_ts))]
        median_gap = sorted(gaps)[len(gaps) // 2]
        # Clamp to reasonable range (1–60 min) to avoid outlier issues
        self._cached_interval = max(1.0, min(60.0, round(median_gap, 1)))
        return self._cached_interval

    @staticmethod
    def _compute_sessions(ts_series, interval_min):
        """Detect sessions and compute total session duration.

        Returns (session_count, total_session_hours).
        A session = consecutive snapshots with gap <= 2.5x interval.
        Duration per session = (last_ts - first_ts) + interval.
        """
        ts_parsed = pd.to_datetime(ts_series, format="%Y-%m-%d %H:%M:%S", errors="coerce").dropna()
        unique_ts = sorted(ts_parsed.unique())
        if not unique_ts:
            return 0, 0.0
        if len(unique_ts) == 1:
            return 1, round(interval_min / 60.0, 2)

        gap_threshold = pd.Timedelta(minutes=interval_min * 2.5)
        interval_td = pd.Timedelta(minutes=interval_min)

        session_hours = []
        session_start = unique_ts[0]
        session_end = unique_ts[0]

        for i in range(1, len(unique_ts)):
            if (unique_ts[i] - unique_ts[i - 1]) > gap_threshold:
                # Close current session
                dur = (session_end - session_start) + interval_td
                session_hours.append(dur.total_seconds() / 3600.0)
                session_start = unique_ts[i]
            session_end = unique_ts[i]

        # Close last session
        dur = (session_end - session_start) + interval_td
        session_hours.append(dur.total_seconds() / 3600.0)

        return len(session_hours), round(sum(session_hours), 2)

    @staticmethod
    def _make_numeric_item(value):
        """Create a QTableWidgetItem that sorts numerically."""
        item = QTableWidgetItem()
        item.setData(Qt.DisplayRole, value)
        return item

    @staticmethod
    def _make_hours_item(value):
        """Create a QTableWidgetItem for hours that always shows 2 decimal places."""
        return NumericSortItem(f"{value:.2f}", float(value))

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

        # Merge features from data with features from policy_map
        data_features = set(df["feature"].unique()) if not df.empty else set()
        policy_features = set(self.policy_map.keys())
        all_features = sorted(data_features | policy_features)

        if not all_features:
            self.stats_table.setSortingEnabled(True)
            return

        if not df.empty:
            df = df.copy()
            df["datetime"] = pd.to_datetime(df["ts"], format="%Y-%m-%d %H:%M:%S", errors="coerce")

        interval_min = self._snapshot_interval_minutes()
        period_hours = self._get_period_hours()

        for row_idx, feat in enumerate(all_features):
            if not df.empty and feat in data_features:
                fdf = df[df["feature"] == feat]
                total_checkouts = len(fdf)
                unique_users = fdf["user"].nunique()
                active_days = fdf["datetime"].dt.date.nunique()

                concurrent_per_snap = fdf.groupby("ts").size()
                peak_concurrent = int(concurrent_per_snap.max()) if not concurrent_per_snap.empty else 0

                est_usage_hours = 0.0
                for usr in fdf["user"].unique():
                    _, usr_hrs = self._compute_sessions(fdf[fdf["user"] == usr]["ts"], interval_min)
                    est_usage_hours += usr_hrs
                est_usage_hours = round(est_usage_hours, 2)

                # Avg concurrent when feature is actively checked out (used for display and Active Util. %)
                avg_concurrent = float(round(concurrent_per_snap.mean(), 2)) if not concurrent_per_snap.empty else 0

                valid_dt = fdf["datetime"].dropna()
                first_seen = str(valid_dt.min()) if not valid_dt.empty else "-"
                last_seen = str(valid_dt.max()) if not valid_dt.empty else "-"
            else:
                # Feature from policy with zero usage
                total_checkouts = 0
                unique_users = 0
                active_days = 0
                avg_concurrent = 0
                peak_concurrent = 0
                est_usage_hours = 0.0
                first_seen = "-"
                last_seen = "-"

            policy_max = self.policy_map.get(feat, None)

            self.stats_table.insertRow(row_idx)
            self.stats_table.setItem(row_idx, 0, QTableWidgetItem(feat))
            self.stats_table.setItem(row_idx, 1, self._make_numeric_item(total_checkouts))
            self.stats_table.setItem(row_idx, 2, self._make_numeric_item(unique_users))
            self.stats_table.setItem(row_idx, 3, self._make_numeric_item(active_days))
            self.stats_table.setItem(row_idx, 4, self._make_numeric_item(avg_concurrent))
            self.stats_table.setItem(row_idx, 5, self._make_numeric_item(peak_concurrent))
            self.stats_table.setItem(row_idx, 6, self._make_hours_item(est_usage_hours))
            self.stats_table.setItem(row_idx, 7, QTableWidgetItem(first_seen))
            self.stats_table.setItem(row_idx, 8, QTableWidgetItem(last_seen))

            if policy_max is not None:
                self.stats_table.setItem(row_idx, 9, self._make_numeric_item(policy_max))

                # Active Util. % = avg concurrent when in use / policy_max
                if policy_max > 0:
                    active_util = avg_concurrent / policy_max * 100
                else:
                    active_util = 0
                au_item = QTableWidgetItem(f"{active_util:.1f}%")
                if active_util >= 80:
                    au_item.setBackground(QColor(144, 238, 144))  # green
                elif active_util >= 30:
                    au_item.setBackground(QColor(255, 255, 153))  # yellow
                else:
                    au_item.setBackground(QColor(255, 182, 182))  # red
                self.stats_table.setItem(row_idx, 10, au_item)

                # Period Util. % = usage_hours / (policy_max × period_hours) × 100
                if policy_max > 0 and period_hours > 0:
                    period_util = est_usage_hours / (policy_max * period_hours) * 100
                else:
                    period_util = 0
                pu_item = QTableWidgetItem(f"{period_util:.1f}%")
                if period_util >= 60:
                    pu_item.setBackground(QColor(144, 238, 144))  # green
                elif period_util >= 20:
                    pu_item.setBackground(QColor(255, 255, 153))  # yellow
                else:
                    pu_item.setBackground(QColor(255, 182, 182))  # red
                self.stats_table.setItem(row_idx, 11, pu_item)
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
    def _get_period_days(self):
        """Return number of days in the selected period (inclusive)."""
        start_qd = self.start_date_edit.date()
        end_qd = self.end_date_edit.date()
        return max(start_qd.daysTo(end_qd) + 1, 1)

    def _update_user_activity(self, df):
        self.user_activity_table.setSortingEnabled(False)
        self.user_activity_table.setRowCount(0)

        if df.empty:
            self.user_activity_table.setSortingEnabled(True)
            return

        df = df.copy()
        df["datetime"] = pd.to_datetime(df["ts"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
        interval_min = self._snapshot_interval_minutes()
        period_days = self._get_period_days()

        users = sorted(df["user"].unique())
        for row_idx, user in enumerate(users):
            udf = df[df["user"] == user]
            company = udf["company"].iloc[0]
            features_used = udf["feature"].nunique()
            total_checkouts = len(udf)
            valid_dt = udf["datetime"].dropna()
            active_days = valid_dt.dt.date.nunique() if not valid_dt.empty else 0
            first_active = str(valid_dt.min()) if not valid_dt.empty else "-"
            last_active = str(valid_dt.max()) if not valid_dt.empty else "-"

            # Session-based usage: sum per-feature session durations
            est_usage_hours = 0.0
            total_sessions = 0
            for feat in udf["feature"].unique():
                uf_feat = udf[udf["feature"] == feat]
                s_count, s_hours = self._compute_sessions(uf_feat["ts"], interval_min)
                est_usage_hours += s_hours
                total_sessions += s_count
            est_usage_hours = round(est_usage_hours, 2)

            avg_hours_day = round(est_usage_hours / period_days, 2)
            avg_hours_day_copy = round(avg_hours_day / features_used, 2) if features_used > 0 else 0.0
            avg_session_hrs = round(est_usage_hours / total_sessions, 2) if total_sessions > 0 else 0.0

            self.user_activity_table.insertRow(row_idx)
            self.user_activity_table.setItem(row_idx, 0, QTableWidgetItem(user))
            self.user_activity_table.setItem(row_idx, 1, QTableWidgetItem(company))
            self.user_activity_table.setItem(row_idx, 2, self._make_numeric_item(features_used))
            self.user_activity_table.setItem(row_idx, 3, self._make_numeric_item(total_checkouts))
            self.user_activity_table.setItem(row_idx, 4, self._make_hours_item(est_usage_hours))
            self.user_activity_table.setItem(row_idx, 5, self._make_numeric_item(active_days))
            self.user_activity_table.setItem(row_idx, 6, QTableWidgetItem(first_active))
            self.user_activity_table.setItem(row_idx, 7, QTableWidgetItem(last_active))
            self.user_activity_table.setItem(row_idx, 8, self._make_hours_item(avg_hours_day))
            self.user_activity_table.setItem(row_idx, 9, self._make_hours_item(avg_hours_day_copy))
            self.user_activity_table.setItem(row_idx, 10, self._make_numeric_item(total_sessions))
            self.user_activity_table.setItem(row_idx, 11, self._make_hours_item(avg_session_hrs))

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

        # Build default filename
        now = datetime.now()
        ts_prefix = now.strftime("%Y%m%d_%H%M%S")
        start_qd = self.start_date_edit.date()
        end_qd = self.end_date_edit.date()
        start_str = start_qd.toString("yyyyMMdd")
        end_str = end_qd.toString("yyyyMMdd")
        default_name = f"{ts_prefix}_{start_str}_{end_str}.csv"

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Filtered Data", default_name,
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
        """Classify period type and compute ordinal from date range.

        Uses the quick period selector when active for accurate naming
        (e.g. weekly-03, monthly-08, yearly).  Falls back to
        date range format when the quick selector is not used.
        """
        granularity = self.quick_granularity.currentText()
        period_text = self.quick_period_combo.currentText()

        # If a quick-period is actively selected, derive from it directly
        if granularity != "(None)" and period_text and not period_text.startswith("-- "):
            if granularity == "Weekly":
                week = int(period_text.split("-")[1])
                return "weekly", f"weekly-{week:02d}"
            elif granularity == "Monthly":
                month = int(period_text.split("-")[1])
                return "monthly", f"monthly-{month:02d}"
            elif granularity == "Quarterly":
                q = int(period_text.split("-")[1])
                return "quarterly", f"quarterly-Q{q}"
            elif granularity == "Yearly":
                return "yearly", "yearly"

        # No quick-period active: use date range as-is
        return "custom", f"{start_date}_{end_date}"

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
                    line, = ax.plot(x, y, linewidth=1.5, label=feat,
                                    drawstyle="steps-post")
                    ax.fill_between(x, y, alpha=0.15, color=line.get_color(),
                                    step="post")
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

                # Clip x-axis to not extend beyond "Now" (prevents chart area past current time)
                now_dt = datetime.now()
                xlim = ax.get_xlim()
                now_num = mdates.date2num(now_dt)
                margin = (xlim[1] - xlim[0]) * 0.015  # 1.5% margin past Now for breathing room
                # Only clip right edge to Now + small margin, don't touch left
                if xlim[1] > now_num + margin:
                    ax.set_xlim(right=now_num + margin)

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
        interval_min = self._snapshot_interval_minutes()
        ph = period_hours if period_hours else 1.0
        rows = []
        for feat in sorted(df["feature"].unique()):
            fdf = df[df["feature"] == feat]
            total_checkouts = len(fdf)
            unique_users = fdf["user"].nunique()
            active_days = fdf["datetime"].dt.date.nunique()
            concurrent_per_snap = fdf.groupby("ts").size()
            peak_conc = int(concurrent_per_snap.max()) if not concurrent_per_snap.empty else 0
            # Usage Hours: sum of per-user session durations for this feature
            est_usage_hours = 0.0
            for usr in fdf["user"].unique():
                _, usr_hrs = self._compute_sessions(fdf[fdf["user"] == usr]["ts"], interval_min)
                est_usage_hours += usr_hrs
            est_usage_hours = round(est_usage_hours, 1)
            # Time-weighted avg concurrent over entire period
            avg_conc = round(est_usage_hours / ph, 2) if ph > 0 else 0
            # Avg concurrent when feature is actively checked out
            avg_conc_active = round(float(concurrent_per_snap.mean()), 2) if not concurrent_per_snap.empty else 0
            valid_dt = fdf["datetime"].dropna()
            first_seen = str(valid_dt.min()) if not valid_dt.empty else "-"
            last_seen = str(valid_dt.max()) if not valid_dt.empty else "-"
            policy_max = pmap.get(feat)
            active_util = None
            period_util = None
            if policy_max and policy_max > 0:
                active_util = round(avg_conc_active / policy_max * 100, 1)
                period_util = round(est_usage_hours / (policy_max * ph) * 100, 1)
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
                "active_utilization": active_util,
                "period_utilization": period_util,
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
        interval_min = self._snapshot_interval_minutes()
        rows = []
        for comp in sorted(df["company"].unique()):
            cdf = df[df["company"] == comp]
            total_checkouts = len(cdf)
            concurrent_per_snap = cdf.groupby("ts").size()
            # Session-based usage: sum per (user, feature) session durations
            est_usage_hours = 0.0
            for usr in cdf["user"].unique():
                udf = cdf[cdf["user"] == usr]
                for feat in udf["feature"].unique():
                    _, s_hrs = self._compute_sessions(udf[udf["feature"] == feat]["ts"], interval_min)
                    est_usage_hours += s_hrs
            est_usage_hours = round(est_usage_hours, 1)
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
        interval_min = self._snapshot_interval_minutes()
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
            est_hours = 0.0
            for feat in udf["feature"].unique():
                _, s_hrs = self._compute_sessions(udf[udf["feature"] == feat]["ts"], interval_min)
                est_hours += s_hrs
            est_hours = round(est_hours, 1)
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
        interval_min = self._snapshot_interval_minutes()
        period_days = self._get_period_days()
        results = []
        for user in sorted(df["user"].unique()):
            udf = df[df["user"] == user]
            company = udf["company"].iloc[0]
            features_used = udf["feature"].nunique()
            total_checkouts = len(udf)
            valid_dt = udf["datetime"].dropna()
            active_days = valid_dt.dt.date.nunique() if not valid_dt.empty else 0
            first_active = str(valid_dt.min()) if not valid_dt.empty else "-"
            last_active = str(valid_dt.max()) if not valid_dt.empty else "-"

            # Session-based usage: sum per-feature session durations
            est_hours = 0.0
            total_sessions = 0
            for feat in udf["feature"].unique():
                uf_feat = udf[udf["feature"] == feat]
                s_count, s_hours = self._compute_sessions(uf_feat["ts"], interval_min)
                est_hours += s_hours
                total_sessions += s_count
            est_hours = round(est_hours, 1)

            avg_hours_day = round(est_hours / period_days, 1)
            avg_hours_day_copy = round(avg_hours_day / features_used, 1) if features_used > 0 else 0.0
            avg_session_hrs = round(est_hours / total_sessions, 2) if total_sessions > 0 else 0.0
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
                "avg_hours_day_copy": avg_hours_day_copy,
                "sessions": total_sessions,
                "avg_session_hrs": avg_session_hrs,
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
<th>Active Days</th><th>Avg When Active</th><th>Peak Concurrent</th>
<th>Usage Hours</th><th>First Seen</th><th>Last Seen</th>
<th>Policy Max</th><th>Active Util. %</th><th>Period Util. %</th></tr>""")
            for s in stat_rows:
                pm = str(s["policy_max"]) if s["policy_max"] is not None else "-"
                euh = s.get("est_usage_hours", 0.0)
                fs = s.get("first_seen", "-")
                ls = s.get("last_seen", "-")
                au = s.get("active_utilization")
                if au is not None:
                    auc = util_color(au)
                    au_cell = (f'<td><span class="util-cell" style="background:{auc};">'
                               f'{au:.1f}%</span></td>')
                else:
                    au_cell = '<td><span class="util-cell" style="background:#dcdcdc;">N/A</span></td>'
                pu = s.get("period_utilization")
                if pu is not None:
                    puc = util_color(pu * 4 / 3)  # scale: 60%→green, 20%→yellow
                    pu_cell = (f'<td><span class="util-cell" style="background:{puc};">'
                               f'{pu:.1f}%</span></td>')
                else:
                    pu_cell = '<td><span class="util-cell" style="background:#dcdcdc;">N/A</span></td>'
                parts.append(
                    f'<tr><td>{s["feature"]}</td><td>{s["total_checkouts"]:,}</td>'
                    f'<td>{s["unique_users"]}</td><td>{s["active_days"]}</td>'
                    f'<td>{s["avg_concurrent"]}</td><td>{s["peak_concurrent"]}</td>'
                    f'<td>{euh}</td><td>{fs}</td><td>{ls}</td>'
                    f'<td>{pm}</td>{au_cell}{pu_cell}</tr>'
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
<th>Total Checkouts</th><th>Usage Hours</th><th>Active Days</th>
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
              border-bottom: 3px solid #1a3a5c;
              position: sticky; top: 0; z-index: 100;
              background: #fff; padding-top: 8px; }}
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
<th>Unique Users</th><th>Peak Concurrent</th><th>Usage Hours</th></tr>""")
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
<th>Usage Hours</th><th>Active Days</th><th>First Active</th>
<th>Last Active</th><th>Avg Hrs/Day</th><th>Avg Hrs/Day/Copy</th>
<th>Sessions</th><th>Avg Session Hrs</th></tr>""")
            for ua in user_activity:
                h.append(
                    f'<tr><td>{ua["user"]}</td><td>{ua["company"]}</td>'
                    f'<td>{ua["features_used"]}</td><td>{ua["total_checkouts"]:,}</td>'
                    f'<td>{ua["est_usage_hours"]}</td><td>{ua["active_days"]}</td>'
                    f'<td>{ua["first_active"]}</td><td>{ua["last_active"]}</td>'
                    f'<td>{ua["avg_hours_day"]}</td>'
                    f'<td>{ua.get("avg_hours_day_copy", 0.0)}</td>'
                    f'<td>{ua.get("sessions", 0)}</td>'
                    f'<td>{ua.get("avg_session_hrs", 0.0)}</td></tr>'
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

        # Start animation and show progress bar immediately
        self._start_export_html_anim()
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_bar.showMessage("Generating HTML report...")
        QApplication.processEvents()

        start_qd = self.start_date_edit.date()
        end_qd = self.end_date_edit.date()
        start_d = date(start_qd.year(), start_qd.month(), start_qd.day())
        end_d = date(end_qd.year(), end_qd.month(), end_qd.day())

        period_type, ordinal = self._determine_period_info(start_d, end_d)

        # Build filename
        now = datetime.now()
        ts_prefix = now.strftime("%Y%m%d_%H%M%S")
        filename = f"{ts_prefix}_{ordinal}.html"

        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        export_path = EXPORT_DIR / filename

        try:
            df = self.filtered_data
            num_companies = df["company"].nunique()

            # Calculate total steps: 8 overall steps + 4 steps per company + 1 final write
            total_steps = 8 + (num_companies * 4) + 1
            current_step = 0

            def update_progress(step_name):
                nonlocal current_step
                current_step += 1
                pct = int((current_step / total_steps) * 100)
                self.progress_bar.setValue(pct)
                self.status_bar.showMessage(f"Generating report... {step_name}")
                QApplication.processEvents()

            # --- Overall data (policy scoped to filtered users) ---
            period_hours = self._get_period_hours()
            all_users = set(df["user"].unique())
            overall_policy = self._policy_map_for_users(all_users)

            update_progress("rendering overall chart")
            chart_b64 = self._render_chart_to_base64(df, start_d, end_d, overall_policy)

            update_progress("building statistics")
            stats = self._build_stats_rows(df, overall_policy, period_hours)

            update_progress("analyzing overuse")
            overuse = self._build_overuse_analysis(df, overall_policy)

            update_progress("building company breakdown")
            company_bd = self._build_company_breakdown(df)

            update_progress("building feature matrix")
            feat_comp = self._build_feature_company_matrix(df)

            update_progress("finding top users")
            top_users = self._build_top_users(df)

            update_progress("building user activity")
            user_activity = self._build_user_activity(df)

            update_progress("preparing metadata")
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
            for idx, comp in enumerate(sorted(df["company"].unique()), 1):
                cdf = df[df["company"] == comp]
                comp_users = set(cdf["user"].unique())
                comp_policy = self._policy_map_for_users(comp_users)

                update_progress(f"[{idx}/{num_companies}] {comp} chart")
                comp_chart = self._render_chart_to_base64(cdf, start_d, end_d, comp_policy)

                update_progress(f"[{idx}/{num_companies}] {comp} stats")
                comp_stats = self._build_stats_rows(cdf, comp_policy, period_hours)

                update_progress(f"[{idx}/{num_companies}] {comp} overuse")
                comp_overuse = self._build_overuse_analysis(cdf, comp_policy)

                update_progress(f"[{idx}/{num_companies}] {comp} top users")
                comp_top = self._build_top_users(cdf)

                company_tabs[comp] = {
                    "chart_b64": comp_chart,
                    "stats": comp_stats,
                    "overuse": comp_overuse,
                    "top_users": comp_top,
                    "total_records": len(cdf),
                    "unique_features": cdf["feature"].nunique(),
                    "unique_users": cdf["user"].nunique(),
                }

            update_progress("generating HTML")
            html = self._generate_html(chart_b64, stats, company_bd,
                                       feat_comp, top_users, overuse,
                                       user_activity, company_tabs, meta)

            with open(export_path, "w", encoding="utf-8") as f:
                f.write(html)

            # Track last export and enable View button
            self.last_exported_html = str(export_path)
            self.view_html_btn.setEnabled(True)

            self.progress_bar.setValue(100)
            self.progress_bar.setVisible(False)
            self._stop_export_html_anim(success=True)
            self.status_bar.showMessage(f"HTML report exported: {export_path}")
            QMessageBox.information(
                self, "Export Complete",
                f"HTML audit report saved to:\n{export_path}\n\nClick 'View HTML' to open it in your browser."
            )
        except Exception as e:
            self.progress_bar.setVisible(False)
            self._stop_export_html_anim(success=False)
            self.status_bar.showMessage(f"Export error: {e}")
            QMessageBox.critical(self, "Export Error", str(e))

    def _view_html(self):
        """Open an exported HTML report in the default web browser with file selection."""
        # Get all HTML files in exports directory
        if not EXPORT_DIR.exists():
            QMessageBox.warning(
                self, "No Exports",
                f"Exports directory does not exist:\n{EXPORT_DIR}\n\nClick 'Export HTML' first."
            )
            self.view_html_btn.setEnabled(False)
            return

        html_files = sorted(EXPORT_DIR.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)

        if not html_files:
            QMessageBox.warning(
                self, "No Exports",
                f"No HTML reports found in:\n{EXPORT_DIR}\n\nClick 'Export HTML' first."
            )
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
            # Use webbrowser module to open in default browser
            import webbrowser
            file_url = selected_file.as_uri()
            webbrowser.open(file_url)
            self.last_exported_html = str(selected_file)
            self.status_bar.showMessage(f"Opened in browser: {selected_file.name}")
        except Exception as e:
            QMessageBox.critical(
                self, "Open Error",
                f"Failed to open HTML file:\n{e}\n\n"
                f"You can manually open:\n{selected_file}"
            )

    def _select_html_file(self, html_files):
        """Show a dialog to select which HTML file to open.

        Args:
            html_files: List of Path objects for HTML files

        Returns:
            Path object of selected file, or None if cancelled
        """
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QListWidget, QPushButton, QHBoxLayout, QLabel

        dialog = QDialog(self)
        dialog.setWindowTitle("Select HTML Report to Open")
        dialog.setModal(True)
        dialog.resize(600, 400)

        layout = QVBoxLayout()

        # Info label
        info_label = QLabel(f"Found {len(html_files)} HTML report(s). Select one to open:")
        layout.addWidget(info_label)

        # File list
        file_list = QListWidget()
        for html_file in html_files:
            # Format: filename (modified: 2026-02-12 15:30:45)
            mtime = datetime.fromtimestamp(html_file.stat().st_mtime)
            display_text = f"{html_file.name}  (modified: {mtime.strftime('%Y-%m-%d %H:%M:%S')})"
            item = QListWidgetItem(display_text)
            item.setData(Qt.UserRole, html_file)  # Store Path object
            file_list.addItem(item)

        # Select first item by default (most recent)
        file_list.setCurrentRow(0)
        file_list.itemDoubleClicked.connect(dialog.accept)  # Double-click to open
        layout.addWidget(file_list)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        open_btn = QPushButton("Open")
        open_btn.setDefault(True)
        open_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(open_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)
        dialog.setLayout(layout)

        # Show dialog and get result
        if dialog.exec_() == QDialog.Accepted:
            selected_item = file_list.currentItem()
            if selected_item:
                return selected_item.data(Qt.UserRole)

        return None


# ============================================================
# License Key Generator (for vendor use)
# ============================================================

def generate_license_key(expiry_date_str, machine_short, secret=_LICENSE_SECRET):
    """Generate a license key for a given expiry and machine.

    Args:
        expiry_date_str: Expiry date as 'YYYY-MM-DD' or 'YYYYMMDD'
        machine_short: 8-character machine identifier (first 8 chars of machine SHA256)
        secret: HMAC secret key (defaults to embedded secret)

    Returns:
        License key string in format: LMON-YYYYMMDD-MACHINESIG-VERIFYSIG

    Example:
        key = generate_license_key('2026-12-31', 'A1B2C3D4')
        # Returns: 'LMON-20261231-A1B2C3D4-E5F67890'

    Usage (vendor generates keys offline):
        from gui_license_monitor import generate_license_key
        key = generate_license_key('2027-03-31', 'A1B2C3D4')
        print(f"Key: {key}")
    """
    # Parse expiry date
    if "-" in expiry_date_str:
        expiry_str = expiry_date_str.replace("-", "")[:8].upper()
    else:
        expiry_str = expiry_date_str[:8].upper()

    # Ensure machine_short is 8 uppercase hex chars
    ms = machine_short.upper()[:8]

    # Generate HMAC signature
    sig_data = f"{expiry_str}:{ms}".encode()
    sig = _hmac.new(secret, sig_data, hashlib.sha256).hexdigest()[:8].upper()

    return f"LMON-{expiry_str}-{ms}-{sig}"


# ============================================================
# Entry point
# ============================================================

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # License check: trial period or key validation
    lm = LicenseManager()
    status, msg = lm.check()
    if status in ("expired",):
        # Must enter key to continue (no skip option)
        dlg = LicenseDialog(None, lm, allow_skip=False)
        if dlg.exec_() != QDialog.Accepted:
            sys.exit(0)
    elif status in ("trial", "trial_expiring"):
        # Show reminder, can skip for now
        dlg = LicenseDialog(None, lm, allow_skip=True)
        dlg.exec_()  # user can continue trial by closing dialog
    # status == 'ok': fully activated, no dialog needed

    gui = LicenseMonitorGUI()
    gui.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
