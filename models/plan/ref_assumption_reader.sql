/* What reads each assumption: one row per assumption × the calculation that uses it, how it uses it, and whether that
   calculation is built. Shown on the assumptions page beside each assumption, so a person changing one sees what will
   move before they save; an assumption with no row here is read by nothing, and the page says so. Kept by hand beside the
   calculations it names — a calculation that starts reading an assumption adds its row. */
MODEL (name plan.ref_assumption_reader, kind FULL, grain (assumption_code, reader));
SELECT * FROM (VALUES
  ('FX_AUDUSD',    'export prices', 'The plan valued', 'plan.money', NULL,
   'a list price in US dollars ÷ AUD/USD in force in the period of the sale', TRUE),
  ('RETURNS_RATE', 'gross-to-net: returns', 'The plan valued', 'plan.money', NULL,
   'returns and ullage = invoice value × the rate in force in the period', TRUE),
  ('CLAIMS_RATE',  'gross-to-net: claims', 'The plan valued', 'plan.money', NULL,
   'shortage and damage claims = invoice value × the rate in force in the period', TRUE),
  ('CPI',          'opex schedule: last year', 'Opex schedule', 'plan.schedule', NULL,
   'every line on last year: rate = 1 + CPI in force at the first period the schedule plans — one index for its twelve periods', TRUE),
  ('ENERGY_IDX',   'standard: energy', 'Standard by plant', 'plan.rung', 'standard',
   'the standard cost of the input materials linked to the index', FALSE),
  ('TINPLATE_IDX', 'standard: tinplate', 'Standard by plant', 'plan.rung', 'standard',
   'the standard cost of the input materials linked to the index', FALSE),
  ('RESIN_IDX',    'standard: resin', 'Standard by plant', 'plan.rung', 'standard',
   'the standard cost of the input materials linked to the index', FALSE),
  ('SUGAR_IDX',    'standard: sugar', 'Standard by plant', 'plan.rung', 'standard',
   'the standard cost of the input materials linked to the index', FALSE)
) AS t(assumption_code, reader, page_label, page, page_slug, how, built)
