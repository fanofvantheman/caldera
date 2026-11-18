/* The planned unit cost (DEC-20261116-02 point 1: each plan's roll-up, by period — the standard is plan.standard_cost): a cost per case by version × material × its plant × period, in four components (DEC-20261115-04), each the
   sum of its pools (plan.planned_unit_cost_pool, DEC-20261116-03).
     material           the material pools: the bill of materials at the plant × each input's price in force
     labour             the direct labour pool: the route's crew ÷ its cases an hour × the plant's loaded hourly rate
     variable_overhead  the variable pools' rates at the plant
     fixed_overhead     the fixed pools' cost for the year ÷ the planned cases at the plant, set on the business plan of the
                        period's fiscal year and held on every plan of that year (DEC-20261115-06); a year with no business
                        plan takes the plan's own (caldera #48)
   Which pool a cost is in is declared by the map (plan.cost_pool_map), the driver its check; direct or indirect labour is
   read from the route. Material, labour and variable overhead are each plan's own; only the fixed component is held.
   Under- or over-absorption is plan.standard_absorption, never folded into the unit cost.
   A component typed where its drivers are missing (plan.unit_cost_act, DEC-20261116-02 point 7) replaces the
   driver-based figure and is marked (typed_*); the driver-based figure is kept beside it (*_driven). The pools beneath
   stay the drivers' — a typed figure has none. */
MODEL (name plan.planned_unit_cost, kind FULL, grain (version_id, material_code, period));
WITH pools AS (
  SELECT version_id, material_code, period,
         SUM(CASE WHEN component = 'material' THEN per_case END) AS material_cost,
         SUM(CASE WHEN component = 'variable_overhead' THEN per_case END) AS variable_overhead,
         SUM(CASE WHEN component = 'fixed_overhead' THEN pool_cost END) AS fixed_pool,
         ANY_VALUE(CASE WHEN component = 'fixed_overhead' THEN denominator END) AS denominator,
         ANY_VALUE(CASE WHEN component = 'fixed_overhead' THEN denominator_version END) AS denominator_version,
         BOOL_OR(CASE WHEN component = 'fixed_overhead' THEN fixed_held END) AS fixed_held
  FROM plan.planned_unit_cost_pool GROUP BY ALL
),
typed AS (
  SELECT version_id, material_code, plant_code, period,
         MAX(CASE WHEN component = 'material' THEN per_case END) AS t_material,
         MAX(CASE WHEN component = 'labour' THEN per_case END) AS t_labour,
         MAX(CASE WHEN component = 'variable_overhead' THEN per_case END) AS t_variable,
         MAX(CASE WHEN component = 'fixed_overhead' THEN per_case END) AS t_fixed
  FROM plan.unit_cost_act GROUP BY ALL
),
driven AS (
  SELECT l.version_id, l.material_code, l.plant_code, l.period, p.material_cost, l.crew_hours, l.loaded_rate, l.labour_cost,
         p.variable_overhead, p.fixed_pool, p.denominator, p.denominator_version, COALESCE(p.fixed_held, FALSE) AS fixed_held,
         p.fixed_pool / NULLIF(p.denominator, 0) AS fixed_overhead
  FROM plan.planned_labour l LEFT JOIN pools p USING (version_id, material_code, period)
)
SELECT d.version_id, d.material_code, d.plant_code, d.period,
       COALESCE(t.t_material, d.material_cost) AS material_cost, d.crew_hours, d.loaded_rate,
       COALESCE(t.t_labour, d.labour_cost) AS labour_cost,
       COALESCE(t.t_variable, d.variable_overhead) AS variable_overhead, d.fixed_pool, d.denominator, d.denominator_version, d.fixed_held,
       COALESCE(t.t_fixed, d.fixed_overhead) AS fixed_overhead,
       COALESCE(COALESCE(t.t_material, d.material_cost), 0) + COALESCE(COALESCE(t.t_labour, d.labour_cost), 0)
         + COALESCE(COALESCE(t.t_variable, d.variable_overhead), 0) + COALESCE(COALESCE(t.t_fixed, d.fixed_overhead), 0) AS unit_cost,
       COALESCE(t.t_material, d.material_cost) IS NOT NULL AND COALESCE(t.t_labour, d.labour_cost) IS NOT NULL
         AND COALESCE(t.t_variable, d.variable_overhead) IS NOT NULL AND (t.t_fixed IS NOT NULL OR d.fixed_pool IS NOT NULL) AS complete,
       t.t_material IS NOT NULL AS typed_material, t.t_labour IS NOT NULL AS typed_labour,
       t.t_variable IS NOT NULL AS typed_variable, t.t_fixed IS NOT NULL AS typed_fixed,
       d.material_cost AS material_driven, d.labour_cost AS labour_driven, d.variable_overhead AS variable_driven, d.fixed_overhead AS fixed_driven
FROM driven d LEFT JOIN typed t ON t.version_id = d.version_id AND t.material_code = d.material_code AND t.plant_code = d.plant_code AND t.period = d.period
