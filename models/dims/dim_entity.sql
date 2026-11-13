/* The legal entities whose ledgers the plan's costs come from. Each keeps its own ledger and its own cost centres; the
   plan reads them through one normalised set (dims.reg_cost_centre_map). A dimension of the cost lines so each entity
   reads alone and together — never a consolidation: intercompany charges between them are left out. */
MODEL (name dims.dim_entity, kind FULL, grain (entity_code));
SELECT entity_code::TEXT AS entity_code, entity_name::TEXT AS entity_name, ledger::TEXT AS ledger, state::TEXT AS state,
       joined_period::TEXT AS joined_period, joined_on::DATE AS joined_on, note::TEXT AS note
FROM bronze.dim_entity
