/* How the facts stand to one another (DEC-20261124-06 points 3–4): a fact *uses* another — it is calculated from it and
   cannot be run without it, so it waits for it — or is *reconciled_with* another — each set on its own, compared, a
   difference an alert to both owners and nothing waiting. Order is here and nowhere else: a role is upstream of another
   only through the facts it owns. A loop of uses is refused. */
MODEL (name dims.ref_fact_relation, kind FULL, grain (fact, relation, other_fact), audits (fact_relation_known, fact_uses_no_loop));
WITH r AS (SELECT * FROM (VALUES
  ('production_quantities',     'uses', 'demand_forecast'),
  ('production_quantities',     'uses', 'inventory_targets'),
  ('raw_material_requirements', 'uses', 'production_quantities'),
  ('purchasing_quantities',     'uses', 'raw_material_requirements'),
  ('purchasing_quantities',     'uses', 'inventory_targets'),
  ('purchasing_quantities',     'reconciled_with', 'storage_capacity'),
  ('production_quantities',     'reconciled_with', 'storage_capacity'),
  ('production_quantities',     'reconciled_with', 'factory_headcount'),
  ('shrinkage_expense',         'uses', 'shrinkage_volume'),
  ('shrinkage_expense',         'uses', 'inventory_valuation'),
  ('manufacturing_overhead',    'uses', 'factory_headcount'),
  ('manufacturing_overhead',    'uses', 'labour_rates'),
  ('manufacturing_overhead',    'uses', 'labour_productivity'),
  ('manufacturing_overhead',    'uses', 'production_quantities'),
  ('inventory_valuation',       'uses', 'purchasing_quantities'),
  ('inventory_valuation',       'uses', 'purchase_prices'),
  ('inventory_valuation',       'uses', 'production_quantities')
) AS t (fact, relation, other_fact))
SELECT r.*, r.fact IN (SELECT fact FROM dims.ref_fact) AND r.other_fact IN (SELECT fact FROM dims.ref_fact) AS facts_known FROM r
