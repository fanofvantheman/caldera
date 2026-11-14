/* Every forward view is a version — named by the cycle that produced it, with a reach, a calendar variant, the standard
   it is valued at and the reference it is read against. Versions are data: a key on every planned fact.
   Two reaches. horizon_start–horizon_end is what the models calculate on the version. The from point is the last period
   the version treats as actual — fixed when it is named, never later than the last closed period, and not moved when a
   later period closes. Every grid reads its actual periods from it, not from the calendar, and shows the plan for the
   horizon after it: periods by month (horizon_periods), then quarters (horizon_quarters, none yet), ending at
   plan_through — never past what the models calculate. The horizon is the version's own, set from its kind when named,
   and changed only by an act (a `horizon` row in the version acts, with a reason and a receipt): the latest stands, and
   the horizon it was named with is kept beside it.
   A version is named from a base by an act (a `name` row in the version acts) that carries the version as named — the
   base's kind, year, reach, calendar, standard, reference and owner copied onto it at naming, with its own from point and
   horizon; it is read here beside the versions the business had before the build, and carries its base and that act. */
MODEL (name dims.ctl_version, kind FULL, grain (version_id), audits (version_vocabulary, version_from_point));
WITH v AS (
  SELECT version_id::TEXT AS version_id, version_kind::TEXT AS version_kind, cycle::TEXT AS cycle, fiscal_year::TEXT AS fiscal_year,
         horizon_start::TEXT AS horizon_start, horizon_end::TEXT AS horizon_end, calendar_variant::TEXT AS calendar_variant,
         standard_version::TEXT AS standard_version, NULLIF(reference_version::TEXT, '') AS reference_version,
         status::TEXT AS status, owner::TEXT AS owner, named_on::DATE AS named_on, NULLIF(from_period::TEXT, '') AS from_period,
         horizon_periods::INT AS horizon_periods, horizon_quarters::INT AS horizon_quarters, NULL::TEXT AS base_version, NULL::TEXT AS named_by_act
  FROM bronze.ctl_version
  UNION ALL
  SELECT * FROM (SELECT version_id::TEXT, version_kind::TEXT, NULLIF(cycle::TEXT, ''), NULLIF(fiscal_year::TEXT, ''), horizon_start::TEXT, horizon_end::TEXT,
         calendar_variant::TEXT, standard_version::TEXT, NULLIF(reference_version::TEXT, ''), 'open', owner::TEXT, entered_on::DATE,
         NULLIF(from_period::TEXT, ''), NULLIF(horizon_periods::TEXT, '')::INT, COALESCE(NULLIF(horizon_quarters::TEXT, '')::INT, 0),
         base_version::TEXT, act_id::TEXT
  FROM bronze.reg_version_act WHERE "act" = 'name'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY version_id ORDER BY entered_on::TEXT, source_file, file_row_number) = 1)
),
h AS (SELECT version_id::TEXT AS version_id, NULLIF(horizon_periods::TEXT, '')::INT AS horizon_periods FROM bronze.reg_version_act
       WHERE "act" = 'horizon' AND NULLIF(horizon_periods::TEXT, '') IS NOT NULL
       QUALIFY ROW_NUMBER() OVER (PARTITION BY version_id ORDER BY entered_on::TEXT DESC, source_file DESC, file_row_number DESC) = 1),
p AS (SELECT period::TEXT AS period, ROW_NUMBER() OVER (ORDER BY period) AS seq FROM bronze.ctl_period),
last_closed AS (SELECT MAX(period::TEXT) AS period FROM bronze.ctl_period WHERE state = 'CLOSED')
SELECT v.* REPLACE (COALESCE(h.horizon_periods, v.horizon_periods) AS horizon_periods), v.horizon_periods AS named_horizon_periods,
       t.period AS plan_through,
       v.from_period IS NOT NULL AND v.from_period <= l.period AS from_not_after_closed,
       t.period IS NOT NULL AND (v.horizon_periods = 0 OR t.period <= v.horizon_end) AS horizon_inside_reach
FROM v
CROSS JOIN last_closed l
LEFT JOIN h ON h.version_id = v.version_id
LEFT JOIN p f ON f.period = v.from_period
LEFT JOIN p t ON t.seq = f.seq + COALESCE(h.horizon_periods, v.horizon_periods)
