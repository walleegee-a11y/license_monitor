#!/usr/bin/env python3
"""Check database records for diagnostics"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "db" / "license_monitor.db"

conn = sqlite3.connect(str(DB_PATH))
cur = conn.cursor()

# Check total records for sally-cute on 2026-01-28
cur.execute("""
    SELECT COUNT(*) as total, MIN(ts) as first_ts, MAX(ts) as last_ts 
    FROM lmstat_snapshot 
    WHERE feature='sally-cute' AND substr(ts,1,10)='2026-01-28'
""")
result = cur.fetchone()
print(f"Total records: {result[0]}")
print(f"First timestamp: {result[1]}")
print(f"Last timestamp: {result[2]}")

# Show sample records
print("\n=== Sample records (first 10) ===")
cur.execute("""
    SELECT ts, feature, user 
    FROM lmstat_snapshot 
    WHERE feature='sally-cute' AND substr(ts,1,10)='2026-01-28'
    ORDER BY ts
    LIMIT 10
""")
for row in cur.fetchall():
    print(row)

print("\n=== Sample records (last 10) ===")
cur.execute("""
    SELECT ts, feature, user 
    FROM lmstat_snapshot 
    WHERE feature='sally-cute' AND substr(ts,1,10)='2026-01-28'
    ORDER BY ts DESC
    LIMIT 10
""")
for row in cur.fetchall():
    print(row)

conn.close()
