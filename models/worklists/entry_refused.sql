/* Entries the run refused because the author does not hold the layer's enter verb. The entry stays on file and out of
   the plan; the author and the layer's owners are told. */
MODEL (name plan.worklist_entry_refused, kind FULL, grain (entry_id));
SELECT e.entry_id, e.version_id, e.layer_no, e.entered_by, e.entered_on, e.scope_material, e.scope_customer, e.period_from, e.period_to, e.value, e.value_kind,
       e.entry_id || ' on ' || e.version_id || ' layer ' || e.layer_no || ' by ' || e.entered_by AS item,
       e.entered_by || COALESCE(', ' || (SELECT STRING_AGG(DISTINCT x.principal, ', ') FROM dims.effective_entitlements x WHERE x.action = 'layer.' || e.layer_no || '.enter'), '') AS whose
FROM plan.layer_entry e WHERE NOT e.entered_by_owner
