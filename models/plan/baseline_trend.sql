/* The fitted trend per category: the last 52 closed weeks over the 52 before, on cleansed history (promotion weeks and
   the dip week after them removed, materials not yet launched or already run out excluded by their active window). */
MODEL (name plan.baseline_trend, kind FULL, grain (category_code));
WITH closed AS (
  SELECT w.week_id, w.week_sequence, MAX(w.week_sequence) OVER () AS last_seq
  FROM dims.dim_week w JOIN dims.dim_period p ON p.period = w.period WHERE p.period_state = 'CLOSED'
),
cleansed AS (
  SELECT s.material_code, m.category_code, c.week_sequence, c.last_seq, s.cases,
         s.is_promo_week OR COALESCE(LAG(s.is_promo_week) OVER (PARTITION BY s.material_code, s.ship_to_code ORDER BY c.week_sequence), FALSE) AS excluded
  FROM history.shipments s JOIN closed c ON c.week_id = s.week_id JOIN dims.dim_material m ON m.material_code = s.material_code
)
SELECT category_code,
       SUM(CASE WHEN week_sequence > last_seq - 52 THEN cases END) AS cases_last_52,
       SUM(CASE WHEN week_sequence <= last_seq - 52 AND week_sequence > last_seq - 104 THEN cases END) AS cases_prior_52,
       SUM(CASE WHEN week_sequence > last_seq - 52 THEN cases END)
         / NULLIF(SUM(CASE WHEN week_sequence <= last_seq - 52 AND week_sequence > last_seq - 104 THEN cases END), 0) - 1 AS yoy_rate
FROM cleansed WHERE NOT excluded
GROUP BY category_code
