/* The shape history gives each cell: cleansed shipments by material × ship-to × fiscal week, each history week re-based
   to the latest close by the category trend, then averaged — so the shape carries the level as at now and each
   ship-to's own seasonality. Zero weeks inside a cell's active window count; weeks before launch or after run-out
   do not. This is what the baseline is read from and what spreads a period contribution to weeks. */
MODEL (name plan.history_shape, kind FULL, grain (material_code, ship_to_code, fiscal_week));
WITH closed AS (
  SELECT w.week_id, w.fiscal_week, w.week_sequence, MAX(w.week_sequence) OVER () AS last_seq
  FROM dims.dim_week w JOIN dims.dim_period p ON p.period = w.period WHERE p.period_state = 'CLOSED'
),
cells AS (SELECT DISTINCT material_code, ship_to_code, account_code FROM history.shipments),
grid AS (
  SELECT c.material_code, c.ship_to_code, c.account_code, h.week_id, h.fiscal_week, h.week_sequence, h.last_seq,
         COALESCE(s.cases, 0) AS cases, COALESCE(s.is_promo_week, FALSE) AS promo
  FROM cells c CROSS JOIN closed h
  LEFT JOIN history.shipments s ON s.material_code = c.material_code AND s.ship_to_code = c.ship_to_code AND s.week_id = h.week_id
),
flagged AS (
  SELECT g.*, COALESCE(LAG(promo) OVER (PARTITION BY material_code, ship_to_code ORDER BY week_sequence), FALSE) AS prior_promo,
         MIN(CASE WHEN cases > 0 THEN week_sequence END) OVER (PARTITION BY material_code, ship_to_code) AS first_seq,
         MAX(CASE WHEN cases > 0 THEN week_sequence END) OVER (PARTITION BY material_code, ship_to_code) AS last_active_seq
  FROM grid g
)
SELECT f.material_code, f.ship_to_code, f.account_code, LEAST(f.fiscal_week, 52) AS fiscal_week,
       AVG(f.cases * POWER(1 + COALESCE(t.yoy_rate, 0), (f.last_seq - f.week_sequence) / 52.0)) AS shape_cases,
       COUNT(*) AS weeks_fitted, MAX(f.last_active_seq) AS last_active_seq, MAX(f.last_seq) AS last_closed_seq
FROM flagged f
JOIN dims.dim_material m ON m.material_code = f.material_code
LEFT JOIN plan.baseline_trend t ON t.category_code = m.category_code
WHERE NOT f.promo AND NOT f.prior_promo AND f.week_sequence BETWEEN f.first_seq AND f.last_active_seq
GROUP BY ALL
