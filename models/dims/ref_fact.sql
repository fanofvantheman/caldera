/* The planning facts an organisation assigns (DEC-20261124-06 point 2): a row per fact — its name, its grain, whether it
   is *calculated* in the cycle or *standing* (set on its own, when its own event happens, and dated — point 4), and the
   right the app asks for to enter it, where a page already reads the table (`right_verb`; blank: the page still reads its
   right from the roles). Who prepares, reviews and reads each is not here: that is the entitlements, dims.planning_entitlement. The list is the
   example CH gave, a storage capacity beside it. */
MODEL (name dims.ref_fact, kind FULL, grain (fact));
SELECT * FROM (VALUES
  ('demand_forecast',          'Sales demand forecast',           'material × customer × period', 'calculated', NULL, 1),
  ('production_quantities',    'Production quantities',           'material × plant × period',    'calculated', NULL, 2),
  ('raw_material_requirements','Raw material requirements',       'material × plant × period',    'calculated', NULL, 3),
  ('inventory_targets',        'Inventory target levels',         'material × node',              'standing',   NULL, 4),
  ('purchasing_quantities',    'Purchasing quantities',           'material × plant × period',    'calculated', 'register.supply_plan.maintain', 5),
  ('purchase_prices',          'Material purchase prices',        'material × plant × period',    'standing',   'register.supply_plan.maintain', 6),
  ('storage_capacity',         'Storage capacity',                'node × storage class',         'standing',   NULL, 7),
  ('shrinkage_volume',         'Inventory shrinkage volume',      'material × node × period',     'standing',   NULL, 8),
  ('shrinkage_expense',        'Inventory shrinkage expense',     'entity × period',              'calculated', NULL, 9),
  ('factory_headcount',        'Factory headcount',               'plant × role × period',        'standing',   NULL, 10),
  ('labour_rates',             'Labour rates',                    'agreement × role',             'standing',   NULL, 11),
  ('labour_productivity',      'Labour productivity',             'line × period',                'standing',   NULL, 12),
  ('manufacturing_overhead',   'Manufacturing overhead forecast', 'plant × period',               'calculated', NULL, 13),
  ('inventory_valuation',      'Inventory valuation',             'material × plant × period',    'calculated', NULL, 14)
) AS t (fact, fact_name, grain, kind, right_verb, ord)
