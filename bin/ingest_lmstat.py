#!/usr/local/python-3.12.2/bin/python3.12
#
# ingest_lmstat.py  (FINAL – correct block handling for snpslmd)
#

import os
import re
import glob
import sqlite3

RAW_DIR = os.environ["RAW_LMSTAT_DIR"]
DB_PATH = os.path.join(os.environ["DB_DIR"], "license_monitor.db")

# external partner user naming: company-xxxx
USER_RE = re.compile(r"^[a-z0-9]+-[a-z]{4}$")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Load policy users for filtering (fall back to USER_RE if empty)
policy_users = set()
try:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='license_policy'")
    if cur.fetchone():
        cur.execute("SELECT DISTINCT user FROM license_policy")
        policy_users = {r[0] for r in cur.fetchall()}
except Exception:
    pass

files = sorted(glob.glob(os.path.join(RAW_DIR, "lmstat_*.txt")))
if not files:
    conn.close()
    exit(0)

path = files[-1]
ts = path.split("lmstat_", 1)[1].replace(".txt", "").replace("_", " ")

current_feature = None

with open(path) as f:
    for raw in f:
        line = raw.rstrip()

        # Feature header
        if line.startswith("Users of "):
            current_feature = line.split("Users of", 1)[1].split(":")[0].strip()
            continue

        # Skip until a feature is active
        if not current_feature:
            continue

        # Skip metadata / quoted lines
        if not line.strip() or line.lstrip().startswith('"'):
            continue

        # Real checkout line
        if " start " in line:
            parts = line.split()
            if len(parts) < 2:
                continue

            user = parts[0]
            host = parts[1]

            # enforce external user policy
            if policy_users:
                if user not in policy_users:
                    continue
            elif not USER_RE.match(user):
                continue

            cur.execute(
                """
                INSERT INTO lmstat_snapshot
                  (ts, user, host, feature, count, source_file)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (ts, user, host, current_feature, 1, os.path.basename(path))
            )

conn.commit()
conn.close()
