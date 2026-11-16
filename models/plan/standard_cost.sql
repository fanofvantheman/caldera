/* The standard: a cost per case by version × material × its plant × period, in four components (DEC-20261115-04), each the
   sum of its pools (plan.standard_cost_pool, DEC-20261116-03).
     material           the material pools: the bill of materials at the plant × each input's price in force
     labour             the direct labour pool: the route's crew ÷ its cases an hour × the plant's loaded hourly rate
     variable_overhead  the variable pools' rates at the plant
     fixed_overhead     the fixed pools' cost for the year ÷ the planned cases at the plant, set on the business plan of the
                        period's fiscal year and held on every plan of that year (DEC-20261115-06); a year with no business
                        plan takes the plan's own (caldera #48)
   Which pool a cost is in is declared by the map (plan.cost_pool_map), the driver its check; direct or indirect labour is
   read from the route. Material, labour and variable overhead are each plan's own; only the fixed component is held.
   Under- or over-absorption is plan.standard_absorption, never folded into the unit cost. */
MODEL (name plan.standard_cost, kind FULL, grain (version_id, material_code, period));
WITH pools AS (
  SELECT version_id, material_code, period,
         SUM(CASE WHEN component = 'material' THEN per_case END) AS material_cost,
         SUM(CASE WHEN component = 'variable_overhead' THEN per_case END) AS variable_overhead,
         SUM(CASE WHEN component = 'fixed_overhead' THEN pool_cost END) AS fixed_pool,
         ANY_VALUE(CASE WHEN component = 'fixed_overhead' THEN denominator END) AS denominator,
         ANY_VALUE(CASE WHEN component = 'fixed_overhead' THEN denominator_version END) AS denominator_version,
         BOOL_OR(CASE WHEN component = 'fixed_overhead' THEN fixed_held END) AS fixed_held
  FROM plan.standard_cost_pool GROUP BY ALL
)
SELECT l.version_id, l.material_code, l.plant_code, l.period, p.material_cost, l.crew_hours, l.loaded_rate, l.labour_cost,
       p.variable_overhead, p.fixed_pool, p.denominator, p.denominator_version, COALESCE(p.fixed_held, FALSE) AS fixed_held, p.fixed_pool / NULLIF(p.denominator, 0) AS fixed_overhead,
       COALESCE(p.material_cost, 0) + COALESCE(l.labour_cost, 0) + COALESCE(p.variable_overhead, 0) + COALESCE(p.fixed_pool / NULLIF(p.denominator, 0), 0) AS std_cost,
       p.material_cost IS NOT NULL AND l.labour_cost IS NOT NULL AND p.variable_overhead IS NOT NULL AND p.fixed_pool IS NOT NULL AS complete
FROM plan.standard_labour l LEFT JOIN pools p USING (version_id, material_code, period)
