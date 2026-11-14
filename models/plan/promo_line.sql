/* The promotions calendar's effect lines on layer 6: for each event, the uplift on the baseline of every material in the
   promo group at every ship-to of the account, day-weighted into the weeks the dated window touches (the account's
   promotional week starts mid-week, so a window is cut by the grid, never snapped to it); the dip in the seven days after
   the window as a timing shift; and each neighbour line the event declares — cannibalisation or halo, a rate on the
   neighbour's baseline in the same window, day-weighted the same way. The rate and funding the event carries are read by
   the financialisation, not here; a neighbour's cases carry none of them. */
MODEL (name plan.promo_line, kind FULL, grain (version_id, event_id, effect_type, material_code, ship_to_code, week_id));
WITH ev AS (
  SELECT e.event_id, e.version_id, e.account_code, e.promo_group_code, e.window_start, e.window_end, e.uplift_pct, e.dip_pct, e.status
  FROM plan.promo_event e WHERE e.event_known
),
touch AS (
  SELECT ev.*, w.week_id, w.week_start, w.week_end,
         GREATEST(0, DATE_DIFF('day', GREATEST(w.week_start, ev.window_start), LEAST(w.week_end, ev.window_end)) + 1) / 7.0 AS in_window,
         GREATEST(0, DATE_DIFF('day', GREATEST(w.week_start, ev.window_end + INTERVAL 1 DAY), LEAST(w.week_end, ev.window_end + INTERVAL 7 DAY)) + 1) / 7.0 AS in_dip
  FROM ev JOIN dims.dim_week w ON w.week_end >= ev.window_start AND w.week_start <= ev.window_end + INTERVAL 7 DAY
),
own AS (
  SELECT t.event_id, t.version_id, x.effect_type, b.material_code, b.ship_to_code, b.account_code, t.week_id,
         CASE x.effect_type WHEN 'primary' THEN b.cases * t.uplift_pct * t.in_window ELSE -b.cases * t.dip_pct * t.in_dip END AS cases,
         t.in_window, t.in_dip
  FROM touch t
  JOIN dims.ref_promo_group g ON g.promo_group_code = t.promo_group_code
  JOIN plan.layer1_lines b ON b.version_id = t.version_id AND b.material_code = g.material_code AND b.account_code = t.account_code AND b.week_id = t.week_id
  CROSS JOIN (SELECT 'primary' AS effect_type UNION ALL SELECT 'timing_shift') x
  WHERE (x.effect_type = 'primary' AND t.in_window > 0) OR (x.effect_type = 'timing_shift' AND t.in_dip > 0)
),
neighbour AS (
  SELECT t.event_id, t.version_id, n.effect_type, b.material_code, b.ship_to_code, b.account_code, t.week_id,
         SUM(b.cases * n.rate * t.in_window) AS cases, ANY_VALUE(t.in_window) AS in_window, 0.0 AS in_dip
  FROM touch t
  JOIN plan.promo_neighbour n ON n.event_id = t.event_id AND n.version_id = t.version_id AND n.event_in_calendar AND n.scope_resolves AND n.sign_fits
  JOIN plan.layer1_lines b ON b.version_id = t.version_id AND b.material_code = n.material_code AND b.account_code = t.account_code AND b.week_id = t.week_id
  WHERE t.in_window > 0
  GROUP BY ALL
)
SELECT * FROM own
UNION ALL
SELECT * FROM neighbour
