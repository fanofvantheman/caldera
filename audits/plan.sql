AUDIT (name layer_entry_version_known);
/* blocking: an entry on a version the plan does not have is a number nobody will ever sum */
SELECT entry_id, version_id FROM @this_model WHERE NOT version_known;

AUDIT (name layer_entry_scope_resolves);
/* blocking: a slice that resolves to no leaf spreads nowhere */
SELECT entry_id, scope_material, scope_customer FROM @this_model WHERE NOT material_scope_resolves OR NOT customer_scope_resolves;

AUDIT (name layer_entry_by_owner);
/* blocking: only the layer's owner enters it — an override is a layer, never an edit of someone else's */
SELECT entry_id, layer_no, entered_by FROM @this_model WHERE NOT entered_by_owner;

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
