/* Entries made after their layer was submitted at a covering scope. Held out of the plan until the holder reopens; the
   author and the holder are told. */
MODEL (name plan.worklist_entry_after_submission, kind FULL, grain (entry_id));
SELECT e.entry_id, e.version_id, e.layer_no, e.entered_by, e.entered_on, e.scope_material, e.scope_customer,
       e.entry_id || ' on layer ' || e.layer_no || ' at ' || e.scope_customer || ' — entered ' || e.entered_on || ' after the layer was submitted' AS item,
       e.entered_by || COALESCE(', ' || (SELECT STRING_AGG(DISTINCT x.principal, ', ') FROM dims.effective_entitlements x
                                         WHERE x.action = 'layer.' || e.layer_no || '.reopen' AND ((x.scope_dimension = 'customer' AND x.node = e.scope_customer) OR (e.scope_customer = 'ALL' AND x.node = 'ALL'))), '') AS whose
FROM plan.layer_entry e WHERE e.after_submission AND NOT (e.withdrawn AND e.withdrawn_by_owner)
