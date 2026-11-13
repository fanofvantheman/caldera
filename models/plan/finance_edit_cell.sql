/* What each of Finance's figures wrote at the grain when it was typed: one row per account × material × period it
   reached, the value it left there and the demand plan at that cell then. These stand — plan.finance_plan puts them in
   the order typed, so a later figure overwrites the cells it reaches. A cell stands while the figure it came from is in
   force; a released or refused figure takes its cells with it. A figure saved before spreads were recorded has none
   here and is spread by the run. */
MODEL (name plan.finance_edit_cell, kind FULL, grain (edit_id));
SELECT c.edit_id::TEXT AS edit_id, c.typed::TEXT AS typed, e.version_id, c.scope_customer::TEXT AS account_code,
       c.scope_material::TEXT AS material_code, e.period, e.measure, c.value::DOUBLE AS value, c.source_at_entry::DOUBLE AS source_at_entry,
       e.entered_on, e.save_id
FROM bronze.reg_finance_overlay c
JOIN plan.finance_edit e ON e.edit_id = c.typed AND e.state = 'in_force'
WHERE c.action = 'cell'
