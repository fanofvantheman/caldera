/* Under- or over-absorption, a line of its own (DEC-20261115-04 point 3, DEC-20261115-06 point 3): each plant's fixed
   overhead in a planned period against what the standard absorbs on the version's cases there — the period's fixed
   overhead per case × cases. Positive is under-absorbed: fixed cost the cases do not carry. Never folded into the unit
   cost.
   Where the rate is held from the business plan of the period's year, the amount splits in two (caldera #48):
     cost_moved    the plan's fixed overhead incurred less the business plan's in the same period — the cost moved
     volume_moved  the business plan's incurred less what the rate absorbs on the plan's cases — the volume moved
   They sum to the amount not absorbed. On the business plan itself cost moved is nil. A period whose rate is the plan's
   own (no business plan for its year) is not split. */
MODEL (name plan.standard_absorption, kind FULL, grain (version_id, plant_code, period));
WITH fixed AS (
  SELECT s.version_id, c.plant_code, s.period, SUM(s.amount) AS fixed_lines
  FROM plan.opex_schedule s JOIN plan.ref_cost_centre_plant c ON c.entity_code = s.entity_code AND c.cost_centre_code = s.cost_centre_code
  WHERE s.driver <> 'cases_made_' || LOWER(c.plant_code) GROUP BY ALL
),
absorbed AS (
  SELECT d.version_id, s.plant_code, d.period, SUM(d.cases) AS cases, SUM(d.cases * s.fixed_overhead) AS absorbed, SUM(d.cases * s.labour_cost) AS direct_labour,
         ANY_VALUE(s.fixed_overhead) AS fixed_overhead, ANY_VALUE(s.denominator_version) AS rate_version, BOOL_AND(s.fixed_held) AS fixed_held
  FROM (SELECT version_id, material_code, period, SUM(cases) cases FROM plan.demand_financialised GROUP BY ALL) d
  JOIN plan.standard_cost s USING (version_id, material_code, period) GROUP BY ALL
),
incurred AS (
  SELECT f.version_id, f.plant_code, f.period, f.fixed_lines, a.direct_labour, f.fixed_lines - COALESCE(a.direct_labour, 0) AS fixed_overhead_incurred,
         a.cases, a.fixed_overhead AS fixed_per_case, a.absorbed, a.rate_version, COALESCE(a.fixed_held, FALSE) AS fixed_held
  FROM fixed f LEFT JOIN absorbed a USING (version_id, plant_code, period)
)
SELECT i.version_id, i.plant_code, i.period, i.fixed_lines, i.direct_labour, i.fixed_overhead_incurred, i.cases, i.fixed_per_case, i.absorbed,
       i.fixed_overhead_incurred - COALESCE(i.absorbed, 0) AS under_absorbed,
       i.rate_version, i.fixed_held, b.fixed_overhead_incurred AS rate_version_incurred,
       CASE WHEN i.fixed_held THEN i.fixed_overhead_incurred - b.fixed_overhead_incurred END AS cost_moved,
       CASE WHEN i.fixed_held THEN b.fixed_overhead_incurred - COALESCE(i.absorbed, 0) END AS volume_moved
FROM incurred i
LEFT JOIN incurred b ON i.fixed_held AND b.version_id = i.rate_version AND b.plant_code = i.plant_code AND b.period = i.period
