/* Layer 1, the baseline, at the storage grain for every version. For an open version it is the baseline in force: our
   own calculation for the accounts the plan calculates, the forecasting system's run for the accounts that take it
   (line source FORECAST), and our calculation again wherever the run does not reach (plan.baseline_in_force). For a frozen version it is what
   was entered — period contributions spread to weeks by the history shape (or by catchment where the material had no
   history). Either way nobody typed a week. */
MODEL (name plan.layer1_lines, kind FULL, grain (version_id, line_source, material_code, ship_to_code, week_id));
WITH computed AS (
  SELECT version_id, CASE source WHEN 'forecast_run' THEN 'FORECAST' ELSE 'BASELINE' END AS line_source, material_code, ship_to_code, account_code, week_id, cases
  FROM plan.baseline_in_force
),
entered AS (
  SELECT ec.version_id, ec.entry_id AS line_source, ec.material_code, ec.ship_to_code, ec.account_code, ec.week_id,
         ec.value * (CASE ec.spread_rule WHEN 'catchment' THEN ec.w_catchment ELSE ec.w_history_shape END)
           / NULLIF(SUM(CASE ec.spread_rule WHEN 'catchment' THEN ec.w_catchment ELSE ec.w_history_shape END) OVER (PARTITION BY ec.entry_id), 0) AS cases
  FROM plan.entry_cells ec
  WHERE ec.layer_no = 1 AND ec.value_kind = 'cases'
)
SELECT * FROM computed WHERE cases > 0
UNION ALL
SELECT * FROM entered WHERE cases IS NOT NULL AND cases <> 0
