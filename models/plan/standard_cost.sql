/* The standard: a cost per case by version × material × its plant × period, in four components (DEC-20261115-04), each
   read from the model that already holds it.
     material           the bill of materials at the plant × each input's price in force (price × index ÷ 100); the
                        utility in the bill is the schedule's energy, variable overhead, and is not priced here
     labour             the route's crew ÷ its cases an hour × the loaded hourly rate of the plant's production halls'
                        positions in the period (the labour model: wages and on-costs over paid hours)
     variable_overhead  the plant's factory cost centres' schedule lines driven by cases made there: the line's own rate
     fixed_overhead     the rate set on the business plan of the period's fiscal year and held on every plan of that year
                        (DEC-20261115-06): its factory cost centres' other lines over its year — indirect labour (every
                        position but the crews), depreciation, production leases, the rest — ÷ its cases at the plant for
                        the year. A period of a year with no business plan takes the plan's own: its fixed lines over the
                        schedule's planned periods ÷ its own cases at the plant over the same periods (caldera #48)
   Variable or fixed is read from the line's driver; direct or indirect labour from the route — no second classification.
   Material, labour and variable overhead are each plan's own; only the fixed component is held. Under- or
   over-absorption is plan.standard_absorption, never folded into the unit cost. */
MODEL (name plan.standard_cost, kind FULL, grain (version_id, material_code, period));
WITH versions AS (SELECT version_id, from_period, plan_through FROM dims.ctl_version WHERE version_kind <> 'actual' AND from_period IS NOT NULL),
route AS (SELECT material_code, plant_code, line_code, rate_cases_per_hour FROM dims.ref_route WHERE is_primary),
mats AS (SELECT DISTINCT d.version_id, d.material_code, d.period FROM plan.demand_financialised d JOIN versions v USING (version_id)
         WHERE d.period > v.from_period AND d.period <= v.plan_through),
idx AS (SELECT version_id, period, assumption_code, value FROM plan.assumption_in_force),
price AS (                                            -- each input's price in each period of each version
  SELECT m.version_id, m.period, p.material_code AS input, p.price * COALESCE(i.value, 100) / 100 AS price
  FROM (SELECT DISTINCT version_id, period FROM mats) m CROSS JOIN dims.reg_input_price p
  LEFT JOIN idx i ON i.version_id = m.version_id AND i.period = m.period AND i.assumption_code = p.index_code
  WHERE p.price_from <= m.period
  QUALIFY ROW_NUMBER() OVER (PARTITION BY m.version_id, m.period, p.material_code ORDER BY p.price_from DESC) = 1
),
material AS (
  SELECT m.version_id, m.material_code, m.period, SUM(b.quantity_per_case * pr.price) AS material_cost, COUNT(*) AS n_inputs
  FROM mats m JOIN route r USING (material_code)
  JOIN dims.ref_bom b ON b.parent_material = m.material_code AND b.plant_code = r.plant_code
  JOIN dims.dim_input_material im ON im.material_code = b.component_material AND im.material_type <> 'utility'
  JOIN price pr ON pr.version_id = m.version_id AND pr.period = m.period AND pr.input = b.component_material
  GROUP BY ALL
),
rate AS (                                             -- the loaded hourly rate of each plant's production halls, by period
  SELECT l.version_id, c.plant_code, l.period, SUM(l.wages + l.on_costs) / NULLIF(SUM(l.fte * 38 * p.weeks_in_period), 0) AS loaded_rate
  FROM plan.labour_line l JOIN plan.ref_cost_centre_plant c ON c.entity_code = l.entity_code AND c.cost_centre_code = l.cost_centre_code AND c.role = 'production'
  JOIN dims.dim_period p ON p.period = l.period WHERE l.model = 'role' GROUP BY ALL
),
labour AS (
  SELECT m.version_id, m.material_code, m.period, r.plant_code, cr.crew / NULLIF(r.rate_cases_per_hour, 0) AS crew_hours, rt.loaded_rate,
         cr.crew / NULLIF(r.rate_cases_per_hour, 0) * rt.loaded_rate AS labour_cost
  FROM mats m JOIN route r USING (material_code) LEFT JOIN dims.ref_line_crew cr ON cr.line_code = r.line_code
  LEFT JOIN rate rt ON rt.version_id = m.version_id AND rt.plant_code = r.plant_code AND rt.period = m.period
),
sched AS (                                            -- the plant's factory lines, each variable or fixed by its driver
  SELECT s.version_id, c.plant_code, s.period, s.driver = 'cases_made_' || LOWER(c.plant_code) AS variable, s.rate, s.amount,
         s.entity_code, s.cost_centre_code, s.account_code
  FROM plan.opex_schedule s JOIN plan.ref_cost_centre_plant c ON c.entity_code = s.entity_code AND c.cost_centre_code = s.cost_centre_code
),
var_rate AS (                                         -- each line's own rate, once: a rate is the line's, for every period
  SELECT version_id, plant_code, SUM(rate) AS variable_overhead
  FROM (SELECT DISTINCT version_id, plant_code, entity_code, cost_centre_code, account_code, rate FROM sched WHERE variable) GROUP BY ALL
),
cases AS (SELECT d.version_id, r.plant_code, d.period, SUM(d.cases) AS cases FROM plan.demand_financialised d JOIN route r USING (material_code) GROUP BY ALL),
direct AS (                                           -- the direct labour the plan's cases need, by plant and period
  SELECT d.version_id, l.plant_code, d.period, SUM(d.cases * l.labour_cost) AS direct_labour
  FROM (SELECT version_id, material_code, period, SUM(cases) cases FROM plan.demand_financialised GROUP BY ALL) d
  JOIN labour l USING (version_id, material_code, period) GROUP BY ALL
),
pool AS (                                             -- fixed overhead over the schedule's planned periods: every fixed line, less the crews,
  SELECT f.version_id, f.plant_code, SUM(f.amount) - COALESCE(MAX(dl.direct_labour), 0) AS fixed_pool, COUNT(DISTINCT f.period) AS n_periods,
         MAX(oc.cases) AS own_cases                   -- and the plan's own cases at the plant over the same periods
  FROM (SELECT version_id, plant_code, SUM(amount) amount, period FROM sched WHERE NOT variable GROUP BY ALL) f
  LEFT JOIN (SELECT dd.version_id, dd.plant_code, SUM(dd.direct_labour) direct_labour FROM direct dd
             WHERE (dd.version_id, dd.period) IN (SELECT version_id, period FROM sched) GROUP BY ALL) dl USING (version_id, plant_code)
  LEFT JOIN (SELECT c.version_id, c.plant_code, SUM(c.cases) cases FROM cases c
             WHERE (c.version_id, c.period) IN (SELECT version_id, period FROM sched) GROUP BY ALL) oc USING (version_id, plant_code)
  GROUP BY ALL
),
bp AS (                                               -- the business plan of each fiscal year: the one named before the build, not a copy of it
  SELECT fiscal_year::INT AS fiscal_year, version_id AS bp_version FROM dims.ctl_version
  WHERE version_kind = 'business_plan' AND base_version IS NULL
  QUALIFY ROW_NUMBER() OVER (PARTITION BY fiscal_year ORDER BY named_on, version_id) = 1
),
fixed_rate AS (                                       -- the rate each period takes: set on its year's business plan, held; else the plan's own
  SELECT m.version_id, l.plant_code, m.period,
         COALESCE(bpp.fixed_pool, po.fixed_pool) AS fixed_pool,
         CASE WHEN bpp.fixed_pool IS NOT NULL THEN bpp.own_cases ELSE po.own_cases END AS denominator,
         CASE WHEN bpp.fixed_pool IS NOT NULL THEN b.bp_version ELSE m.version_id END AS denominator_version,
         bpp.fixed_pool IS NOT NULL AS fixed_held
  FROM (SELECT DISTINCT version_id, material_code, period FROM mats) m JOIN labour l USING (version_id, material_code, period)
  JOIN dims.dim_period p ON p.period = m.period
  LEFT JOIN bp b ON b.fiscal_year = p.fiscal_year::INT
  LEFT JOIN pool bpp ON bpp.version_id = b.bp_version AND bpp.plant_code = l.plant_code
  LEFT JOIN pool po ON po.version_id = m.version_id AND po.plant_code = l.plant_code
  GROUP BY ALL
)
SELECT m.version_id, m.material_code, l.plant_code, m.period, mt.material_cost, l.crew_hours, l.loaded_rate, l.labour_cost,
       vr.variable_overhead, fr.fixed_pool, fr.denominator, fr.denominator_version, fr.fixed_held, fr.fixed_pool / NULLIF(fr.denominator, 0) AS fixed_overhead,
       COALESCE(mt.material_cost, 0) + COALESCE(l.labour_cost, 0) + COALESCE(vr.variable_overhead, 0) + COALESCE(fr.fixed_pool / NULLIF(fr.denominator, 0), 0) AS std_cost,
       mt.material_cost IS NOT NULL AND l.labour_cost IS NOT NULL AND vr.variable_overhead IS NOT NULL AND fr.fixed_pool IS NOT NULL AS complete
FROM mats m JOIN labour l USING (version_id, material_code, period)
LEFT JOIN material mt USING (version_id, material_code, period)
LEFT JOIN var_rate vr ON vr.version_id = m.version_id AND vr.plant_code = l.plant_code
LEFT JOIN fixed_rate fr ON fr.version_id = m.version_id AND fr.plant_code = l.plant_code AND fr.period = m.period
