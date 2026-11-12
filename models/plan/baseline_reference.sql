/* Our own calculation of the baseline, for every account whatever its source: the history shape of each cell-week carried
   forward by the category trend over the version's horizon. Crude on purpose — the same fiscal week averaged over the
   history with promotion weeks and the week after removed, at the category's year-on-year rate. It is the baseline of
   the accounts the plan calculates, and the reference a baseline made elsewhere is read against. */
MODEL (name plan.baseline_reference, kind FULL, grain (version_id, material_code, ship_to_code, week_id));
SELECT v.version_id, hs.material_code, hs.ship_to_code, hs.account_code, w.week_id, w.week_start, hs.weeks_fitted,
       hs.shape_cases * POWER(1 + COALESCE(t.yoy_rate, 0), (w.week_sequence - hs.last_closed_seq) / 52.0) AS cases
FROM dims.ctl_version v
JOIN dims.dim_week w ON w.period BETWEEN v.horizon_start AND v.horizon_end
JOIN plan.history_shape hs ON hs.fiscal_week = LEAST(w.fiscal_week, 52)
JOIN dims.dim_material m ON m.material_code = hs.material_code
LEFT JOIN plan.baseline_trend t ON t.category_code = m.category_code
WHERE v.status = 'open' AND hs.last_active_seq = hs.last_closed_seq        -- a cell that stopped shipping has no baseline
  AND hs.shape_cases > 0
