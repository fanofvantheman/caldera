/* The standard's material, input by input: material × plant × fiscal year × input, set on the business plan of the year
   (DEC-20261116-02 point 2) — the standard usage, the bill's quantity per case, and the standard price, the input's cost
   over the year ÷ its quantity over the year on the business plan's own cases. It holds because the business plan is
   closed. A year with no business plan, or a material it plans no cases of, has no standard. */
MODEL (name plan.standard_input, kind FULL, grain (material_code, plant_code, fiscal_year, input_code));
WITH bp AS (
  SELECT fiscal_year::INT AS fiscal_year, version_id AS bp_version FROM dims.ctl_version
  WHERE version_kind = 'business_plan' AND base_version IS NULL
  QUALIFY ROW_NUMBER() OVER (PARTITION BY fiscal_year ORDER BY named_on, version_id) = 1
),
cases AS (SELECT version_id, material_code, period, SUM(cases) AS cases FROM plan.demand_financialised GROUP BY ALL)
SELECT i.material_code, i.plant_code, b.fiscal_year, i.input_code, ANY_VALUE(i.pool_code) AS pool_code, b.bp_version AS set_on,
       SUM(i.quantity * c.cases) / NULLIF(SUM(c.cases), 0) AS std_quantity,
       SUM(i.per_case * c.cases) / NULLIF(SUM(i.quantity * c.cases), 0) AS std_price,
       SUM(c.cases) AS bp_cases
FROM plan.planned_material_input i
JOIN dims.dim_period p ON p.period = i.period
JOIN bp b ON b.bp_version = i.version_id AND b.fiscal_year = p.fiscal_year::INT
JOIN cases c ON c.version_id = i.version_id AND c.material_code = i.material_code AND c.period = i.period
WHERE c.cases > 0
GROUP BY i.material_code, i.plant_code, b.fiscal_year, i.input_code, b.bp_version
