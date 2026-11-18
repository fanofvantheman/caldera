/* The stages a Plan is worked in (DEC-20261118-04 point 1): a stage is a handover between owners, in order; a step is
   calculation order inside one owner's work. Each names what it hands over and the right whose holder hands it over —
   an existing right of the stage's owner. Supply is three stages: the inventory planner hands to production, production
   to materials. Storage is a reading on the inventory and production pages, not a stage. */
MODEL (name dims.ref_stage, kind FULL, grain stage);
SELECT * FROM (VALUES
  (1, 'demand',     'Demand',             'the demand plan',                                      'demand.plan.submit'),
  (2, 'valuation',  'Demand valuation',   'net sales — the demand plan''s cases valued',          'register.terms.maintain'),
  (3, 'inventory',  'Inventory',          'the requirement on each plant, by material and period', 'register.service_level.maintain'),
  (4, 'production', 'Production',         'cases to make',                                        'delta.supply.enter'),
  (5, 'materials',  'Materials',          'material purchases, with the stock and average cost they make', 'register.supply_plan.maintain'),
  (6, 'cost',       'Cost',               'planned unit cost, absorption, variances',             'standard.derive'),
  (7, 'finance',    'Finance''s forecast', 'the profit and loss',                                 'overlay.finance.enter'),
  (8, 'statements', 'Statements',         'the reading layer',                                    'register.timing_policy.maintain')
) AS t (ord, stage, stage_name, hands_over, verb)
