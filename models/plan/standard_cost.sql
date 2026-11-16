/* The standard cost: one cost per case by material × plant × fiscal year in the four components, the sum of its pools
   (plan.standard_cost_pool), set on the business plan of the year and unchanged through it — the benchmark every plan of
   the year is read against (DEC-20261116-02 points 1–3). The planned unit cost is each plan's own roll-up, by period
   (plan.planned_unit_cost); the difference is plan.cost_variance. */
MODEL (name plan.standard_cost, kind FULL, grain (material_code, plant_code, fiscal_year));
SELECT material_code, plant_code, fiscal_year, ANY_VALUE(set_on) AS set_on,
       SUM(CASE WHEN component = 'material' THEN std_per_case END) AS std_material,
       SUM(CASE WHEN component = 'labour' THEN std_per_case END) AS std_labour,
       ANY_VALUE(CASE WHEN component = 'labour' THEN std_hours END) AS std_hours,
       ANY_VALUE(CASE WHEN component = 'labour' THEN std_rate END) AS std_rate,
       SUM(CASE WHEN component = 'variable_overhead' THEN std_per_case END) AS std_variable,
       SUM(CASE WHEN component = 'fixed_overhead' THEN std_per_case END) AS std_fixed,
       SUM(CASE WHEN component = 'fixed_overhead' THEN fixed_pool_cost END) AS fixed_pool_cost,
       ANY_VALUE(CASE WHEN component = 'fixed_overhead' THEN fixed_denominator END) AS fixed_denominator,
       SUM(std_per_case) AS std_cost,
       MAX(bp_cases) AS bp_cases
FROM plan.standard_cost_pool GROUP BY material_code, plant_code, fiscal_year
