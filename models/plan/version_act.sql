/* Closing and reopening a version, changing its horizon, naming one from a base, the arrivals a named version takes from
   its base (a `take`: a forecasting run for an account, or a file from the promotions system — referenced, never
   copied), and promoting one to the latest view: one row per act, in the order taken — who, when, why (a
   horizon act carries the new number of periods by month; dims.ctl_version reads the latest). A version's state is read from
   this register (plan.version_state), never edited in place; the face places an act as a file in the landing and the
   generator writes the acts the business took before the build began. */
MODEL (name plan.version_act, kind FULL, grain (act_id));
SELECT a.act_id::TEXT AS act_id, a.version_id::TEXT AS version_id, a."act"::TEXT AS "act", NULLIF(a.reason::TEXT, '') AS reason,
       a.entered_by::TEXT AS entered_by, a.entered_on::TEXT AS entered_on, NULLIF(a.horizon_periods::TEXT, '')::INT AS horizon_periods,
       NULLIF(a.base_version::TEXT, '') AS base_version, NULLIF(a.from_period::TEXT, '') AS from_period,
       NULLIF(a.arrival::TEXT, '') AS arrival, NULLIF(a.arrival_id::TEXT, '') AS arrival_id, NULLIF(a.account_code::TEXT, '') AS account_code,
       CASE WHEN a.source_file LIKE '20%' THEN a.source_file END AS placed_by_file, a.file_row_number
FROM bronze.reg_version_act a
