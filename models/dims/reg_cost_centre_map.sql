/* The mapping as loaded: entity × ledger cost centre → the plan's cost centre, effective-dated. Many ledger cost centres
   to one of ours, never one to many. A ledger cost centre with no row here is an item on the ledgers' queue
   (plan.worklist_cost_centre_unmapped); what a person decides there is read with this by plan.cost_centre_map. */
MODEL (name dims.reg_cost_centre_map, kind FULL, grain (entity_code, ledger_cost_centre, valid_from));
SELECT m.entity_code::TEXT AS entity_code, m.ledger_cost_centre::TEXT AS ledger_cost_centre, m.cost_centre_code::TEXT AS cost_centre_code,
       m.valid_from::DATE AS valid_from, NULLIF(m.valid_to::TEXT, '')::DATE AS valid_to, m.mapped_by::TEXT AS mapped_by, NULLIF(m.note::TEXT, '') AS note,
       c.cost_centre_code IS NOT NULL AS target_known
FROM bronze.reg_cost_centre_map m LEFT JOIN bronze.dim_cost_centre c ON c.cost_centre_code = m.cost_centre_code
