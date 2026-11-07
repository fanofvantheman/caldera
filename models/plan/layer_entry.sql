/* What the people typed: one row per contribution to a layer on a version — the slice chosen on each dimension, a time
   window in periods, a value in cases or as a rate on the baseline, the rule that spreads it, who entered it and why.
   Flags say whether the row can be used; nothing is corrected here. */
MODEL (name plan.layer_entry, kind FULL, grain (entry_id),
       audits (layer_entry_version_known, layer_entry_scope_resolves, layer_entry_by_owner, layer_entry_vocabulary, layer_entry_window_in_horizon));
SELECT e.entry_id::TEXT AS entry_id, e.version_id::TEXT AS version_id, e.layer_no::INT AS layer_no,
       e.entered_by::TEXT AS entered_by, e.entered_on::DATE AS entered_on, e.reason_code::TEXT AS reason_code, e.effect_type::TEXT AS effect_type,
       e.scope_material::TEXT AS scope_material, e.scope_customer::TEXT AS scope_customer,
       e.period_from::TEXT AS period_from, e.period_to::TEXT AS period_to, e.value_kind::TEXT AS value_kind, e.value::DOUBLE AS value,
       e.spread_rule::TEXT AS spread_rule, NULLIF(e.note::TEXT, '') AS note, e.source_file, e.file_row_number,
       v.version_id IS NOT NULL AS version_known,
       EXISTS (SELECT 1 FROM dims.dim_material_hierarchy h WHERE h.ancestor_code = e.scope_material AND h.descendant_is_leaf)
         OR EXISTS (SELECT 1 FROM dims.ref_promo_group g WHERE g.promo_group_code = e.scope_material) AS material_scope_resolves,
       EXISTS (SELECT 1 FROM dims.dim_customer_hierarchy h WHERE h.ancestor_code = e.scope_customer AND h.descendant_is_leaf) AS customer_scope_resolves,
       EXISTS (SELECT 1 FROM dims.effective_entitlements x WHERE x.principal = e.entered_by AND x.action = 'layer.' || e.layer_no::TEXT || '.enter') AS entered_by_owner,
       e.period_from >= v.horizon_start AND e.period_to <= v.horizon_end AS window_in_horizon,
       e.period_from <= e.period_to AS window_ordered
FROM bronze.layer_entry e
LEFT JOIN dims.ctl_version v ON v.version_id = e.version_id
