/* Events from the promotions sender held out of the calendar: what each waits for — a code with no mapping, a proposal
   nobody has reviewed, a status still proposed — and what it would bring when it enters: the cases (uplift in the window
   less the dip after, on the baseline of every material in the promo group at every ship-to of the account, day-weighted
   as the calendar does it), the net sales those cases and the event's price reduction and scan funding would move at the
   list and terms in force, and the fixed fee beside. Where a code is not yet mapped to an account or a promo group the
   volume cannot be placed and reads nothing. Routed to trade marketing; the event enters on the first run after its wait
   is over. */
MODEL (name plan.worklist_promo_held, kind FULL, grain (version_id, event_id));
WITH ev AS (
  SELECT * FROM plan.promo_sender_event WHERE state = 'held'
),
touch AS (
  SELECT ev.event_id, ev.version_id, ev.account_code, ev.promo_group_code, ev.uplift_pct, ev.dip_pct, ev.tpr_per_case, ev.scan_funding_per_case,
         w.week_id,
         GREATEST(0, DATE_DIFF('day', GREATEST(w.week_start, ev.window_start), LEAST(w.week_end, ev.window_end)) + 1) / 7.0 AS in_window,
         GREATEST(0, DATE_DIFF('day', GREATEST(w.week_start, ev.window_end + INTERVAL 1 DAY), LEAST(w.week_end, ev.window_end + INTERVAL 7 DAY)) + 1) / 7.0 AS in_dip
  FROM ev JOIN dims.dim_week w ON w.week_end >= ev.window_start AND w.week_start <= ev.window_end + INTERVAL 7 DAY
),
cells AS (
  SELECT t.*, b.material_code, b.ship_to_code, b.cases AS baseline_cases,
         b.cases * t.uplift_pct * t.in_window AS primary_cases, -b.cases * t.dip_pct * t.in_dip AS dip_cases
  FROM touch t
  JOIN dims.ref_promo_group g ON g.promo_group_code = t.promo_group_code
  JOIN plan.layer1_lines b ON b.version_id = t.version_id AND b.material_code = g.material_code AND b.account_code = t.account_code AND b.week_id = t.week_id
),
rate AS (   -- at each cell, what a baseline case nets and how much of an invoice dollar survives the off-invoice terms
  SELECT version_id, material_code, ship_to_code, week_id, SUM(net_sales) / NULLIF(SUM(cases), 0) AS net_per_case,
         SUM(net_sales + scan_funding) / NULLIF(SUM(gross_invoice), 0) AS kept_of_invoice, BOOL_OR(event_ids IS NULL) AS clean
  FROM plan.demand_financialised WHERE layer_no = 1 GROUP BY ALL
),
money AS (
  SELECT c.event_id, c.version_id, SUM(c.primary_cases + c.dip_cases) AS cases,
         SUM((c.primary_cases + c.dip_cases) * COALESCE(r.net_per_case, 0)
             - c.in_window * (c.baseline_cases + c.primary_cases) * (c.tpr_per_case * COALESCE(r.kept_of_invoice, 0) + c.scan_funding_per_case * a.supplies_scan_data::INT)) AS net_sales
  FROM cells c
  JOIN dims.dim_account a ON a.account_code = c.account_code
  LEFT JOIN rate r ON r.version_id = c.version_id AND r.material_code = c.material_code AND r.ship_to_code = c.ship_to_code AND r.week_id = c.week_id
  GROUP BY ALL
),
readers AS (SELECT STRING_AGG(DISTINCT principal, ', ') AS whose FROM dims.effective_entitlements WHERE action = 'register.promo_calendar.maintain')
SELECT e.event_id, e.version_id, e.sender_file, e.local_account, e.local_product_group, e.local_tactic, e.local_status,
       e.account_code, e.promo_group_code, e.window_start, e.window_end, e.waits_for,
       COALESCE(m.cases, 0) AS would_bring_cases, COALESCE(m.net_sales, 0) AS would_bring_net_sales, e.fixed_fee AS would_bring_fixed_fee,
       e.event_id || ' (' || e.local_account || ', ' || e.local_product_group || ', ' || e.window_start || ') waits for ' || e.waits_for AS item,
       r.whose
FROM ev e
LEFT JOIN money m ON m.event_id = e.event_id AND m.version_id = e.version_id
CROSS JOIN readers r
