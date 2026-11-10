/* Trading accounts: the member terms are agreed with and demand is planned for. Channel, tier, route to market and
   terms are attributes; the trading group equals the account unless a deployment says otherwise. Each account names
   where its promotions are mastered — TPM (the trade promotion system sends them) or PLAN (typed in the plan) — so one
   promotion can never arrive through both doors. */
MODEL (name dims.dim_account, kind FULL, grain (account_code), audits (account_promotions_master_known));
SELECT account_code::TEXT AS account_code, account_name::TEXT AS account_name, account_code::TEXT AS trading_group_code,
       channel::TEXT AS channel, NULLIF(sub_channel::TEXT, '') AS sub_channel, account_tier::TEXT AS account_tier,
       route_to_market::TEXT AS route_to_market, state::TEXT AS state, price_list::TEXT AS price_list,
       payment_terms_days::INT AS payment_terms_days, settlement_discount_pct::DOUBLE AS settlement_discount_pct,
       collaborative_flag::TEXT = 'Y' AS is_collaborative, scan_flag::TEXT = 'Y' AS supplies_scan_data, status::TEXT AS status,
       planning_unit::TEXT AS planning_unit, planning_unit_name::TEXT AS planning_unit_name,
       COALESCE(NULLIF(promotions_master::TEXT, ''), 'PLAN') AS promotions_master
FROM bronze.dim_account
