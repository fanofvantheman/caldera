/* The waterfall in long form: one row per line per measure, each deduction carrying the attributes that decide it —
   band (presentation), flow position, driver basis, conditionality, source. An event's lump sums join here as planned
   money against the event — its fixed fee, its retail-media money and its drawdown on the account's co-op envelope, each
   its own measure — attributed to the materials in its scope by their cases in the window. The envelope itself is not
   money here: only what events draw from it is, so it is counted once. */
MODEL (name plan.gross_to_net, kind FULL, grain (version_id, layer_no, line_source, effect_type, material_code, ship_to_code, week_id, measure),
       audits (long_form_ties_to_wide));
WITH f AS (SELECT * FROM plan.demand_financialised),
long AS (
  SELECT version_id, layer_no, line_source, effect_type, material_code, ship_to_code, account_code, week_id, period, measure, amount, 'derived' AS value_state
  FROM f UNPIVOT (amount FOR measure IN (gross_at_list, standing_discount, temporary_price_reduction, retro_rebate, volume_rebate_accrual,
                                         warehouse_allowance, scan_funding, settlement_discount, returns_and_ullage, claims, net_sales))
),
lump AS (
  SELECT event_id, 'promotional_fixed_fee' AS measure, fixed_fee AS amount FROM plan.promo_event WHERE fixed_fee > 0
  UNION ALL SELECT event_id, 'promotional_media', media_fee FROM plan.promo_event WHERE media_fee > 0
  UNION ALL SELECT event_id, 'coop_envelope_drawdown', envelope_drawdown FROM plan.promo_event WHERE envelope_drawdown > 0
),
fee_scope AS (
  SELECT r.event_id, r.version_id, s.layer_no, s.line_source, s.effect_type, s.material_code, s.ship_to_code, s.account_code, s.week_id, s.period,
         s.cases * r.in_window AS in_window_cases
  FROM plan.promo_rate_in_window r
  JOIN plan.demand_stack s ON s.version_id = r.version_id AND s.material_code = r.material_code AND s.account_code = r.account_code AND s.week_id = r.week_id
  WHERE s.cases > 0
),
fee_share AS (
  SELECT f.*, l.measure, l.amount * f.in_window_cases / SUM(f.in_window_cases) OVER (PARTITION BY f.event_id, l.measure) AS fee
  FROM fee_scope f JOIN lump l ON l.event_id = f.event_id
),
fees AS (
  SELECT version_id, layer_no, line_source, effect_type, material_code, ship_to_code, account_code, week_id, period, measure,
         SUM(fee) AS amount, 'allocated' AS value_state
  FROM fee_share GROUP BY ALL
),
rows_ AS (SELECT * FROM long WHERE amount <> 0 UNION ALL SELECT * FROM fees)
SELECT r.*, m.band, m.flow_position, m.driver_basis, m.conditionality, m.source, m.sign
FROM rows_ r
JOIN (VALUES
  ('gross_at_list',             'gross',       NULL,          'per_case',       NULL,            'price_list',  0),
  ('standing_discount',         'on_invoice',  'on_invoice',  'pct_of_list',    'unconditional', 'terms',      -1),
  ('temporary_price_reduction', 'on_invoice',  'on_invoice',  'per_case',       'event',         'promotions', -1),
  ('retro_rebate',              'volume_terms','off_invoice', 'pct_of_invoice', 'unconditional', 'terms',      -1),
  ('volume_rebate_accrual',     'volume_terms','off_invoice', 'pct_of_invoice', 'volume',        'terms',      -1),
  ('scan_funding',              'promotion',   'off_invoice', 'per_case',       'event',         'promotions', -1),
  ('promotional_fixed_fee',     'promotion',   'off_invoice', 'lump_sum',       'event',         'promotions', -1),
  ('promotional_media',         'promotion',   'off_invoice', 'lump_sum',       'event',         'promotions', -1),
  ('coop_envelope_drawdown',    'promotion',   'off_invoice', 'lump_sum',       'event',         'terms',      -1),
  ('warehouse_allowance',       'service',     'off_invoice', 'pct_of_invoice', 'unconditional', 'terms',      -1),
  ('settlement_discount',       'payment',     'off_invoice', 'pct_of_invoice', 'payment',       'terms',      -1),
  ('returns_and_ullage',        'compliance',  'off_invoice', 'pct_of_invoice', 'compliance',    'history',    -1),
  ('claims',                    'compliance',  'off_invoice', 'pct_of_invoice', 'compliance',    'history',    -1),
  ('net_sales',                 'net',         NULL,          NULL,             NULL,            'derived',     0)
) AS m(measure, band, flow_position, driver_basis, conditionality, source, sign) ON m.measure = r.measure
