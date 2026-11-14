/* Every forward view is a version — named by the cycle that produced it, with a reach, a calendar variant, the standard
   it is valued at and the reference it is read against. Versions are data: a key on every planned fact.
   Two reaches. horizon_start–horizon_end is what the models calculate on the version. The from point is the last period
   the version treats as actual — fixed when it is named, never later than the last closed period, and not moved when a
   later period closes. Every grid reads its actual periods from it, not from the calendar, and shows the plan for the
   horizon after it: periods by month (horizon_periods), then quarters (horizon_quarters, none yet), ending at
   plan_through — never past what the models calculate. The horizon is the version's own, set from its kind when named. */
MODEL (name dims.ctl_version, kind FULL, grain (version_id), audits (version_vocabulary, version_from_point));
WITH v AS (
  SELECT version_id::TEXT AS version_id, version_kind::TEXT AS version_kind, cycle::TEXT AS cycle, fiscal_year::TEXT AS fiscal_year,
         horizon_start::TEXT AS horizon_start, horizon_end::TEXT AS horizon_end, calendar_variant::TEXT AS calendar_variant,
         standard_version::TEXT AS standard_version, NULLIF(reference_version::TEXT, '') AS reference_version,
         status::TEXT AS status, owner::TEXT AS owner, named_on::DATE AS named_on, NULLIF(from_period::TEXT, '') AS from_period,
         horizon_periods::INT AS horizon_periods, horizon_quarters::INT AS horizon_quarters
  FROM bronze.ctl_version
),
p AS (SELECT period::TEXT AS period, ROW_NUMBER() OVER (ORDER BY period) AS seq FROM bronze.ctl_period),
last_closed AS (SELECT MAX(period::TEXT) AS period FROM bronze.ctl_period WHERE state = 'CLOSED')
SELECT v.*, t.period AS plan_through,
       v.from_period IS NOT NULL AND v.from_period <= l.period AS from_not_after_closed,
       t.period IS NOT NULL AND (v.horizon_periods = 0 OR t.period <= v.horizon_end) AS horizon_inside_reach
FROM v
CROSS JOIN last_closed l
LEFT JOIN p f ON f.period = v.from_period
LEFT JOIN p t ON t.seq = f.seq + v.horizon_periods
