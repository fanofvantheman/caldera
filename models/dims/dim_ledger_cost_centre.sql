/* Each entity's own cost centres, as its ledger has them — theirs, never planned on; visible beneath the plan's own. */
MODEL (name dims.dim_ledger_cost_centre, kind FULL, grain (entity_code, ledger_cost_centre));
SELECT l.entity_code::TEXT AS entity_code, l.ledger_cost_centre::TEXT AS ledger_cost_centre, l.ledger_name::TEXT AS ledger_name,
       e.entity_code IS NOT NULL AS entity_known
FROM bronze.dim_ledger_cost_centre l LEFT JOIN bronze.dim_entity e ON e.entity_code = l.entity_code
