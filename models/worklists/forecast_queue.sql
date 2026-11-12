/* Where the forecasting system's run and the plan's structures disagree and nobody has decided: one row per item, never
   per week. Theirs, not ours — a material code in the run the plan does not have: held out of the plan, with the cases
   it would bring, the description and the place in their structure it was sent with. Ours, not theirs — a material ×
   account the plan calculates and the run does not carry: the plan stands on our calculation meanwhile, marked. Routed
   to those who own the baseline; an item leaves when a person resolves it, and the resolution stands for later runs. */
MODEL (name plan.worklist_forecast_queue, kind FULL, grain (kind, item_code, account_code));
WITH run AS (SELECT * FROM plan.forecast_run WHERE in_force),
theirs AS (
  SELECT s.version_id, s.run_id, 'theirs_not_ours' AS kind, s.sent_code AS item_code, 'ALL' AS account_code,
         STRING_AGG(DISTINCT s.account_code, ', ' ORDER BY s.account_code) AS accounts, ANY_VALUE(s.sent_description) AS description,
         ANY_VALUE(s.sender_hierarchy) AS sender_hierarchy, SUM(s.cases) AS cases, COUNT(DISTINCT s.week_start) AS weeks, MIN(s.week_start) AS first_week,
         NULL::INT AS weeks_of_history, 'held out of the plan' AS meanwhile
  FROM plan.forecast_series s WHERE s.state = 'held' GROUP BY ALL
),
ours AS (
  SELECT b.version_id, r.run_id, 'ours_not_theirs' AS kind, b.material_code AS item_code, b.account_code,
         b.account_code AS accounts, ANY_VALUE(m.material_name) AS description, NULL AS sender_hierarchy, SUM(b.cases) AS cases,
         COUNT(DISTINCT b.week_id) AS weeks, NULL::DATE AS first_week, MAX(h.weeks_fitted)::INT AS weeks_of_history, 'on our calculation' AS meanwhile
  FROM plan.baseline_in_force b
  JOIN run r ON r.version_id = b.version_id
  JOIN dims.dim_material m ON m.material_code = b.material_code
  JOIN dims.dim_week w ON w.week_id = b.week_id AND w.week_start BETWEEN r.first_week AND r.last_day
  LEFT JOIN (SELECT material_code, account_code, MAX(n) AS weeks_fitted
             FROM (SELECT material_code, ship_to_code, account_code, SUM(weeks_fitted) AS n FROM plan.history_shape GROUP BY ALL) GROUP BY ALL) h
         ON h.material_code = b.material_code AND h.account_code = b.account_code
  WHERE b.source = 'our_calculation_gap' GROUP BY ALL
),
readers AS (SELECT STRING_AGG(DISTINCT principal, ', ') AS whose FROM dims.effective_entitlements WHERE action = 'layer.1.enter')
SELECT q.*, CASE q.kind WHEN 'theirs_not_ours' THEN q.item_code || ' (' || COALESCE(q.description, 'no description') || ') is in run ' || q.run_id || ' and not in the plan — held, ' || ROUND(q.cases)::BIGINT || ' cases'
                        ELSE q.item_code || ' at ' || q.account_code || ' is in the plan and not in run ' || q.run_id || ' — on our calculation, ' || ROUND(q.cases)::BIGINT || ' cases' END AS item,
       r.whose
FROM (SELECT * FROM theirs UNION ALL SELECT * FROM ours) q CROSS JOIN readers r
