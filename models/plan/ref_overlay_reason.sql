/* Why Finance holds a view the consensus does not: the reasons an overlay entry may give. A risk or an opportunity, each
   with a reason, so what Finance adds to the plan can be read by cause and its bias found. */
MODEL (name plan.ref_overlay_reason, kind FULL, grain (reason_code));
SELECT * FROM (VALUES
  ('RANGE_REVIEW',  'A customer range review not yet in the plan', FALSE),
  ('PRICE_TIMING',  'A price change landing earlier or later than the plan has it', FALSE),
  ('TRADE_SPEND',   'Trade spend running above or below the terms and the calendar', FALSE),
  ('CUSTOMER',      'A customer''s trading or credit position', FALSE),
  ('MARKET',        'Market or category conditions', FALSE),
  ('OTHER',         'Anything else — the note says what', TRUE)
) AS t(reason_code, description, note_required)
