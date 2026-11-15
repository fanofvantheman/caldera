/* Which plant a factory cost centre's costs are the overhead of, and whether it is a production hall (whose positions are
   the crews' — the direct labour rate is read there) or a support centre. Quality is split by entity: each entity runs
   one plant. Logistics is distribution — outbound freight and storage after the plant, below gross margin — and is the
   overhead of no plant. */
MODEL (name plan.ref_cost_centre_plant, kind FULL, grain (entity_code, cost_centre_code));
SELECT * FROM (VALUES
  ('CF',  'CC_E_FRUIT', 'ECH', 'production'), ('CF', 'CC_E_TOM', 'ECH', 'production'), ('CF', 'CC_E_BEANS', 'ECH', 'production'),
  ('CF',  'CC_E_SPRD',  'ECH', 'production'), ('CF', 'CC_E_MAINT', 'ECH', 'support'),  ('CF', 'CC_E_WHSE', 'ECH', 'support'),
  ('CF',  'CC_QA',      'ECH', 'support'),
  ('RBF', 'CC_L_PROD',  'LOX', 'production'), ('RBF', 'CC_L_MAINT', 'LOX', 'support'), ('RBF', 'CC_L_WHSE', 'LOX', 'support'),
  ('RBF', 'CC_QA',      'LOX', 'support')
) AS t (entity_code, cost_centre_code, plant_code, role)
