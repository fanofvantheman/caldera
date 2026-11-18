/* An actual period's cost as reported, by plant × pool × period (DEC-20261117-01): the ledgers' actuals read through the
   cost pool map (plan.cost_pool_cell) — what the map was declared for — beside the standard absorbed on the cases made.
   A ledger does not know what one product cost; its grain is the plant.
     actual      the ledger's cost in the pool at the plant; material consumed is booked to the two material accounts
                 (DEC-20261117-01 point 6). Direct labour is the route's hours on the actual cases at the standard rate,
                 and the rest of the wage cell is indirect labour (DEC-20261116-03 point 6) — so direct labour carries no
                 variance and indirect labour carries all of the wage cell's
     absorbed    the standard set on the business plan of the period's year × the actual cases of each material with a
                 standard (cases shipped stand in for cases made: Caldera has no production history)
     variance    actual − absorbed, whole by pool: there are no actual quantities to split price from usage or rate from
                 efficiency. A fixed pool splits as a plan does: spending (actual − the business plan's in the period) and
                 volume (the business plan's − the rate × the actual cases)
   A year with no standard has no absorption: the actual cost stands, no variance, and the wage cell is not split. Cases of
   a material with no standard in a year that has one absorb nothing; their cost is in the variance. */
MODEL (name plan.actual_cost_pool, kind FULL, grain (plant_code, pool_code, period));
WITH route AS (SELECT material_code, plant_code FROM dims.ref_route WHERE is_primary),
bp AS (
  SELECT fiscal_year::INT AS fiscal_year, version_id AS bp_version FROM dims.ctl_version
  WHERE version_kind = 'business_plan' AND base_version IS NULL
  QUALIFY ROW_NUMBER() OVER (PARTITION BY fiscal_year ORDER BY named_on, version_id) = 1
),
cases AS (
  SELECT s.material_code, r.plant_code, s.period, p.fiscal_year::INT AS fiscal_year, SUM(s.cases) AS cases
  FROM history.shipments s JOIN route r USING (material_code) JOIN dims.dim_period p ON p.period = s.period GROUP BY ALL
),
plant_cases AS (SELECT plant_code, period, SUM(cases) AS cases FROM cases GROUP BY ALL),
ledger AS (
  SELECT c.plant_code, c.pool_code, c.component, a.period, SUM(a.amount) AS amount
  FROM plan.cost_actual a JOIN plan.cost_pool_cell c ON c.entity_code = a.entity_code AND c.cost_centre_code = a.cost_centre_code AND c.account_code = a.account_code
  WHERE a.state = 'mapped' AND c.component IS NOT NULL AND c.plant_code IS NOT NULL GROUP BY ALL
),
absorbed AS (
  SELECT c.plant_code, s.pool_code, s.component, c.period, SUM(c.cases * s.std_per_case) AS absorbed, SUM(c.cases) AS cases_with_standard
  FROM cases c JOIN plan.standard_cost_pool s ON s.material_code = c.material_code AND s.plant_code = c.plant_code AND s.fiscal_year = c.fiscal_year
  GROUP BY ALL
),
direct AS (SELECT plant_code, period, absorbed AS direct FROM absorbed WHERE pool_code = 'DIRECT_LABOUR'),
actual AS (
  SELECT l.plant_code, l.pool_code, l.component, l.period,
         l.amount - CASE WHEN l.pool_code = 'INDIRECT_LABOUR' THEN COALESCE(d.direct, 0) ELSE 0 END AS amount
  FROM ledger l LEFT JOIN direct d ON d.plant_code = l.plant_code AND d.period = l.period
  UNION ALL SELECT plant_code, 'DIRECT_LABOUR', 'labour', period, direct FROM direct
),
joined AS (
  SELECT COALESCE(a.plant_code, b.plant_code) AS plant_code, COALESCE(a.pool_code, b.pool_code) AS pool_code,
         COALESCE(a.component, b.component) AS component, COALESCE(a.period, b.period) AS period,
         a.amount AS actual, b.absorbed, b.cases_with_standard
  FROM actual a FULL JOIN absorbed b ON b.plant_code = a.plant_code AND b.pool_code = a.pool_code AND b.period = a.period
)
SELECT j.plant_code, j.pool_code, j.component, j.period, p.fiscal_year::INT AS fiscal_year, pc.cases, j.cases_with_standard,
       COALESCE(j.actual, 0) AS actual, j.absorbed, j.absorbed IS NOT NULL AS has_standard, CASE WHEN j.absorbed IS NOT NULL THEN b.bp_version END AS set_on,
       CASE WHEN j.absorbed IS NOT NULL THEN COALESCE(j.actual, 0) - j.absorbed END AS variance,
       CASE WHEN j.absorbed IS NOT NULL AND j.component = 'fixed_overhead' THEN r.amount END AS budget_incurred,
       CASE WHEN j.absorbed IS NOT NULL AND j.component = 'fixed_overhead' THEN COALESCE(j.actual, 0) - COALESCE(r.amount, 0) END AS spending,
       CASE WHEN j.absorbed IS NOT NULL AND j.component = 'fixed_overhead' THEN COALESCE(r.amount, 0) - j.absorbed END AS volume
FROM joined j
JOIN dims.dim_period p ON p.period = j.period
LEFT JOIN plant_cases pc ON pc.plant_code = j.plant_code AND pc.period = j.period
LEFT JOIN bp b ON b.fiscal_year = p.fiscal_year::INT
LEFT JOIN plan.cost_pool_rate r ON r.version_id = b.bp_version AND r.plant_code = j.plant_code AND r.pool_code = j.pool_code AND r.period = j.period
