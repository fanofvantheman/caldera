/* Entries whose reason is not in the vocabulary. They are in the plan; they cannot be read for bias until the reason is
   one the register knows. */
MODEL (name plan.worklist_reason_unknown, kind FULL, grain (entry_id));
SELECT e.entry_id, e.version_id, e.layer_no, e.entered_by, e.reason_code,
       e.entry_id || ' gives reason ' || COALESCE(e.reason_code, '(none)') AS item, e.entered_by AS whose
FROM plan.layer_entry e WHERE NOT e.reason_known AND e.entered_by_owner
