/* The unconstrained demand plan: the stack summed, by version at the storage grain. The signal; the supply constraint
   is a separate plan read against it, never a layer here. */
MODEL (name plan.unconstrained_demand, kind FULL, grain (version_id, material_code, ship_to_code, week_id));
SELECT version_id, material_code, standard_material, ship_to_code, account_code, week_id, period, fiscal_year,
       SUM(cases) AS cases, SUM(tonnes) AS tonnes, SUM(CASE WHEN layer_no = 1 THEN cases END) AS baseline_cases,
       SUM(CASE WHEN layer_no > 1 THEN cases END) AS layered_cases
FROM plan.demand_stack
GROUP BY ALL
