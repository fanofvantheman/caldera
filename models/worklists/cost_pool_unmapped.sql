/* The map's queue: a cell of the plan's cost centre × account that carries a cost and no rule reaches — it is in no cost
   pool and not declared out of cost of goods, so the cost of a case cannot say whether it holds it. Decided by setting a
   rule on the cost pools page (DEC-20261116-03 point 4); routed to whoever keeps the map. */
MODEL (name plan.worklist_cost_pool_unmapped, kind FULL, grain (entity_code, cost_centre_code, account_code));
SELECT c.entity_code, c.cost_centre_code, c.account_code, cc.cost_centre_name, a.account_name, c.drivers,
       (SELECT STRING_AGG(DISTINCT x.principal, ', ' ORDER BY x.principal) FROM dims.effective_entitlements x WHERE x.action = 'register.cost_centre_map.maintain') AS whose,
       c.cost_centre_code || ' ' || cc.cost_centre_name || ' × ' || c.account_code || ' ' || a.account_name || ' (' || c.entity_code || ') is in no cost pool' AS item
FROM plan.cost_pool_cell c
LEFT JOIN plan.planning_cost_centre cc ON cc.cost_centre_code = c.cost_centre_code
LEFT JOIN dims.dim_gl_account a ON a.account_code = c.account_code
WHERE c.unmapped
