/* Direct labour per case by version × material × period at the material's primary plant: the route's crew ÷ its cases an
   hour × the loaded hourly rate of the plant's production halls' positions in the period (the labour model: wages and
   on-costs over paid hours). Read by the direct labour pool and, through the cases, by what indirect labour is left
   (DEC-20261115-04 point 2: direct or indirect is read from the route). */
MODEL (name plan.planned_labour, kind FULL, grain (version_id, material_code, period));
WITH versions AS (SELECT version_id, from_period, plan_through FROM dims.ctl_version WHERE version_kind <> 'actual' AND from_period IS NOT NULL),
route AS (SELECT material_code, plant_code, line_code, rate_cases_per_hour FROM dims.ref_route WHERE is_primary),
mats AS (SELECT DISTINCT d.version_id, d.material_code, d.period FROM plan.demand_financialised d JOIN versions v USING (version_id)
         WHERE d.period > v.from_period AND d.period <= v.plan_through),
rate AS (
  SELECT l.version_id, c.plant_code, l.period, SUM(l.wages + l.on_costs) / NULLIF(SUM(l.fte * 38 * p.weeks_in_period), 0) AS loaded_rate
  FROM plan.labour_line l JOIN plan.ref_cost_centre_plant c ON c.entity_code = l.entity_code AND c.cost_centre_code = l.cost_centre_code AND c.role = 'production'
  JOIN dims.dim_period p ON p.period = l.period WHERE l.model = 'role' GROUP BY ALL
)
SELECT m.version_id, m.material_code, m.period, r.plant_code, cr.crew / NULLIF(r.rate_cases_per_hour, 0) AS crew_hours, rt.loaded_rate,
       cr.crew / NULLIF(r.rate_cases_per_hour, 0) * rt.loaded_rate AS labour_cost
FROM mats m JOIN route r USING (material_code) LEFT JOIN dims.ref_line_crew cr ON cr.line_code = r.line_code
LEFT JOIN rate rt ON rt.version_id = m.version_id AND rt.plant_code = r.plant_code AND rt.period = m.period
