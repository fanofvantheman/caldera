/* The promotions calendar as filed for a version: a dated window at an account over a promo group, with the mechanic,
   the uplift and dip assumptions, the price reduction and scan funding per case, and any fixed fee. */
MODEL (name plan.promo_event, kind FULL, grain (event_id), audits (promo_event_valid));
SELECT e.event_id::TEXT AS event_id, e.version_id::TEXT AS version_id, e.account_code::TEXT AS account_code, e.promo_group_code::TEXT AS promo_group_code,
       e.window_start::DATE AS window_start, e.window_end::DATE AS window_end, e.mechanic::TEXT AS mechanic,
       e.uplift_pct::DOUBLE AS uplift_pct, e.dip_pct::DOUBLE AS dip_pct, e.tpr_per_case::DOUBLE AS tpr_per_case,
       e.scan_funding_per_case::DOUBLE AS scan_funding_per_case, e.fixed_fee::DOUBLE AS fixed_fee, e.status::TEXT AS status,
       e.owner::TEXT AS owner, e.baseline_version::TEXT AS baseline_version,
       v.version_id IS NOT NULL AND a.account_code IS NOT NULL AND g.promo_group_code IS NOT NULL AND e.window_end::DATE >= e.window_start::DATE AS event_known
FROM bronze.reg_promo_event e
LEFT JOIN dims.ctl_version v ON v.version_id = e.version_id
LEFT JOIN dims.dim_account a ON a.account_code = e.account_code
LEFT JOIN (SELECT DISTINCT promo_group_code FROM dims.ref_promo_group) g ON g.promo_group_code = e.promo_group_code
