/* The cost pools: a short set, declared before any ledger is read, each a named kind of factory cost belonging to exactly
   one of the four components of a case's cost (DEC-20261116-03). A pool is where a rate is set and read. Material pools
   are read from the input's type, never mapped from a ledger; the rest are reached through the map of cost centre ×
   account (plan.cost_pool_map). A deployment may add a pool beneath a component; it may not add a component or put a
   pool in two. NOT_COGS is the map's other answer: distribution, selling and administration, below gross margin. */
MODEL (name dims.ref_cost_pool, kind FULL, grain pool_code);
SELECT * FROM (VALUES
  ('INGREDIENTS',     'Ingredients',                  'material',          'ingredient', 'the bill × the price of each ingredient',                          10),
  ('PACKAGING',       'Packaging',                    'material',          'packaging',  'the bill × the price of each pack component',                       11),
  ('DIRECT_LABOUR',   'Direct labour',                'labour',            NULL,         'the route''s crew hours × the loaded rate',                          20),
  ('PROCESS_ENERGY',  'Process energy',               'variable_overhead', NULL,         'a rate per case made at the plant',                                  30),
  ('CONSUMABLES',     'Production consumables',       'variable_overhead', NULL,         'a rate per case made at the plant',                                  31),
  ('VAR_HANDLING',    'Variable handling',            'variable_overhead', NULL,         'a rate per case made at the plant',                                  32),
  ('INDIRECT_LABOUR', 'Indirect labour',              'fixed_overhead',    NULL,         'the cost for the year ÷ the planned cases at the plant',             40),
  ('MAINTENANCE',     'Maintenance',                  'fixed_overhead',    NULL,         'the cost for the year ÷ the planned cases at the plant',             41),
  ('DEPN_LEASES',     'Depreciation and leases',      'fixed_overhead',    NULL,         'the cost for the year ÷ the planned cases at the plant',             42),
  ('SITE_ENERGY',     'Site energy and occupancy',    'fixed_overhead',    NULL,         'the cost for the year ÷ the planned cases at the plant',             43),
  ('QUALITY',         'Quality',                      'fixed_overhead',    NULL,         'the cost for the year ÷ the planned cases at the plant',             44),
  ('OTHER_FACTORY',   'Other factory',                'fixed_overhead',    NULL,         'the cost for the year ÷ the planned cases at the plant',             45),
  ('NOT_COGS',        'Not in cost of goods',         NULL,                NULL,         'below gross margin: distribution, selling, administration',          90)
) AS t (pool_code, pool_name, component, input_type, reaches, sort_order)
