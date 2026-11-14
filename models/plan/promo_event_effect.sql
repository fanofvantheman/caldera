/* Each event in the calendar read the way a commercial audience reads it: the gross uplift (its own range in the
   window), the dip after it, what it takes from (or lends to) the neighbours it declares, and the net incremental —
   in cases and in net sales at the list and terms in force. Its return is on the net: the net incremental net sales,
   less the price reduction and scan funding it gives on every other case sold in its window at the promoted scope (the
   baseline cases sell at the reduced price too), less its lump sums — fixed fee, retail media, co-op drawdown. An event
   with no neighbour line reads none declared, not none. */
MODEL (name plan.promo_event_effect, kind FULL, grain (version_id, event_id));
WITH lines AS (
  SELECT line_source AS event_id, version_id,
         SUM(CASE WHEN effect_type = 'primary' THEN cases ELSE 0 END) AS uplift_cases,
         SUM(CASE WHEN effect_type = 'timing_shift' THEN cases ELSE 0 END) AS dip_cases,
         SUM(CASE WHEN effect_type IN ('cannibalisation', 'halo') THEN cases ELSE 0 END) AS neighbour_cases,
         SUM(CASE WHEN effect_type = 'primary' THEN net_sales ELSE 0 END) AS uplift_net_sales,
         SUM(CASE WHEN effect_type = 'timing_shift' THEN net_sales ELSE 0 END) AS dip_net_sales,
         SUM(CASE WHEN effect_type IN ('cannibalisation', 'halo') THEN net_sales ELSE 0 END) AS neighbour_net_sales
  FROM plan.demand_financialised WHERE layer_no = 6 GROUP BY ALL
),
given AS (
  SELECT r.version_id, r.event_id,
         SUM(f.cases * r.in_window * (r.tpr_per_case * COALESCE((f.net_sales + f.scan_funding) / NULLIF(f.gross_invoice, 0), 0)
                                      + r.scan_funding_per_case * a.supplies_scan_data::INT)) AS given_on_other_cases
  FROM plan.promo_rate_in_window r
  JOIN plan.demand_financialised f ON f.version_id = r.version_id AND f.material_code = r.material_code AND f.account_code = r.account_code AND f.week_id = r.week_id
  JOIN dims.dim_account a ON a.account_code = r.account_code
  WHERE NOT (f.layer_no = 6 AND f.line_source = r.event_id)
  GROUP BY 1, 2
),
declared AS (
  SELECT version_id, event_id, STRING_AGG(DISTINCT effect_type || ' ' || scope_material || ' ' || format('{:+.0f}%', rate * 100), '; ') AS neighbours
  FROM plan.promo_neighbour WHERE event_in_calendar AND scope_resolves AND sign_fits GROUP BY 1, 2
)
SELECT e.event_id, e.version_id, e.account_code, e.promo_group_code, e.mechanic, e.mechanic_family, e.window_start, e.window_end,
       COALESCE(l.uplift_cases, 0) AS uplift_cases, COALESCE(l.dip_cases, 0) AS dip_cases, COALESCE(l.neighbour_cases, 0) AS neighbour_cases,
       COALESCE(l.uplift_cases, 0) + COALESCE(l.dip_cases, 0) + COALESCE(l.neighbour_cases, 0) AS net_incremental_cases,
       COALESCE(l.uplift_net_sales, 0) AS uplift_net_sales, COALESCE(l.dip_net_sales, 0) AS dip_net_sales, COALESCE(l.neighbour_net_sales, 0) AS neighbour_net_sales,
       COALESCE(l.uplift_net_sales, 0) + COALESCE(l.dip_net_sales, 0) + COALESCE(l.neighbour_net_sales, 0) AS net_incremental_net_sales,
       COALESCE(g.given_on_other_cases, 0) AS given_on_other_cases, e.lump_sums,
       COALESCE(l.uplift_net_sales, 0) + COALESCE(l.dip_net_sales, 0) + COALESCE(l.neighbour_net_sales, 0) - COALESCE(g.given_on_other_cases, 0) - e.lump_sums AS net_return,
       d.neighbours
FROM plan.promo_event e
LEFT JOIN lines l ON l.event_id = e.event_id AND l.version_id = e.version_id
LEFT JOIN given g ON g.event_id = e.event_id AND g.version_id = e.version_id
LEFT JOIN declared d ON d.event_id = e.event_id AND d.version_id = e.version_id
WHERE e.event_known
