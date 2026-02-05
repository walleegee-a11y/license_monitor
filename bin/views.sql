PRAGMA foreign_keys = ON;

-- ============================================================
-- 0. Base snapshot normalization
-- ============================================================

DROP VIEW IF EXISTS v_usage_ts_norm;

CREATE VIEW v_usage_ts_norm AS
SELECT
  id,
  datetime(
    substr(ts,1,4) || '-' ||
    substr(ts,6,2) || '-' ||
    substr(ts,9,2) || ' ' ||
    substr(ts,12,2) || ':' ||
    substr(ts,15,2) || ':' ||
    substr(ts,18,2)
  ) AS ts_norm,
  user,
  host,
  feature,
  count
FROM lmstat_snapshot;


-- ============================================================
-- 1. Base aggregation (period-independent)
-- ============================================================

DROP VIEW IF EXISTS v_usage_base;

CREATE VIEW v_usage_base AS
SELECT
  u.user,
  COALESCE(
    p.company,
    CASE WHEN instr(u.user, '-') > 0
         THEN substr(u.user, 1, instr(u.user, '-') - 1)
         ELSE u.user
    END
  ) AS company,
  u.feature,
  u.ts_norm
FROM v_usage_ts_norm u
LEFT JOIN (SELECT DISTINCT user, company FROM license_policy) p
  ON u.user = p.user;


-- ============================================================
-- 1b. Concurrent count at each snapshot per company/feature
-- ============================================================

DROP VIEW IF EXISTS v_concurrent_snapshot;

CREATE VIEW v_concurrent_snapshot AS
SELECT ts_norm, company, feature,
       COUNT(*) AS concurrent_count
FROM v_usage_base
GROUP BY ts_norm, company, feature;


-- ============================================================
-- 2. WEEKLY usage
-- ============================================================

DROP VIEW IF EXISTS v_usage_weekly;

CREATE VIEW v_usage_weekly AS
SELECT
  strftime('%Y-W%W', ts_norm) AS period,
  company,
  feature,
  COUNT(*)                      AS usage_count,
  COUNT(DISTINCT user)          AS active_users,
  COUNT(DISTINCT ts_norm)       AS active_snapshots,
  COUNT(*) * 5                  AS usage_minutes,
  ROUND(COUNT(*) * 5 / 60.0, 2) AS usage_hours,
  ROUND(
    100.0 * COUNT(*) /
    SUM(COUNT(*)) OVER (PARTITION BY strftime('%Y-W%W', ts_norm), feature),
    1
  ) AS usage_ratio_percent
FROM v_usage_base
GROUP BY period, company, feature;


-- ============================================================
-- 3. MONTHLY usage
-- ============================================================

DROP VIEW IF EXISTS v_usage_monthly;

CREATE VIEW v_usage_monthly AS
SELECT
  strftime('%Y-%m', ts_norm) AS period,
  company,
  feature,
  COUNT(*)                      AS usage_count,
  COUNT(DISTINCT user)          AS active_users,
  COUNT(DISTINCT ts_norm)       AS active_snapshots,
  COUNT(*) * 5                  AS usage_minutes,
  ROUND(COUNT(*) * 5 / 60.0, 2) AS usage_hours,
  ROUND(
    100.0 * COUNT(*) /
    SUM(COUNT(*)) OVER (PARTITION BY strftime('%Y-%m', ts_norm), feature),
    1
  ) AS usage_ratio_percent
FROM v_usage_base
GROUP BY period, company, feature;


-- ============================================================
-- 4. QUARTERLY usage
-- ============================================================

DROP VIEW IF EXISTS v_usage_quarterly;

CREATE VIEW v_usage_quarterly AS
SELECT
  strftime('%Y', ts_norm) || '-Q' ||
  ((cast(strftime('%m', ts_norm) as integer)-1)/3 + 1) AS period,
  company,
  feature,
  COUNT(*)                      AS usage_count,
  COUNT(DISTINCT user)          AS active_users,
  COUNT(DISTINCT ts_norm)       AS active_snapshots,
  COUNT(*) * 5                  AS usage_minutes,
  ROUND(COUNT(*) * 5 / 60.0, 2) AS usage_hours,
  ROUND(
    100.0 * COUNT(*) /
    SUM(COUNT(*)) OVER (
      PARTITION BY
        strftime('%Y', ts_norm),
        ((cast(strftime('%m', ts_norm) as integer)-1)/3 + 1),
        feature
    ),
    1
  ) AS usage_ratio_percent
FROM v_usage_base
GROUP BY period, company, feature;


-- ============================================================
-- 5. YEARLY usage
-- ============================================================

DROP VIEW IF EXISTS v_usage_yearly;

CREATE VIEW v_usage_yearly AS
SELECT
  strftime('%Y', ts_norm) AS period,
  company,
  feature,
  COUNT(*)                      AS usage_count,
  COUNT(DISTINCT user)          AS active_users,
  COUNT(DISTINCT ts_norm)       AS active_snapshots,
  COUNT(*) * 5                  AS usage_minutes,
  ROUND(COUNT(*) * 5 / 60.0, 2) AS usage_hours,
  ROUND(
    100.0 * COUNT(*) /
    SUM(COUNT(*)) OVER (PARTITION BY strftime('%Y', ts_norm), feature),
    1
  ) AS usage_ratio_percent
FROM v_usage_base
GROUP BY period, company, feature;


-- ============================================================
-- 5b. Peak concurrent aggregated per period/company/feature
-- ============================================================

DROP VIEW IF EXISTS v_peak_weekly;

CREATE VIEW v_peak_weekly AS
SELECT strftime('%Y-W%W', ts_norm) AS period,
       company, feature,
       MAX(concurrent_count) AS peak_concurrent
FROM v_concurrent_snapshot
GROUP BY period, company, feature;


DROP VIEW IF EXISTS v_peak_monthly;

CREATE VIEW v_peak_monthly AS
SELECT strftime('%Y-%m', ts_norm) AS period,
       company, feature,
       MAX(concurrent_count) AS peak_concurrent
FROM v_concurrent_snapshot
GROUP BY period, company, feature;


DROP VIEW IF EXISTS v_peak_quarterly;

CREATE VIEW v_peak_quarterly AS
SELECT strftime('%Y', ts_norm) || '-Q' ||
       ((cast(strftime('%m', ts_norm) as integer)-1)/3 + 1) AS period,
       company, feature,
       MAX(concurrent_count) AS peak_concurrent
FROM v_concurrent_snapshot
GROUP BY period, company, feature;


DROP VIEW IF EXISTS v_peak_yearly;

CREATE VIEW v_peak_yearly AS
SELECT strftime('%Y', ts_norm) AS period,
       company, feature,
       MAX(concurrent_count) AS peak_concurrent
FROM v_concurrent_snapshot
GROUP BY period, company, feature;


-- ============================================================
-- 6. POLICY-AWARE EXTENSIONS (weekly/monthly/quarterly/yearly)
-- ============================================================

-- ---- WEEKLY EXT ----
DROP VIEW IF EXISTS v_usage_weekly_ext;

CREATE VIEW v_usage_weekly_ext AS
SELECT
  w.*,
  ROUND(
    CAST(w.usage_count AS REAL) / NULLIF(w.active_snapshots,0),
    2
  ) AS avg_concurrent,
  pk.peak_concurrent,
  p.policy_max,
  ROUND(
    CAST(w.usage_count AS REAL) / NULLIF(w.active_snapshots,0)
    / NULLIF(p.policy_max, 0) * 100,
    1
  ) AS utilization_pct,
  CASE
    WHEN p.policy_max IS NULL THEN 'NO_POLICY'
    WHEN (CAST(w.usage_count AS REAL) / NULLIF(w.active_snapshots,0)) >= p.policy_max * 0.8
         THEN 'EFFECTIVE_USE'
    WHEN (CAST(w.usage_count AS REAL) / NULLIF(w.active_snapshots,0)) >= p.policy_max * 0.3
         THEN 'PARTIAL_USE'
    ELSE 'UNDERUTILIZED'
  END AS utilization_status
FROM v_usage_weekly w
LEFT JOIN v_peak_weekly pk
  ON w.period = pk.period AND w.company = pk.company AND w.feature = pk.feature
LEFT JOIN (
  SELECT company, feature, MAX(policy_max) AS policy_max
  FROM license_policy
  GROUP BY company, feature
) p ON w.company = p.company AND w.feature = p.feature;


-- ---- MONTHLY EXT ----
DROP VIEW IF EXISTS v_usage_monthly_ext;

CREATE VIEW v_usage_monthly_ext AS
SELECT
  m.*,
  ROUND(
    CAST(m.usage_count AS REAL) / NULLIF(m.active_snapshots,0),
    2
  ) AS avg_concurrent,
  pk.peak_concurrent,
  p.policy_max,
  ROUND(
    CAST(m.usage_count AS REAL) / NULLIF(m.active_snapshots,0)
    / NULLIF(p.policy_max, 0) * 100,
    1
  ) AS utilization_pct,
  CASE
    WHEN p.policy_max IS NULL THEN 'NO_POLICY'
    WHEN (CAST(m.usage_count AS REAL) / NULLIF(m.active_snapshots,0)) >= p.policy_max * 0.8
         THEN 'EFFECTIVE_USE'
    WHEN (CAST(m.usage_count AS REAL) / NULLIF(m.active_snapshots,0)) >= p.policy_max * 0.3
         THEN 'PARTIAL_USE'
    ELSE 'UNDERUTILIZED'
  END AS utilization_status
FROM v_usage_monthly m
LEFT JOIN v_peak_monthly pk
  ON m.period = pk.period AND m.company = pk.company AND m.feature = pk.feature
LEFT JOIN (
  SELECT company, feature, MAX(policy_max) AS policy_max
  FROM license_policy
  GROUP BY company, feature
) p ON m.company = p.company AND m.feature = p.feature;


-- ---- QUARTERLY EXT ----
DROP VIEW IF EXISTS v_usage_quarterly_ext;

CREATE VIEW v_usage_quarterly_ext AS
SELECT
  q.*,
  ROUND(
    CAST(q.usage_count AS REAL) / NULLIF(q.active_snapshots,0),
    2
  ) AS avg_concurrent,
  pk.peak_concurrent,
  p.policy_max,
  ROUND(
    CAST(q.usage_count AS REAL) / NULLIF(q.active_snapshots,0)
    / NULLIF(p.policy_max, 0) * 100,
    1
  ) AS utilization_pct,
  CASE
    WHEN p.policy_max IS NULL THEN 'NO_POLICY'
    WHEN (CAST(q.usage_count AS REAL) / NULLIF(q.active_snapshots,0)) >= p.policy_max * 0.8
         THEN 'EFFECTIVE_USE'
    WHEN (CAST(q.usage_count AS REAL) / NULLIF(q.active_snapshots,0)) >= p.policy_max * 0.3
         THEN 'PARTIAL_USE'
    ELSE 'UNDERUTILIZED'
  END AS utilization_status
FROM v_usage_quarterly q
LEFT JOIN v_peak_quarterly pk
  ON q.period = pk.period AND q.company = pk.company AND q.feature = pk.feature
LEFT JOIN (
  SELECT company, feature, MAX(policy_max) AS policy_max
  FROM license_policy
  GROUP BY company, feature
) p ON q.company = p.company AND q.feature = p.feature;


-- ---- YEARLY EXT ----
DROP VIEW IF EXISTS v_usage_yearly_ext;

CREATE VIEW v_usage_yearly_ext AS
SELECT
  y.*,
  ROUND(
    CAST(y.usage_count AS REAL) / NULLIF(y.active_snapshots,0),
    2
  ) AS avg_concurrent,
  pk.peak_concurrent,
  p.policy_max,
  ROUND(
    CAST(y.usage_count AS REAL) / NULLIF(y.active_snapshots,0)
    / NULLIF(p.policy_max, 0) * 100,
    1
  ) AS utilization_pct,
  CASE
    WHEN p.policy_max IS NULL THEN 'NO_POLICY'
    WHEN (CAST(y.usage_count AS REAL) / NULLIF(y.active_snapshots,0)) >= p.policy_max * 0.8
         THEN 'EFFECTIVE_USE'
    WHEN (CAST(y.usage_count AS REAL) / NULLIF(y.active_snapshots,0)) >= p.policy_max * 0.3
         THEN 'PARTIAL_USE'
    ELSE 'UNDERUTILIZED'
  END AS utilization_status
FROM v_usage_yearly y
LEFT JOIN v_peak_yearly pk
  ON y.period = pk.period AND y.company = pk.company AND y.feature = pk.feature
LEFT JOIN (
  SELECT company, feature, MAX(policy_max) AS policy_max
  FROM license_policy
  GROUP BY company, feature
) p ON y.company = p.company AND y.feature = p.feature;
