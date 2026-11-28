/* The domains of each planning process: the areas of the business a role type plans in. A declared list by process —
   a domain of the same name in two processes is two domains. Set on a role type; a role and an assignment read their
   type's. */
MODEL (name dims.ref_domain, kind FULL, grain (process, domain));
SELECT * FROM (VALUES
  ('ibp',       'demand',        'Demand',                 1),
  ('ibp',       'sales',         'Sales & Commercial',     2),
  ('ibp',       'supply',        'Supply',                 3),
  ('ibp',       'manufacturing', 'Manufacturing',          4),
  ('ibp',       'procurement',   'Procurement',            5),
  ('ibp',       'inventory',     'Inventory & Logistics',  6),
  ('ibp',       'people',        'People & Workforce',     7),
  ('ibp',       'finance',       'Finance',                8),
  ('ibp',       'management',    'IBP Management',         9),
  ('financial', 'revenue',       'Sales & Revenue',        1),
  ('financial', 'cost',          'Cost & Expenditure',     2),
  ('financial', 'workforce',     'Workforce',              3),
  ('financial', 'capital',       'Capital & Investment',   4),
  ('financial', 'treasury',      'Treasury & Cash Flow',   5),
  ('financial', 'tax',           'Tax',                    6),
  ('financial', 'accounting',    'Financial Accounting',   7),
  ('financial', 'fpa',           'FP&A',                   8),
  ('financial', 'business_unit', 'Business Unit Finance',  9),
  ('financial', 'executive',     'Executive Finance',     10)
) AS t (process, domain, domain_name, ord)
