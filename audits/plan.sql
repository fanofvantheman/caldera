AUDIT (name layer_entry_version_known);
/* blocking: an entry on a version the plan does not have is a number nobody will ever sum */
SELECT entry_id, version_id FROM @this_model WHERE NOT version_known;

AUDIT (name layer_entry_scope_resolves);
/* blocking: a slice that resolves to no leaf spreads nowhere */
SELECT entry_id, scope_material, scope_customer FROM @this_model WHERE NOT material_scope_resolves OR NOT customer_scope_resolves;

AUDIT (name layer_entry_by_owner);
/* blocking: only the layer's owner enters it — an override is a layer, never an edit of someone else's */
SELECT entry_id, layer_no, entered_by FROM @this_model WHERE NOT entered_by_owner;

AUDIT (name layer_entry_withdraw_by_owner);
/* blocking: a withdrawal is the owner's act too — a row that tries to take out someone else's entry is refused, and
   the entry stands */
SELECT entry_id, layer_no, withdrawn_by FROM @this_model WHERE withdrawn AND NOT withdrawn_by_owner;

AUDIT (name layer_entry_reason_known, blocking false);
/* warn: a reason the vocabulary does not have cannot be read for bias */
SELECT entry_id, reason_code FROM @this_model WHERE NOT reason_known;

AUDIT (name layer_entry_after_submission, blocking false);
/* verdict: the layer was submitted at a scope covering this entry before it was made — held out until a reopen */
SELECT entry_id, layer_no, scope_customer, entered_on FROM @this_model WHERE after_submission AND NOT (withdrawn AND withdrawn_by_owner);

AUDIT (name layer_entry_vocabulary);
SELECT entry_id FROM @this_model
WHERE layer_no NOT BETWEEN 1 AND 9 OR value_kind NOT IN ('cases', 'rate_on_baseline')
   OR spread_rule NOT IN ('baseline_shape', 'history_shape', 'catchment') OR effect_type NOT IN ('primary', 'cannibalisation', 'timing_shift')
   OR NOT window_ordered;

AUDIT (name layer_entry_window_in_horizon, blocking false);
/* warn: an entry outside the version's horizon is kept but contributes nothing the version reads */
SELECT entry_id, version_id, period_from, period_to FROM @this_model WHERE version_known AND NOT window_in_horizon;

AUDIT (name promo_event_valid);
SELECT event_id FROM @this_model WHERE NOT event_known;

AUDIT (name terms_vocabulary);
SELECT instrument_code FROM @this_model
WHERE NOT account_known
   OR instrument_kind NOT IN ('standing_discount', 'retro_rebate', 'volume_rebate', 'growth_incentive', 'warehouse_allowance', 'settlement_discount', 'range_bonus')
   OR driver_basis NOT IN ('pct_of_list', 'pct_of_invoice', 'per_case', 'lump_sum', 'tiered')
   OR flow_position NOT IN ('on_invoice', 'off_invoice')
   OR conditionality NOT IN ('unconditional', 'volume', 'growth', 'event', 'compliance', 'payment')
   OR settlement_timing NOT IN ('in_period', 'quarterly', 'annual_retro');

AUDIT (name stack_cells_non_negative, blocking false);
/* warn: a cell whose layers sum below zero — an exit or dip larger than what was there */
SELECT version_id, material_code, ship_to_code, week_id, SUM(cases) AS cases FROM @this_model
GROUP BY ALL HAVING SUM(cases) < -0.5;

AUDIT (name every_cell_priced);
/* blocking: a case with no list price in force is volume the P&L cannot see */
SELECT DISTINCT version_id, material_code, account_code, price_list FROM @this_model WHERE NOT priced;

AUDIT (name gross_to_net_identity);
/* blocking: gross at list less every deduction is net sales, to the cent, on every line */
SELECT version_id, line_source, material_code, ship_to_code, week_id FROM @this_model
WHERE ABS(gross_at_list - standing_discount - temporary_price_reduction - retro_rebate - volume_rebate_accrual - warehouse_allowance
          - scan_funding - settlement_discount - returns_and_ullage - claims - net_sales) > 0.005;

AUDIT (name long_form_ties_to_wide);
/* blocking: the long form carries exactly the wide form's money plus the fixed fees */
WITH long AS (
  SELECT version_id, SUM(CASE WHEN measure = 'gross_at_list' THEN amount END) AS gross, SUM(CASE WHEN measure = 'net_sales' THEN amount END) AS net
  FROM @this_model GROUP BY version_id
),
wide AS (SELECT version_id, SUM(gross_at_list) AS gross, SUM(net_sales) AS net FROM plan.demand_financialised GROUP BY version_id)
SELECT l.version_id, l.gross - w.gross AS gross_diff, l.net - w.net AS net_diff
FROM long l JOIN wide w ON w.version_id = l.version_id
WHERE ABS(l.gross - w.gross) > 0.01 OR ABS(l.net - w.net) > 0.01;

AUDIT (name promo_event_one_door);
/* blocking: an event in the calendar came in through the door its account's promotions are mastered at — the sender's
   for TPM, the plan's for PLAN — so no promotion is counted through both */
SELECT event_id, source, account_code, promotions_master FROM @this_model
WHERE (source = 'sender' AND promotions_master <> 'TPM') OR (source = 'plan' AND promotions_master <> 'PLAN');

AUDIT (name promo_mapping_vocabulary);
SELECT sender, subject, local_code FROM @this_model
WHERE subject NOT IN ('mechanic', 'funding_type', 'status', 'customer', 'material')
   OR origin NOT IN ('first_pass', 'person') OR review_state NOT IN ('proposed', 'accepted', 'altered')
   OR (confidence IS NOT NULL AND confidence NOT IN ('high', 'medium', 'low'));

AUDIT (name promo_mapping_target_known);
/* blocking: a mapping in force lands on a member of our list — the reviewer alters within it, never invents */
SELECT sender, subject, local_code, target_code FROM @this_model WHERE review_state IN ('accepted', 'altered') AND NOT target_known;

AUDIT (name mechanic_family_known);
SELECT mechanic, family FROM @this_model
WHERE family NOT IN ('price', 'feature_and_display', 'pack', 'theme_and_seasonal', 'trial_and_experience', 'loyalty_and_personalised', 'clearance', 'unclassified');

AUDIT (name funding_type_priced_has_column);
SELECT funding_type FROM @this_model
WHERE priced AND COALESCE(event_column, '') NOT IN ('tpr_per_case', 'scan_funding_per_case', 'fixed_fee');

AUDIT (name account_promotions_master_known);
SELECT account_code, promotions_master FROM @this_model WHERE promotions_master NOT IN ('TPM', 'PLAN');
