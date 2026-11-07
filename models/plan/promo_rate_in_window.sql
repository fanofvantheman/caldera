/* What an event does to the invoice: the temporary price reduction and scan funding per case, day-weighted by how much of
   each week sits inside the window, on every material in the promo group at the account. Applies to every case shipped
   in the window whatever layer carried it — the baseline cases are sold at the reduced price too. */
MODEL (name plan.promo_rate_in_window, kind FULL, grain (event_id, material_code, account_code, week_id));
SELECT e.event_id, e.version_id, g.material_code, e.account_code, w.week_id,
       (GREATEST(0, DATE_DIFF('day', GREATEST(w.week_start, e.window_start), LEAST(w.week_end, e.window_end)) + 1) / 7.0) AS in_window,
       e.tpr_per_case, e.scan_funding_per_case
FROM plan.promo_event e
JOIN dims.ref_promo_group g ON g.promo_group_code = e.promo_group_code
JOIN dims.dim_week w ON w.week_end >= e.window_start AND w.week_start <= e.window_end
WHERE e.event_known
