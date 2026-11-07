/* Trading accounts: the member terms are agreed with and demand is planned for. Channel, tier, route to market and
   terms are attributes; the trading group equals the account unless a deployment says otherwise. */
MODEL (name dims.dim_account, kind FULL, grain (account_code));
SELECT account_code::TEXT AS account_code, account_name::TEXT AS account_name, account_code::TEXT AS trading_group_code,
       channel::TEXT AS channel, NULLIF(sub_channel::TEXT, '') AS sub_channel, account_tier::TEXT AS account_tier,
       route_to_market::TEXT AS route_to_market, state::TEXT AS state, price_list::TEXT AS price_list,
       payment_terms_days::INT AS payment_terms_days, settlement_discount_pct::DOUBLE AS settlement_discount_pct,
       collaborative_flag::TEXT = 'Y' AS is_collaborative, scan_flag::TEXT = 'Y' AS supplies_scan_data, status::TEXT AS status
FROM bronze.dim_account
