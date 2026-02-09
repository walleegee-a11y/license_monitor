#!/usr/local/python-3.12.2/bin/python3.12
"""Bulk ingest all lmstat files into database"""

import os
import re
import glob
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).parent
RAW_DIR = BASE_DIR / "raw" / "lmstat"
DB_PATH = BASE_DIR / "db" / "license_monitor.db"

# Create db directory if it doesn't exist
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

conn = sqlite3.connect(str(DB_PATH))
cur = conn.cursor()

# Ensure table exists with correct schema
cur.execute("""
    CREATE TABLE IF NOT EXISTS lmstat_snapshot (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        user TEXT,
        host TEXT,
        feature TEXT NOT NULL,
        count INTEGER NOT NULL,
        source_file TEXT NOT NULL
    )
""")

# Clear existing data for clean re-ingest
cur.execute("DELETE FROM lmstat_snapshot")
print("Cleared existing lmstat_snapshot data")

# Track already-ingested source files to avoid duplicates
ingested_sources = set()

files = sorted(glob.glob(str(RAW_DIR / "lmstat_*.txt")))
print(f"Found {len(files)} files to process")

ingested_count = 0

for file_idx, path in enumerate(files):
    filename = Path(path).name

    # Avoid duplicate source files
    if filename in ingested_sources:
        continue
    ingested_sources.add(filename)

    # Extract timestamp: lmstat_2026-01-28_10-04-22.txt → 2026-01-28 10:04:22
    ts_str = filename.replace("lmstat_", "").replace(".txt", "")
    ts_str = ts_str.replace("_", " ", 1)
    parts = ts_str.split(" ")
    if len(parts) == 2:
        date_part = parts[0]
        time_part = parts[1].replace("-", ":")
        ts_str = f"{date_part} {time_part}"

    current_feature = None
    records_in_file = 0

    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.rstrip()

                # Feature header: "Users of FeatureName:  (Total of X licenses..."
                if line.startswith("Users of ") and "licenses issued" in line:
                    match = re.match(r"Users of ([^:]+):", line)
                    if match:
                        current_feature = match.group(1).strip()
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

                    cur.execute(
                        """
                        INSERT INTO lmstat_snapshot
                          (ts, user, host, feature, count, source_file)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (ts_str, user, host, current_feature, 1, filename),
                    )
                    records_in_file += 1

        if records_in_file > 0:
            ingested_count += records_in_file
            print(f"[{file_idx+1}/{len(files)}] {filename}: {records_in_file} records")

    except Exception as e:
        print(f"ERROR processing {filename}: {e}")

conn.commit()
conn.close()

print(f"\nTotal records ingested: {ingested_count}")
