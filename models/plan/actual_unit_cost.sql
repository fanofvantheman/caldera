/* A material's actual cost per case in an actual period, as a share (DEC-20261117-01 point 4): its standard on its cases
   plus its share of each pool's variance at its plant, in proportion to the standard it absorbed from that pool — so each
   pool's actual per case is the standard's × actual ÷ absorbed at the plant. No other allocation is offered, and the page
   marks the figure as apportioned. Summed over the materials at a plant it is the ledger's cost, to the dollar.
   Only where the period's year has a standard: the variance lines are whole by component — material, labour, variable
   overhead, fixed overhead — with nothing split into price and usage or rate and efficiency (point 5). */
MODEL (name plan.actual_unit_cost, kind FULL, grain (material_code, period));
WITH route AS (SELECT material_code, plant_code FROM dims.ref_route WHERE is_primary),
cases AS (
  SELECT s.material_code, r.plant_code, s.period, p.fiscal_year::INT AS fiscal_year, SUM(s.cases) AS cases
  FROM history.shipments s JOIN route r USING (material_code) JOIN dims.dim_period p ON p.period = s.period GROUP BY ALL
),
pool AS (
  SELECT c.material_code, c.plant_code, c.period, c.fiscal_year, c.cases, s.pool_code, s.component, s.std_per_case, a.actual, a.absorbed, s.set_on,
         s.std_per_case * COALESCE(a.actual, 0) / NULLIF(a.absorbed, 0) AS actual_per_case
  FROM cases c
  JOIN plan.standard_cost_pool s ON s.material_code = c.material_code AND s.plant_code = c.plant_code AND s.fiscal_year = c.fiscal_year
  LEFT JOIN plan.actual_cost_pool a ON a.plant_code = c.plant_code AND a.pool_code = s.pool_code AND a.period = c.period
  WHERE c.cases > 0
)
SELECT material_code, ANY_VALUE(plant_code) AS plant_code, period, ANY_VALUE(fiscal_year) AS fiscal_year, ANY_VALUE(set_on) AS set_on, ANY_VALUE(cases) AS cases,
       SUM(CASE WHEN component = 'material' THEN actual_per_case END) AS material_cost,
       SUM(CASE WHEN component = 'labour' THEN actual_per_case END) AS labour_cost,
       SUM(CASE WHEN component = 'variable_overhead' THEN actual_per_case END) AS variable_overhead,
       SUM(CASE WHEN component = 'fixed_overhead' THEN actual_per_case END) AS fixed_overhead,
       SUM(actual_per_case) AS unit_cost,
       SUM(CASE WHEN component = 'material' THEN std_per_case END) AS std_material,
       SUM(CASE WHEN component = 'labour' THEN std_per_case END) AS std_labour,
       SUM(CASE WHEN component = 'variable_overhead' THEN std_per_case END) AS std_variable,
       SUM(CASE WHEN component = 'fixed_overhead' THEN std_per_case END) AS std_fixed,
       SUM(std_per_case) AS std_cost,
       SUM(CASE WHEN component = 'material' THEN actual_per_case - std_per_case END) AS var_material,
       SUM(CASE WHEN component = 'labour' THEN actual_per_case - std_per_case END) AS var_labour,
       SUM(CASE WHEN component = 'variable_overhead' THEN actual_per_case - std_per_case END) AS var_oh,
       SUM(CASE WHEN component = 'fixed_overhead' THEN actual_per_case - std_per_case END) AS fixed_oh,
       SUM(actual_per_case - std_per_case) AS var_total
FROM pool GROUP BY material_code, period
