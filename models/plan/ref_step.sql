/* The steps of each process (DEC-20261115-03 point 3): a process's areas, each scoped on one dimension, with the right
   that submits it (the right that enters it) and the right that accepts it or sends it back. The demand plan's step is
   its own submission (subjects `plan` and `unit`); every other step's subject is `step:<step>` in the same register of
   acts. `built` says whether there is anything yet to submit. */
MODEL (name plan.ref_step, kind FULL, grain (step));
SELECT * FROM (VALUES
  ('ibp',     1, 'demand',         'Demand',          'customer',     'plan',           'demand.plan.submit',   'review.demand.close',  TRUE),
  ('ibp',     2, 'supply',         'Supply',          'location',     'step:supply',    'delta.supply.enter',   'review.supply.close',  FALSE),
  ('ibp',     3, 'reconciliation', 'Reconciliation',  'customer',     'step:reconciliation', 'delta.allocation.enter', 'review.reconciliation.close', FALSE),
  ('finplan', 1, 'revenue',        'Revenue',         'customer',     'step:revenue',   'overlay.finance.enter', 'review.revenue.close', TRUE),
  ('finplan', 2, 'labour',         'Labour',          'organisation', 'step:labour',    'headcount.enter',      'review.labour.close',  TRUE),
  ('finplan', 3, 'opex',           'Opex',            'organisation', 'step:opex',      'schedule.line.enter',  'review.opex.close',    TRUE),
  ('finplan', 4, 'capital',        'Capital',         'organisation', 'step:capital',   'capex.project.enter',  'review.capital.close', TRUE)
) AS t (process, ord, step, step_label, dimension, subject, submit_verb, decide_verb, built)
