/* The cost of a case by pool: version × material × period × pool at the material's primary plant (DEC-20261116-03). Each
   pool is in exactly one component, and a component's cost per case is the sum of its pools'.
     material pools     the bill at the plant × each input's price in force (price × index ÷ 100), the input's pool read
                        from its type; the utility in the bill is the schedule's energy, an overhead pool, not priced here
     direct labour      plan.standard_labour: the route's crew hours × the loaded rate
     variable overhead  each variable pool's rate at the plant (plan.cost_pool_rate)
     fixed overhead     each fixed pool's cost for the year ÷ the planned cases at the plant, both set on the business plan
                        of the period's fiscal year and held on every plan of that year (DEC-20261115-06); a year with no
                        business plan takes the plan's own: its pool over the schedule's planned periods ÷ its own cases
                        over the same periods */
MODEL (name plan.standard_cost_pool, kind FULL, grain (version_id, material_code, period, pool_code));
WITH versions AS (SELECT version_id, from_period, plan_through FROM dims.ctl_version WHERE version_kind <> 'actual' AND from_period IS NOT NULL),
route AS (SELECT material_code, plant_code, line_code FROM dims.ref_route WHERE is_primary),
mats AS (SELECT version_id, material_code, period, plant_code FROM plan.standard_labour),
idx AS (SELECT version_id, period, assumption_code, value FROM plan.assumption_in_force),
price AS (
  SELECT m.version_id, m.period, p.material_code AS input, p.price * COALESCE(i.value, 100) / 100 AS price
  FROM (SELECT DISTINCT version_id, period FROM mats) m CROSS JOIN dims.reg_input_price p
  LEFT JOIN idx i ON i.version_id = m.version_id AND i.period = m.period AND i.assumption_code = p.index_code
  WHERE p.price_from <= m.period
  QUALIFY ROW_NUMBER() OVER (PARTITION BY m.version_id, m.period, p.material_code ORDER BY p.price_from DESC) = 1
),
material AS (
  SELECT m.version_id, m.material_code, m.period, m.plant_code, pl.pool_code, pl.component, SUM(b.quantity_per_case * pr.price) AS per_case
  FROM mats m
  JOIN dims.ref_bom b ON b.parent_material = m.material_code AND b.plant_code = m.plant_code
  JOIN dims.dim_input_material im ON im.material_code = b.component_material AND im.material_type <> 'utility'
  JOIN dims.ref_cost_pool pl ON pl.input_type = im.material_type
  JOIN price pr ON pr.version_id = m.version_id AND pr.period = m.period AND pr.input = b.component_material
  GROUP BY ALL
),
labour AS (
  SELECT version_id, material_code, period, plant_code, 'DIRECT_LABOUR' AS pool_code, 'labour' AS component, labour_cost AS per_case
  FROM plan.standard_labour WHERE labour_cost IS NOT NULL
),
var_line AS (SELECT DISTINCT version_id, plant_code, pool_code, line_rate FROM plan.cost_pool_rate WHERE component = 'variable_overhead'),
variable AS (
  SELECT m.version_id, m.material_code, m.period, m.plant_code, v.pool_code, 'variable_overhead' AS component,
         COALESCE(v.line_rate, 0) + COALESCE(r.rate_not_by_cases, 0) AS per_case
  FROM mats m JOIN var_line v ON v.version_id = m.version_id AND v.plant_code = m.plant_code
  LEFT JOIN plan.cost_pool_rate r ON r.version_id = m.version_id AND r.plant_code = m.plant_code AND r.pool_code = v.pool_code AND r.period = m.period
),
cases AS (SELECT d.version_id, r.plant_code, d.period, SUM(d.cases) AS cases FROM plan.demand_financialised d JOIN route r USING (material_code) GROUP BY ALL),
sched_periods AS (SELECT DISTINCT version_id, period FROM plan.cost_pool_rate),
own_cases AS (
  SELECT c.version_id, c.plant_code, SUM(c.cases) AS cases FROM cases c JOIN sched_periods s USING (version_id, period) GROUP BY ALL
),
pool_year AS (                                       -- each fixed pool over the schedule's planned periods
  SELECT version_id, plant_code, pool_code, SUM(amount) AS pool_cost FROM plan.cost_pool_rate WHERE component = 'fixed_overhead' GROUP BY ALL
),
bp AS (
  SELECT fiscal_year::INT AS fiscal_year, version_id AS bp_version FROM dims.ctl_version
  WHERE version_kind = 'business_plan' AND base_version IS NULL
  QUALIFY ROW_NUMBER() OVER (PARTITION BY fiscal_year ORDER BY named_on, version_id) = 1
),
rate_from AS (                                       -- whose pools a period takes: its year's business plan where it has them, else its own
  SELECT m.version_id, m.material_code, m.period, m.plant_code,
         CASE WHEN h.held THEN b.bp_version ELSE m.version_id END AS rate_version, COALESCE(h.held, FALSE) AS fixed_held
  FROM mats m JOIN dims.dim_period p ON p.period = m.period LEFT JOIN bp b ON b.fiscal_year = p.fiscal_year::INT
  LEFT JOIN (SELECT DISTINCT version_id, plant_code, TRUE AS held FROM pool_year) h ON h.version_id = b.bp_version AND h.plant_code = m.plant_code
),
fixed AS (
  SELECT f.version_id, f.material_code, f.period, f.plant_code, y.pool_code, 'fixed_overhead' AS component,
         y.pool_cost / NULLIF(oc.cases, 0) AS per_case, y.pool_cost, oc.cases AS denominator, f.rate_version AS denominator_version, f.fixed_held
  FROM rate_from f JOIN pool_year y ON y.version_id = f.rate_version AND y.plant_code = f.plant_code
  LEFT JOIN own_cases oc ON oc.version_id = f.rate_version AND oc.plant_code = f.plant_code
)
SELECT version_id, material_code, period, plant_code, pool_code, component, per_case,
       NULL::DOUBLE AS pool_cost, NULL::DOUBLE AS denominator, NULL::TEXT AS denominator_version, NULL::BOOLEAN AS fixed_held FROM material
UNION ALL SELECT version_id, material_code, period, plant_code, pool_code, component, per_case, NULL, NULL, NULL, NULL FROM labour
UNION ALL SELECT version_id, material_code, period, plant_code, pool_code, component, per_case, NULL, NULL, NULL, NULL FROM variable
UNION ALL SELECT version_id, material_code, period, plant_code, pool_code, component, per_case, pool_cost, denominator, denominator_version, fixed_held FROM fixed
