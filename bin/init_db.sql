PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS lmstat_snapshot (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  user TEXT,
  host TEXT,
  feature TEXT NOT NULL,
  count INTEGER NOT NULL,
  source_file TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snap_ts
  ON lmstat_snapshot(ts);

CREATE INDEX IF NOT EXISTS idx_snap_user_feat
  ON lmstat_snapshot(user, feature);
