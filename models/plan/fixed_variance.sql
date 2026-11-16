/* Fixed overhead against the standard, by version × plant × fixed pool × period (DEC-20261116-02 point 5,
   DEC-20261116-03 point 8): a plant's money, not a case's.
     spending  the plan's pool cost in the period less the business plan's in the same period
     volume    the business plan's pool cost less what the standard rate absorbs on the plan's cases at the plant
   Summed over the pools they are plan.standard_absorption's cost moved and volume moved. Only where the rate is held from
   the business plan of the period's year; on the business plan itself spending is nil. */
MODEL (name plan.fixed_variance, kind FULL, grain (version_id, plant_code, pool_code, period));
WITH rate AS (                                         -- the standard rate per case of each fixed pool, as the plan holds it
  SELECT DISTINCT version_id, plant_code, period, pool_code, per_case, denominator_version
  FROM plan.planned_unit_cost_pool WHERE component = 'fixed_overhead' AND fixed_held
),
route AS (SELECT material_code, plant_code FROM dims.ref_route WHERE is_primary),
cases AS (SELECT d.version_id, r.plant_code, d.period, SUM(d.cases) AS cases FROM plan.demand_financialised d JOIN route r USING (material_code) GROUP BY ALL)
SELECT p.version_id, p.plant_code, p.pool_code, p.period, r.denominator_version AS set_on, p.amount AS incurred, b.amount AS budget_incurred,
       r.per_case AS std_rate, c.cases, r.per_case * c.cases AS absorbed,
       p.amount - b.amount AS spending, b.amount - r.per_case * COALESCE(c.cases, 0) AS volume
FROM plan.cost_pool_rate p
JOIN rate r ON r.version_id = p.version_id AND r.plant_code = p.plant_code AND r.pool_code = p.pool_code AND r.period = p.period
LEFT JOIN plan.cost_pool_rate b ON b.version_id = r.denominator_version AND b.plant_code = p.plant_code AND b.pool_code = p.pool_code AND b.period = p.period
LEFT JOIN cases c ON c.version_id = p.version_id AND c.plant_code = p.plant_code AND c.period = p.period
WHERE p.component = 'fixed_overhead'
