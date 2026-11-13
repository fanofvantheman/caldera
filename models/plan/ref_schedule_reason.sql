/* Why a schedule figure was typed — one reason per save. */
MODEL (name plan.ref_schedule_reason, kind FULL, grain (reason_code));
SELECT * FROM (VALUES
  ('CONTRACT',  'A contract or price agreed', FALSE),
  ('ONE_OFF',   'A one-off cost in the month', FALSE),
  ('TIMING',    'Timing — the same cost in a different month', FALSE),
  ('ACTIVITY',  'More or less activity than the driver says', FALSE),
  ('METHOD',    'The driver or rate does not fit this line', FALSE),
  ('OTHER',     'Other — say what', TRUE)
) AS t(reason_code, description, note_required)
