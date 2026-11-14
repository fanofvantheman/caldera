/* Every act on the opex schedule, in the order typed: a line's driver, its rate typed over the calculated one (no value:
   back to calculated), a month typed (with the calculated amount when it was typed), a reset of typed months back to
   calculated. One file per save; each act carries the save's reason. plan.opex_schedule applies them in order. A
   withdrawal is a later row naming an act (its edit_id) or a save (its save_id): what it names is out of force, and
   stays on record here. */
MODEL (name plan.schedule_edit, kind FULL, grain (edit_id), audits (schedule_edit_valid));
SELECT e.edit_id::TEXT AS edit_id, e.save_id::TEXT AS save_id, e.version_id::TEXT AS version_id, e.entity_code::TEXT AS entity_code,
       e.cost_centre_code::TEXT AS cost_centre_code, e.account_code::TEXT AS account_code, e.action::TEXT AS action,
       NULLIF(e.period::TEXT, '') AS period, e.value::DOUBLE AS value, NULLIF(e.driver::TEXT, '') AS driver, e.calc_at_entry::DOUBLE AS calc_at_entry,
       e.reason_code::TEXT AS reason_code, NULLIF(e.note::TEXT, '') AS note, e.entered_by::TEXT AS entered_by, e.entered_on::TIMESTAMP AS entered_on,
       e.source_file::TEXT AS source_file, NULLIF(e.withdraws::TEXT, '') AS withdraws,
       w.edit_id AS withdrawn_by_act, w.entered_by AS withdrawn_by, w.entered_on::TIMESTAMP AS withdrawn_on
FROM bronze.reg_schedule_edit e
LEFT JOIN (SELECT withdraws, ANY_VALUE(edit_id) AS edit_id, ANY_VALUE(entered_by) AS entered_by, ANY_VALUE(entered_on) AS entered_on
           FROM bronze.reg_schedule_edit WHERE action = 'withdraw' GROUP BY 1) w ON w.withdraws IN (e.edit_id, e.save_id)
