/* Why Finance's figure differs from the demand plan beneath it: the reason each save gives, so the variance can say why
   and its bias be found. BUILD is the reason where nothing feeds — Finance builds the figure itself. */
MODEL (name plan.ref_overlay_reason, kind FULL, grain (reason_code));
SELECT * FROM (VALUES
  ('RANGE_REVIEW',  'A customer range review not yet in the plan', FALSE),
  ('PRICE_TIMING',  'A price change landing earlier or later than the plan has it', FALSE),
  ('TRADE_SPEND',   'Trade spend running above or below the terms and the calendar', FALSE),
  ('CUSTOMER',      'A customer''s trading or credit position', FALSE),
  ('MARKET',        'Market or category conditions', FALSE),
  ('BUILD',         'Built by Finance — no demand plan feeds it', FALSE),
  ('OTHER',         'Anything else — the note says what', TRUE)
) AS t(reason_code, description, note_required)
