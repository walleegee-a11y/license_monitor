#!/usr/local/python-3.12.2/bin/python3.12
import sqlite3
import sys
import os

BASE = os.environ.get("LICENSE_MONITOR_HOME", "/home/appl/license_monitor")
DB   = f"{BASE}/db/license_monitor.db"
OPTIONS = os.environ.get("OPTIONS_FILE")

if not OPTIONS:
    if len(sys.argv) > 1:
        OPTIONS = sys.argv[1]
    else:
        print("Usage: OPTIONS_FILE=/path/to/options.opt ingest_policy.py")
        print("   or: ingest_policy.py /path/to/options.opt")
        sys.exit(1)

grp = {}       # {group_name: [user1, user2, ...]}
grp_co = {}    # {group_name: company}

con = sqlite3.connect(DB)
cur = con.cursor()

# Ensure table exists
cur.execute("""
    CREATE TABLE IF NOT EXISTS license_policy (
        user       TEXT NOT NULL,
        company    TEXT,
        feature    TEXT NOT NULL,
        policy_max INTEGER,
        source_file TEXT,
        PRIMARY KEY (user, feature)
    )
""")

# Clear existing policy from this source file before re-ingesting
cur.execute("DELETE FROM license_policy WHERE source_file = ?", (OPTIONS,))

with open(OPTIONS, encoding="utf-8", errors="replace") as f:
    for line in f:
        line = line.strip()

        # Skip comments and blank lines
        if not line or line.startswith("#"):
            continue

        if line.startswith("GROUP"):
            parts = line.split()
            group_name = parts[1]
            users = parts[2:]
            grp[group_name] = users
            grp_co[group_name] = group_name.split("_", 1)[0]

        elif line.startswith("MAX"):
            parts = line.split()
            # MAX <count> <feature> USER <username>
            # MAX <count> <feature> GROUP <groupname>
            maxv    = int(parts[1])
            feature = parts[2]
            kind    = parts[3]   # USER or GROUP
            target  = parts[4]

            if kind == "GROUP":
                users = grp.get(target)
                if not users:
                    continue
                company = grp_co.get(target, target.split("_", 1)[0])
                for user in users:
                    cur.execute(
                        "INSERT OR REPLACE INTO license_policy VALUES (?,?,?,?,?)",
                        (user, company, feature, maxv, OPTIONS)
                    )
            elif kind == "USER":
                user = target
                company = user.split("-")[0]
                cur.execute(
                    "INSERT OR REPLACE INTO license_policy VALUES (?,?,?,?,?)",
                    (user, company, feature, maxv, OPTIONS)
                )
            else:
                continue

        # Skip EXCLUDE/INCLUDE lines — they are FlexLM directives, not DB entries

con.commit()
con.close()
print(f"Policy ingested from: {OPTIONS}")
