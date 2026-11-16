/* Every cell of the plan's cost centre × account that carries a cost — in any plan's schedule or in the ledgers' actuals
   read through the plan's cost centres — resolved to one pool by the most specific rule in force (plan.cost_pool_map), or
   to none: a cell with no rule is not silently out, it is the worklist plan.worklist_cost_pool_unmapped. The plant is the
   cost centre's (plan.ref_cost_centre_plant). The pool declares the component; the driver is its check: a variable pool
   whose schedule line is not driven by cases made at the plant, or a fixed pool whose line is, is marked (DEC-20261116-03
   points 4, 5). */
MODEL (name plan.cost_pool_cell, kind FULL, grain (entity_code, cost_centre_code, account_code));
WITH cells AS (
  SELECT entity_code, cost_centre_code, account_code FROM plan.opex_schedule
  UNION SELECT entity_code, cost_centre_code, account_code FROM plan.cost_actual WHERE state = 'mapped'
),
resolved AS (
  SELECT c.*, m.pool_code, m.tier, m.entity_code <> '' AS rule_names_entity, m.act_id,
         m.cost_centre_code AS rule_cost_centre, m.account_code AS rule_account
  FROM cells c LEFT JOIN plan.cost_pool_map m
    ON (m.entity_code = '' OR m.entity_code = c.entity_code)
   AND (m.cost_centre_code = '' OR m.cost_centre_code = c.cost_centre_code)
   AND (m.account_code = '' OR m.account_code = c.account_code)
   AND (m.cost_centre_code <> '' OR m.account_code <> '')
  QUALIFY ROW_NUMBER() OVER (PARTITION BY c.entity_code, c.cost_centre_code, c.account_code
                             ORDER BY m.tier NULLS LAST, (m.entity_code <> '') DESC) = 1
),
drivers AS (
  SELECT entity_code, cost_centre_code, account_code, STRING_AGG(DISTINCT driver, ', ' ORDER BY driver) AS drivers
  FROM plan.opex_schedule GROUP BY ALL
)
SELECT r.entity_code, r.cost_centre_code, r.account_code, r.pool_code, p.pool_name, p.component, r.tier, r.act_id,
       r.rule_cost_centre, r.rule_account, r.rule_names_entity,
       cp.plant_code, cp.role, d.drivers,
       r.pool_code IS NULL AS unmapped,
       p.component IS NOT NULL AND cp.plant_code IS NULL AS no_plant,
       CASE WHEN p.component = 'variable_overhead' THEN d.drivers IS NOT NULL AND d.drivers IS DISTINCT FROM 'cases_made_' || LOWER(cp.plant_code)
            WHEN p.component = 'fixed_overhead' THEN COALESCE(d.drivers LIKE '%cases_made_' || LOWER(cp.plant_code) || '%', FALSE)
            ELSE FALSE END AS driver_disagrees
FROM resolved r
LEFT JOIN dims.ref_cost_pool p ON p.pool_code = r.pool_code
LEFT JOIN plan.ref_cost_centre_plant cp ON cp.entity_code = r.entity_code AND cp.cost_centre_code = r.cost_centre_code
LEFT JOIN drivers d ON d.entity_code = r.entity_code AND d.cost_centre_code = r.cost_centre_code AND d.account_code = r.account_code
