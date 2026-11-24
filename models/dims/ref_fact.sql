/* The planning facts an organisation assigns (DEC-20261124-06 point 2): a row per fact — its name, its grain, whether it
   is *calculated* in the cycle or *standing* (set on its own, when its own event happens, and dated — point 4), and the
   right the app asks for to enter it, where a page already reads the table (`right_verb`; blank: the page still reads its
   right from the roles). Who prepares, reviews and reads each is not here: that is the entitlements, dims.planning_entitlement. The list is the
   example CH gave, a storage capacity beside it. Each fact belongs to one planning process (`process`, dims.ref_process —
   DEC-20261124-08): finance's three facts to financial planning, the rest to integrated business planning. */
MODEL (name dims.ref_fact, kind FULL, grain (fact), audits (fact_process_known));
WITH t AS (SELECT * FROM (VALUES
  ('demand_forecast',          'Sales demand forecast',           'material × customer × period', 'calculated', NULL, 1, 'ibp'),
  ('production_quantities',    'Production quantities',           'material × plant × period',    'calculated', NULL, 2, 'ibp'),
  ('raw_material_requirements','Raw material requirements',       'material × plant × period',    'calculated', NULL, 3, 'ibp'),
  ('inventory_targets',        'Inventory target levels',         'material × node',              'standing',   NULL, 4, 'ibp'),
  ('purchasing_quantities',    'Purchasing quantities',           'material × plant × period',    'calculated', 'register.supply_plan.maintain', 5, 'ibp'),
  ('purchase_prices',          'Material purchase prices',        'material × plant × period',    'standing',   'register.supply_plan.maintain', 6, 'ibp'),
  ('storage_capacity',         'Storage capacity',                'node × storage class',         'standing',   NULL, 7, 'ibp'),
  ('shrinkage_volume',         'Inventory shrinkage volume',      'material × node × period',     'standing',   NULL, 8, 'ibp'),
  ('shrinkage_expense',        'Inventory shrinkage expense',     'entity × period',              'calculated', NULL, 9, 'financial'),
  ('factory_headcount',        'Factory headcount',               'plant × role × period',        'standing',   NULL, 10, 'ibp'),
  ('labour_rates',             'Labour rates',                    'agreement × role',             'standing',   NULL, 11, 'ibp'),
  ('labour_productivity',      'Labour productivity',             'line × period',                'standing',   NULL, 12, 'ibp'),
  ('manufacturing_overhead',   'Manufacturing overhead forecast', 'plant × period',               'calculated', NULL, 13, 'financial'),
  ('inventory_valuation',      'Inventory valuation',             'material × plant × period',    'calculated', NULL, 14, 'financial')
) AS t (fact, fact_name, grain, kind, right_verb, ord, process))
SELECT t.*, t.process IN (SELECT process FROM dims.ref_process) AS process_known FROM t
