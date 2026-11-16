/* The standard by pool: material × plant × fiscal year × pool, set on the business plan of the year and held for the year
   (DEC-20261116-02 points 1–3, DEC-20261116-03). Each pool's standard per case, weighted by the business plan's own cases
   over its year, with what it was made from:
     material pools     Σ the inputs' standard usage × standard price (plan.standard_input)
     direct labour      standard hours (the route's crew hours per case) × the standard rate (the labour cost over the
                        year ÷ the hours over the year)
     variable overhead  the pool's cost per case over the year
     fixed overhead     the pool's cost for the year ÷ the business plan's planned cases at the plant — the rate as built
   A year with no business plan, or a material it plans no cases of, has no standard. */
MODEL (name plan.standard_cost_pool, kind FULL, grain (material_code, plant_code, fiscal_year, pool_code));
WITH bp AS (
  SELECT fiscal_year::INT AS fiscal_year, version_id AS bp_version FROM dims.ctl_version
  WHERE version_kind = 'business_plan' AND base_version IS NULL
  QUALIFY ROW_NUMBER() OVER (PARTITION BY fiscal_year ORDER BY named_on, version_id) = 1
),
cases AS (SELECT version_id, material_code, period, SUM(cases) AS cases FROM plan.demand_financialised GROUP BY ALL),
bp_cells AS (                                          -- the business plan's own cells in its year, with their cases
  SELECT u.*, b.fiscal_year, c.cases FROM plan.planned_unit_cost_pool u
  JOIN dims.dim_period p ON p.period = u.period
  JOIN bp b ON b.bp_version = u.version_id AND b.fiscal_year = p.fiscal_year::INT
  JOIN cases c ON c.version_id = u.version_id AND c.material_code = u.material_code AND c.period = u.period
  WHERE c.cases > 0
),
lab AS (
  SELECT l.material_code, l.plant_code, b.fiscal_year, SUM(l.crew_hours * c.cases) / NULLIF(SUM(c.cases), 0) AS std_hours,
         SUM(l.labour_cost * c.cases) / NULLIF(SUM(l.crew_hours * c.cases), 0) AS std_rate
  FROM plan.planned_labour l JOIN dims.dim_period p ON p.period = l.period
  JOIN bp b ON b.bp_version = l.version_id AND b.fiscal_year = p.fiscal_year::INT
  JOIN cases c ON c.version_id = l.version_id AND c.material_code = l.material_code AND c.period = l.period
  WHERE c.cases > 0 GROUP BY ALL
),
mat AS (SELECT material_code, plant_code, fiscal_year, pool_code, SUM(std_quantity * std_price) AS per_case FROM plan.standard_input GROUP BY ALL)
SELECT x.material_code, x.plant_code, x.fiscal_year, x.pool_code, x.component, ANY_VALUE(b.bp_version) AS set_on,
       CASE WHEN x.component = 'material' THEN ANY_VALUE(m.per_case)
            WHEN x.component = 'labour' THEN ANY_VALUE(l.std_hours * l.std_rate)
            WHEN x.component = 'fixed_overhead' THEN ANY_VALUE(x.fixed_rate)
            ELSE SUM(x.per_case * x.cases) / NULLIF(SUM(x.cases), 0) END AS std_per_case,
       ANY_VALUE(CASE WHEN x.component = 'labour' THEN l.std_hours END) AS std_hours,
       ANY_VALUE(CASE WHEN x.component = 'labour' THEN l.std_rate END) AS std_rate,
       ANY_VALUE(x.pool_cost) AS fixed_pool_cost, ANY_VALUE(x.denominator) AS fixed_denominator, SUM(x.cases) AS bp_cases
FROM (SELECT *, per_case AS fixed_rate FROM bp_cells) x
JOIN bp b ON b.fiscal_year = x.fiscal_year
LEFT JOIN mat m ON m.material_code = x.material_code AND m.plant_code = x.plant_code AND m.fiscal_year = x.fiscal_year AND m.pool_code = x.pool_code
LEFT JOIN lab l ON l.material_code = x.material_code AND l.plant_code = x.plant_code AND l.fiscal_year = x.fiscal_year
GROUP BY x.material_code, x.plant_code, x.fiscal_year, x.pool_code, x.component
