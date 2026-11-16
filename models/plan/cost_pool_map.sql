/* The map in force: every rule of cost centre × account onto a pool, as set and changed on the cost pools page — the
   latest act per key stands, and a 'remove' takes the key out. A rule may leave the entity, the cost centre or the
   account blank (any). Specificity, most specific first: cost centre × account, then cost centre, then account; within a
   tier a rule naming the entity beats one that does not. */
MODEL (name plan.cost_pool_map, kind FULL, grain (entity_code, cost_centre_code, account_code));
WITH acts AS (
  SELECT COALESCE(entity_code, '') AS entity_code, COALESCE(cost_centre_code, '') AS cost_centre_code, COALESCE(account_code, '') AS account_code,
         action, pool_code, set_by, set_at, reason, act_id, source_file, file_row_number
  FROM bronze.reg_cost_pool_rule
)
SELECT a.entity_code, a.cost_centre_code, a.account_code, a.pool_code, a.set_by, a.set_at, a.reason, a.act_id,
       CASE WHEN a.cost_centre_code <> '' AND a.account_code <> '' THEN 1 WHEN a.cost_centre_code <> '' THEN 2 ELSE 3 END AS tier,
       p.pool_code IS NOT NULL AS pool_known
FROM acts a LEFT JOIN dims.ref_cost_pool p ON p.pool_code = a.pool_code
QUALIFY ROW_NUMBER() OVER (PARTITION BY a.entity_code, a.cost_centre_code, a.account_code ORDER BY a.set_at::TIMESTAMP DESC, a.source_file DESC, a.file_row_number DESC) = 1
    AND a.action = 'set'
