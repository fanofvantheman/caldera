/* The baseline the open version stands on, cell-week by cell-week, and where each came from. Each account says where its
   baseline is made. calculated: the account's baseline is ours. forecast_run: the forecasting system's series, which
   arrives by account and is spread to the account's ship-tos by our own history shape for that week (by the cell's
   share of the year where that week has none; by stores served where the material has never shipped there) — the
   shape stays ours whatever the source. Where the run and the plan disagree the cell never reads zero by accident:
   our_calculation_gap — a material × account we calculate and the run does not carry, until someone decides;
   our_calculation_kept — the same, after someone has said to keep ours; our_calculation_beyond_run — past the run's last
   week. A series someone has set to zero on purpose has no rows here. */
MODEL (name plan.baseline_in_force, kind FULL, grain (version_id, material_code, ship_to_code, week_id));
WITH run AS (SELECT * FROM plan.forecast_run WHERE in_force),
series AS (
  SELECT version_id, material_code, account_code, week_id, SUM(cases) AS cases
  FROM plan.forecast_series WHERE state = 'in' GROUP BY ALL
),
year_shape AS (SELECT material_code, ship_to_code, SUM(shape_cases) AS shape_year FROM plan.history_shape GROUP BY ALL),
weighted AS (
  SELECT s.version_id, s.material_code, st.ship_to_code, s.account_code, s.week_id, s.cases,
         COALESCE(h.shape_cases, 0) AS w_week, COALESCE(y.shape_year, 0) AS w_year, GREATEST(st.stores_served, 1)::DOUBLE AS w_stores
  FROM series s
  JOIN dims.dim_week w ON w.week_id = s.week_id
  JOIN dims.dim_ship_to st ON st.account_code = s.account_code
  LEFT JOIN plan.history_shape h ON h.material_code = s.material_code AND h.ship_to_code = st.ship_to_code AND h.fiscal_week = LEAST(w.fiscal_week, 52)
  LEFT JOIN year_shape y ON y.material_code = s.material_code AND y.ship_to_code = st.ship_to_code
),
totals AS (
  SELECT *, SUM(w_week) OVER cell AS t_week, SUM(w_year) OVER cell AS t_year, SUM(w_stores) OVER cell AS t_stores
  FROM weighted WINDOW cell AS (PARTITION BY version_id, material_code, account_code, week_id)
),
landed AS (
  SELECT version_id, material_code, ship_to_code, account_code, week_id,
         cases * CASE WHEN t_week > 0 THEN w_week / t_week WHEN t_year > 0 THEN w_year / t_year ELSE w_stores / t_stores END AS cases,
         'forecast_run' AS source,
         CASE WHEN t_week > 0 THEN 'history shape of the week' WHEN t_year > 0 THEN 'share of the year' ELSE 'stores served' END AS spread_by
  FROM totals
),
sent AS (SELECT DISTINCT version_id, material_code, account_code FROM series),
ours AS (
  SELECT b.version_id, b.material_code, b.ship_to_code, b.account_code, b.week_id, b.cases,
         CASE WHEN r.run_id IS NULL OR a.baseline_source <> 'FORECAST' THEN 'calculated'
              WHEN b.week_start > r.last_day OR b.week_start < r.first_week THEN CASE WHEN s.material_code IS NULL AND res.resolution = 'zero' THEN NULL ELSE 'our_calculation_beyond_run' END
              WHEN s.material_code IS NOT NULL THEN NULL                        -- the run carries the series: what it says for the week is the week
              WHEN res.resolution = 'zero' THEN NULL
              WHEN res.resolution = 'keep_ours' THEN 'our_calculation_kept'
              ELSE 'our_calculation_gap' END AS source
  FROM plan.baseline_reference b
  JOIN dims.dim_account a ON a.account_code = b.account_code
  LEFT JOIN run r ON r.version_id = b.version_id AND r.account_code = b.account_code
  LEFT JOIN sent s ON s.version_id = b.version_id AND s.material_code = b.material_code AND s.account_code = b.account_code
  LEFT JOIN plan.forecast_resolution res ON res.kind = 'ours_not_theirs' AND res.item_code = b.material_code AND res.account_code = b.account_code
)
SELECT version_id, material_code, ship_to_code, account_code, week_id, cases, source, spread_by FROM landed WHERE cases > 0
UNION ALL
SELECT version_id, material_code, ship_to_code, account_code, week_id, cases, source, NULL FROM ours WHERE source IS NOT NULL AND cases > 0
