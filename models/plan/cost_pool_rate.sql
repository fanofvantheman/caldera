/* Each overhead pool at each plant by version × period, from the schedule lines the map puts in it (plan.cost_pool_cell):
     variable pools  rate      a line driven by cases made at the plant gives its own rate, once (a rate is the line's,
                               for every period); any other line in the pool, its amount ÷ the plant's cases in the period
     fixed pools     amount    every line's amount in the period; indirect labour less the direct labour the route's crews
                               take for the plan's cases at the plant (the wage cell is one cell; the route splits it)
   The cost centre stops here: past this model the grain is pool × plant (DEC-20261116-03 point 6). */
MODEL (name plan.cost_pool_rate, kind FULL, grain (version_id, plant_code, pool_code, period));
WITH route AS (SELECT material_code, plant_code FROM dims.ref_route WHERE is_primary),
line AS (
  SELECT s.version_id, c.plant_code, c.pool_code, c.component, s.period, s.entity_code, s.cost_centre_code, s.account_code, s.rate, s.amount,
         s.driver = 'cases_made_' || LOWER(c.plant_code) AS by_cases
  FROM plan.opex_schedule s JOIN plan.cost_pool_cell c USING (entity_code, cost_centre_code, account_code)
  WHERE c.component IN ('variable_overhead', 'fixed_overhead') AND c.plant_code IS NOT NULL
),
cases AS (SELECT d.version_id, r.plant_code, d.period, SUM(d.cases) AS cases FROM plan.demand_financialised d JOIN route r USING (material_code) GROUP BY ALL),
direct AS (
  SELECT d.version_id, l.plant_code, d.period, SUM(d.cases * l.labour_cost) AS direct_labour
  FROM (SELECT version_id, material_code, period, SUM(cases) cases FROM plan.demand_financialised GROUP BY ALL) d
  JOIN plan.planned_labour l USING (version_id, material_code, period) GROUP BY ALL
),
line_rate AS (                                       -- the lines driven by cases made: each line's own rate, once
  SELECT version_id, plant_code, pool_code, SUM(rate) AS line_rate
  FROM (SELECT DISTINCT version_id, plant_code, pool_code, entity_code, cost_centre_code, account_code, rate FROM line WHERE component = 'variable_overhead' AND by_cases)
  GROUP BY ALL
),
by_period AS (
  SELECT version_id, plant_code, pool_code, ANY_VALUE(component) AS component, period, SUM(amount) AS amount,
         SUM(CASE WHEN component = 'variable_overhead' AND NOT COALESCE(by_cases, FALSE) THEN amount ELSE 0 END) AS amount_not_by_cases
  FROM line GROUP BY version_id, plant_code, pool_code, period
)
SELECT b.version_id, b.plant_code, b.pool_code, b.component, b.period, b.amount AS lines_amount,
       CASE WHEN b.pool_code = 'INDIRECT_LABOUR' THEN COALESCE(d.direct_labour, 0) ELSE 0 END AS direct_labour,
       b.amount - CASE WHEN b.pool_code = 'INDIRECT_LABOUR' THEN COALESCE(d.direct_labour, 0) ELSE 0 END AS amount,
       c.cases,
       CASE WHEN b.component = 'variable_overhead' THEN lr.line_rate END AS line_rate,
       CASE WHEN b.component = 'variable_overhead' THEN b.amount_not_by_cases / NULLIF(c.cases, 0) END AS rate_not_by_cases
FROM by_period b
LEFT JOIN direct d ON d.version_id = b.version_id AND d.plant_code = b.plant_code AND d.period = b.period
LEFT JOIN cases c ON c.version_id = b.version_id AND c.plant_code = b.plant_code AND c.period = b.period
LEFT JOIN line_rate lr ON lr.version_id = b.version_id AND lr.plant_code = b.plant_code AND lr.pool_code = b.pool_code
