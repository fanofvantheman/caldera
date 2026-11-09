/* Entries the run could not place: a scope that reaches nothing, a window outside the version's horizon or reversed,
   a version not on the register. The author fixes the entry by withdrawing it and entering again. */
MODEL (name plan.worklist_entry_unresolved, kind FULL, grain (entry_id));
SELECT e.entry_id, e.version_id, e.layer_no, e.entered_by, e.scope_material, e.scope_customer, e.period_from, e.period_to,
       e.entry_id || ': ' || CONCAT_WS('; ',
         CASE WHEN NOT e.version_known THEN 'version ' || e.version_id || ' unknown' END,
         CASE WHEN NOT e.material_scope_resolves THEN 'material scope ' || e.scope_material || ' reaches nothing' END,
         CASE WHEN NOT e.customer_scope_resolves THEN 'customer scope ' || e.scope_customer || ' reaches nothing' END,
         CASE WHEN NOT e.window_ordered THEN 'window reversed' END,
         CASE WHEN e.window_ordered AND NOT e.window_in_horizon THEN 'window outside the horizon' END) AS item,
       e.entered_by AS whose
FROM plan.layer_entry e
WHERE e.entered_by_owner AND NOT (e.version_known AND e.material_scope_resolves AND e.customer_scope_resolves AND e.window_ordered AND e.window_in_horizon)
