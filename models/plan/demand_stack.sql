/* The stack: every layer line at the storage grain, keyed by version. Layer 1 as computed or entered; layers 2–9 as the
   entries spread — a rate on the version's own baseline, or cases spread by the baseline's shape within the slice, by the
   history shape, or by catchment where nothing was there before; layer 6 from the promotions calendar. The unconstrained
   demand plan is the sum. A line knows its source, so every case traces to the row that put it there. */
MODEL (name plan.demand_stack, kind FULL, grain (version_id, layer_no, line_source, effect_type, material_code, ship_to_code, week_id),
       audits (stack_cells_non_negative));
WITH layer1 AS (
  SELECT version_id, 1 AS layer_no, line_source, 'primary' AS effect_type,
         CASE WHEN line_source IN ('BASELINE', 'FORECAST') THEN 'FITTED' ELSE 'BUDGET' END AS reason_code,
         material_code, ship_to_code, account_code, week_id, cases
  FROM plan.layer1_lines
),
weighted AS (
  SELECT ec.*, b.cases AS baseline_cases,
         CASE ec.spread_rule WHEN 'catchment' THEN ec.w_catchment WHEN 'history_shape' THEN ec.w_history_shape ELSE COALESCE(b.cases, 0) END AS weight
  FROM plan.entry_cells ec
  LEFT JOIN plan.layer1_lines b ON b.version_id = ec.version_id AND b.material_code = ec.material_code AND b.ship_to_code = ec.ship_to_code AND b.week_id = ec.week_id
  WHERE ec.layer_no > 1
),
upper AS (
  SELECT version_id, layer_no, entry_id AS line_source, effect_type, reason_code, material_code, ship_to_code, account_code, week_id,
         CASE value_kind WHEN 'rate_on_baseline' THEN baseline_cases * value
              ELSE value * weight / NULLIF(SUM(weight) OVER (PARTITION BY entry_id), 0) END AS cases
  FROM weighted
),
promo AS (
  SELECT version_id, 6 AS layer_no, event_id AS line_source, effect_type, 'PROMOTION' AS reason_code, material_code, ship_to_code, account_code, week_id, cases
  FROM plan.promo_line
),
lines AS (SELECT * FROM layer1 UNION ALL SELECT * FROM upper UNION ALL SELECT * FROM promo)
SELECT l.version_id, l.layer_no, n.layer_name, n.owner_role, l.line_source, l.effect_type, l.reason_code,
       l.material_code, m.standard_material, l.ship_to_code, l.account_code, l.week_id, w.period, w.fiscal_year,
       l.cases, l.cases * m.case_net_kg / 1000 AS tonnes
FROM lines l
JOIN dims.dim_week w ON w.week_id = l.week_id
JOIN dims.dim_material m ON m.material_code = l.material_code
JOIN plan.ref_layer n ON n.layer_no = l.layer_no
WHERE l.cases IS NOT NULL AND l.cases <> 0
