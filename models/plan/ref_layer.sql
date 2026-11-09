/* The layers of the demand stack: number, name, the role that owns it, sign, whether it is present at this stage, and the
   level of the customer structure its owner submits at — account for the account-facing layers, unit for the planner's own,
   all for the layers scoped on material, which have no per-account step. */
MODEL (name plan.ref_layer, kind FULL, grain (layer_no));
SELECT * FROM (VALUES
  (1, 'Statistical baseline',   'DEMAND_PLANNER',      '+', TRUE,  'computed from cleansed history: level, trend, each ship-to''s seasonality', 'unit'),
  (2, 'Baseline adjustment',    'DEMAND_PLANNER',      '±', TRUE,  'judgement with a reason code, at any slice; rates on the baseline in the far horizon', 'unit'),
  (3, 'Market',                 'COMMERCIAL_INSIGHTS', '±', FALSE, 'folded into layer 2 at this stage', 'none'),
  (4, 'Distribution',           'KEY_ACCOUNT_MANAGER', '±', TRUE,  'listings gained and lost, by catchment', 'account'),
  (5, 'Price response',         'REVENUE_MANAGER',     '±', FALSE, 'absent by declaration at this stage', 'none'),
  (6, 'Promotions',             'TRADE_MARKETING',     '±', TRUE,  'the calendar''s uplift in the window and the dip after it', 'account'),
  (7, 'Innovation',             'PORTFOLIO_MARKETING', '+', TRUE,  'launch volume typed in, cannibalisation as its own line', 'all'),
  (8, 'Lifecycle exit',         'PORTFOLIO_MARKETING', '-', TRUE,  'run-out and discontinuation', 'all'),
  (9, 'Customer collaborative', 'KEY_ACCOUNT_MANAGER', '±', FALSE, 'absent at this stage', 'none')
) AS t(layer_no, layer_name, owner_role, sign, present_at_this_stage, how, submits_at)
