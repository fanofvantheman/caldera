/* Layer 1, the baseline, at the storage grain for every version. For an open version it is computed: the history shape
   of each cell-week carried forward by the category trend over the version's horizon. For a frozen version it is what
   was entered — period contributions spread to weeks by the history shape (or by catchment where the material had no
   history). Either way nobody typed a week. */
MODEL (name plan.layer1_lines, kind FULL, grain (version_id, line_source, material_code, ship_to_code, week_id));
WITH computed AS (
  SELECT v.version_id, 'BASELINE' AS line_source, hs.material_code, hs.ship_to_code, hs.account_code, w.week_id,
         hs.shape_cases * POWER(1 + COALESCE(t.yoy_rate, 0), (w.week_sequence - hs.last_closed_seq) / 52.0) AS cases
  FROM dims.ctl_version v
  JOIN dims.dim_week w ON w.period BETWEEN v.horizon_start AND v.horizon_end
  JOIN plan.history_shape hs ON hs.fiscal_week = LEAST(w.fiscal_week, 52)
  JOIN dims.dim_material m ON m.material_code = hs.material_code
  LEFT JOIN plan.baseline_trend t ON t.category_code = m.category_code
  WHERE v.status = 'open' AND hs.last_active_seq = hs.last_closed_seq        -- a cell that stopped shipping has no baseline
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
