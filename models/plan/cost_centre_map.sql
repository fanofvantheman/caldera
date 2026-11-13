/* The mapping in force: the register as loaded, and every decision on the ledgers' queue (door GL in plan.door_act) — map
   to one of ours, open a new one (a provisional cost centre of ours carrying the ledger centre's code and name), or leave
   out with a reason. A decision applies from the entity's first period. One row per entity × ledger cost centre × span. */
MODEL (name plan.cost_centre_map, kind FULL, grain (entity_code, ledger_cost_centre, valid_from), audits (cost_centre_map_one_target));
WITH decided AS (
  SELECT a.scope_code AS entity_code, a.item_code AS ledger_cost_centre,
         CASE a.resolution WHEN 'map_to' THEN a.target_code WHEN 'open_new' THEN a.item_code END AS cost_centre_code,
         e.joined_on AS valid_from, NULL::DATE AS valid_to, a.acted_by AS mapped_by, a.reason AS note,
         a.resolution AS how, a.act_id
  FROM plan.door_act a JOIN dims.dim_entity e ON e.entity_code = a.scope_code
  WHERE a.door = 'GL' AND a.kind = 'unmapped_cost_centre' AND a.in_force
)
SELECT m.*, m.cost_centre_code IS NULL OR m.how = 'open_new' OR c.cost_centre_code IS NOT NULL AS target_known
FROM (
  SELECT entity_code, ledger_cost_centre, cost_centre_code, valid_from, valid_to, mapped_by, note, 'loaded' AS how, NULL::TEXT AS act_id
  FROM dims.reg_cost_centre_map r
  WHERE NOT EXISTS (SELECT 1 FROM decided d WHERE d.entity_code = r.entity_code AND d.ledger_cost_centre = r.ledger_cost_centre)
  UNION ALL
  SELECT entity_code, ledger_cost_centre, cost_centre_code, valid_from, valid_to, mapped_by, note, how, act_id FROM decided
) m LEFT JOIN bronze.dim_cost_centre c ON c.cost_centre_code = m.cost_centre_code     -- as loaded: current even before the dims are restated
