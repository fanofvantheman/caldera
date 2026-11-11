/* The promotions calendar for a version — one calendar, two doors. The events the promotions sender sends for the
   accounts it masters, resolved through the mapping, and the events typed in the plan for every other account; each
   carries its source and, for a sender's event, the sender's codes beside the mapped ones. Only events in the calendar
   are here: held, refused and cancelled events are on their own lists. Downstream reads it as one: a dated window at an
   account over a promo group, the mechanic and its family, the uplift and dip, the price reduction and scan funding per
   case, and the lump sums — a fixed fee, retail-media money, a drawdown on the account's co-op envelope — with any
   funding the financialisation does not yet price, carried and shown.
   The account's promotional week rides on the event: an event whose window does not start on the account's week day,
   or does not run whole promotional weeks, is flagged — never refused or snapped; the dates are the sender's or the
   author's to state, and the grid cuts the window by days either way. */
MODEL (name plan.promo_event, kind FULL, grain (event_id), audits (promo_event_valid, promo_event_one_door));
WITH both AS (
  SELECT event_id, version_id, 'sender' AS source, sender, account_code, promo_group_code, window_start, window_end, mechanic,
         uplift_pct, dip_pct, 'sender' AS response_source, tpr_per_case, scan_funding_per_case, fixed_fee, media_fee, envelope_drawdown, status,
         'trade.marketing@caldera' AS owner, baseline_version, unpriced_funding,
         CONCAT_WS(' · ', local_account, local_product_group, local_tactic, local_status, local_fund_types) AS local_codes, NULL AS note
  FROM plan.promo_sender_event WHERE state = 'in'
  UNION ALL
  SELECT event_id, version_id, 'plan', NULL, account_code, promo_group_code, window_start, window_end, mechanic,
         uplift_pct, dip_pct, response_source, tpr_per_case, scan_funding_per_case, fixed_fee, media_fee, envelope_drawdown, status,
         owner, baseline_version, NULL, NULL, note
  FROM plan.promo_typed_event WHERE state = 'in'
)
SELECT b.event_id, b.version_id, b.source, b.sender, b.account_code, b.promo_group_code, b.window_start, b.window_end,
       b.mechanic, m.family AS mechanic_family, b.uplift_pct, b.dip_pct, b.response_source, b.tpr_per_case, b.scan_funding_per_case,
       b.fixed_fee, b.media_fee, b.envelope_drawdown, b.fixed_fee + b.media_fee + b.envelope_drawdown AS lump_sums,
       b.status, b.owner, b.baseline_version, b.unpriced_funding, b.local_codes, b.note, a.promotions_master,
       a.promo_week_start, DAYNAME(b.window_start) AS window_start_day, DATE_DIFF('day', b.window_start, b.window_end) + 1 AS window_days,
       a.promo_week_start IS NOT NULL AND (DAYNAME(b.window_start) <> a.promo_week_start OR (DATE_DIFF('day', b.window_start, b.window_end) + 1) % 7 <> 0) AS off_week,
       CASE WHEN a.promo_week_start IS NOT NULL AND DAYNAME(b.window_start) <> a.promo_week_start
              THEN 'starts on a ' || DAYNAME(b.window_start) || '; ' || b.account_code || ' promotional weeks start on a ' || a.promo_week_start
            WHEN a.promo_week_start IS NOT NULL AND (DATE_DIFF('day', b.window_start, b.window_end) + 1) % 7 <> 0
              THEN (DATE_DIFF('day', b.window_start, b.window_end) + 1) || ' days — not whole promotional weeks' END AS off_week_says,
       v.version_id IS NOT NULL AND a.account_code IS NOT NULL AND g.promo_group_code IS NOT NULL AND m.mechanic IS NOT NULL
         AND b.window_end >= b.window_start AS event_known
FROM both b
LEFT JOIN dims.ctl_version v ON v.version_id = b.version_id
LEFT JOIN dims.dim_account a ON a.account_code = b.account_code
LEFT JOIN dims.ref_mechanic m ON m.mechanic = b.mechanic
LEFT JOIN (SELECT DISTINCT promo_group_code FROM dims.ref_promo_group) g ON g.promo_group_code = b.promo_group_code
