/* Under- or over-absorption, a line of its own (DEC-20261115-04 point 3): each plant's fixed overhead in a planned period
   against what the standard absorbs on the version's cases there — fixed overhead per case × cases. Positive is
   under-absorbed: fixed cost the cases do not carry. Never folded into the unit cost. */
MODEL (name plan.standard_absorption, kind FULL, grain (version_id, plant_code, period));
WITH route AS (SELECT material_code, plant_code FROM dims.ref_route WHERE is_primary),
fixed AS (
  SELECT s.version_id, c.plant_code, s.period, SUM(s.amount) AS fixed_lines
  FROM plan.opex_schedule s JOIN plan.ref_cost_centre_plant c ON c.entity_code = s.entity_code AND c.cost_centre_code = s.cost_centre_code
  WHERE s.driver <> 'cases_made_' || LOWER(c.plant_code) GROUP BY ALL
),
absorbed AS (
  SELECT d.version_id, s.plant_code, d.period, SUM(d.cases) AS cases, SUM(d.cases * s.fixed_overhead) AS absorbed, SUM(d.cases * s.labour_cost) AS direct_labour,
         ANY_VALUE(s.fixed_overhead) AS fixed_overhead
  FROM (SELECT version_id, material_code, period, SUM(cases) cases FROM plan.demand_financialised GROUP BY ALL) d
  JOIN plan.standard_cost s USING (version_id, material_code, period) GROUP BY ALL
)
SELECT f.version_id, f.plant_code, f.period, f.fixed_lines, a.direct_labour, f.fixed_lines - COALESCE(a.direct_labour, 0) AS fixed_overhead_incurred,
       a.cases, a.fixed_overhead AS fixed_per_case, a.absorbed, f.fixed_lines - COALESCE(a.direct_labour, 0) - COALESCE(a.absorbed, 0) AS under_absorbed
FROM fixed f LEFT JOIN absorbed a USING (version_id, plant_code, period)
