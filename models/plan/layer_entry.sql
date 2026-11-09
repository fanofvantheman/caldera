/* What the people typed: one row per contribution to a layer on a version — the slice chosen on each dimension, a time
   window in periods, a value in cases or as a rate on the baseline, the rule that spreads it, who entered it and why.
   A later row may withdraw it; the entry stays on file, marked. Flags say whether the row can be used; nothing is
   corrected here. */
MODEL (name plan.layer_entry, kind FULL, grain (entry_id),
       audits (layer_entry_version_known, layer_entry_scope_resolves, layer_entry_by_owner, layer_entry_withdraw_by_owner,
               layer_entry_reason_known, layer_entry_vocabulary, layer_entry_window_in_horizon, layer_entry_after_submission));
WITH withdrawals AS (
  SELECT w.withdraws::TEXT AS entry_id, w.entered_by::TEXT AS withdrawn_by, w.entered_on::DATE AS withdrawn_on, NULLIF(w.note::TEXT, '') AS withdrawal_note,
         w.layer_no::INT AS layer_no
  FROM bronze.layer_entry w WHERE w.action = 'withdraw'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY w.withdraws ORDER BY w.source_file DESC, w.file_row_number DESC) = 1
)
SELECT e.entry_id::TEXT AS entry_id, e.version_id::TEXT AS version_id, e.layer_no::INT AS layer_no,
       e.entered_by::TEXT AS entered_by, e.entered_on::DATE AS entered_on, e.reason_code::TEXT AS reason_code, e.effect_type::TEXT AS effect_type,
       e.scope_material::TEXT AS scope_material, e.scope_customer::TEXT AS scope_customer,
       e.period_from::TEXT AS period_from, e.period_to::TEXT AS period_to, e.value_kind::TEXT AS value_kind, e.value::DOUBLE AS value,
       e.spread_rule::TEXT AS spread_rule, NULLIF(e.note::TEXT, '') AS note, e.source_file, e.file_row_number,
       wd.entry_id IS NOT NULL AS withdrawn, wd.withdrawn_by, wd.withdrawn_on, wd.withdrawal_note,
       wd.entry_id IS NULL OR EXISTS (SELECT 1 FROM dims.effective_entitlements x WHERE x.principal = wd.withdrawn_by AND x.action = 'layer.' || e.layer_no::TEXT || '.withdraw') AS withdrawn_by_owner,
       r.reason_code IS NOT NULL AS reason_known,
       EXISTS (SELECT 1 FROM plan.submission s JOIN dims.dim_customer_hierarchy h ON h.ancestor_code = s.scope_node AND h.descendant_code = e.scope_customer
               WHERE s.version_id = e.version_id AND s.subject = 'layer:' || e.layer_no::TEXT AND s.state = 'submitted' AND s.acted_by_holder
                 AND s.acted_on < e.entered_on::DATE) AS after_submission,
       v.version_id IS NOT NULL AS version_known,
       EXISTS (SELECT 1 FROM dims.dim_material_hierarchy h WHERE h.ancestor_code = e.scope_material AND h.descendant_is_leaf)
         OR EXISTS (SELECT 1 FROM dims.ref_promo_group g WHERE g.promo_group_code = e.scope_material) AS material_scope_resolves,
       EXISTS (SELECT 1 FROM dims.dim_customer_hierarchy h WHERE h.ancestor_code = e.scope_customer AND h.descendant_is_leaf) AS customer_scope_resolves,
       EXISTS (SELECT 1 FROM dims.effective_entitlements x WHERE x.principal = e.entered_by AND x.action = 'layer.' || e.layer_no::TEXT || '.enter') AS entered_by_owner,
       e.period_from >= v.horizon_start AND e.period_to <= v.horizon_end AS window_in_horizon,
       e.period_from <= e.period_to AS window_ordered
FROM bronze.layer_entry e
LEFT JOIN dims.ctl_version v ON v.version_id = e.version_id
LEFT JOIN withdrawals wd ON wd.entry_id = e.entry_id
LEFT JOIN plan.ref_reason_code r ON r.reason_code = e.reason_code
WHERE e.action = 'enter' OR e.action IS NULL
