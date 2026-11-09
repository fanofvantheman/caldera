/* Withdrawals the run refused because the withdrawer does not hold the layer's withdraw verb. The entry stands. */
MODEL (name plan.worklist_withdrawal_refused, kind FULL, grain (entry_id));
SELECT e.entry_id, e.version_id, e.layer_no, e.withdrawn_by, e.withdrawn_on, e.entered_by,
       'withdrawal of ' || e.entry_id || ' by ' || e.withdrawn_by || ' — the entry stands' AS item,
       e.withdrawn_by || COALESCE(', ' || (SELECT STRING_AGG(DISTINCT x.principal, ', ') FROM dims.effective_entitlements x WHERE x.action = 'layer.' || e.layer_no || '.withdraw'), '') AS whose
FROM plan.layer_entry e WHERE e.withdrawn AND NOT e.withdrawn_by_owner
