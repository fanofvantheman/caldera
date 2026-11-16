/* The key raw materials (DEC-20261116-04 point 1): the few inputs whose price or availability moves the cost of a case,
   declared input by input at the plant that draws them — each with how it is bought (contract: a price fixed, or tied to
   an index, for its term; spot: the price in force with its index; campaign intake: bought in the input's campaign window
   for the year's requirement), the cover a purchase keeps (periods of the next period's requirement), and the stock on
   hand when a plan opens and its cost against the price in force — periods of requirement for a contract or spot material;
   a campaign material opens with what it needs until its window, 5% over (opening_periods is not read for it). Every other input has no stock
   and no purchase line and is valued at its price in force. Specimen figures: Caldera loads no contracts and no stock
   balance — a declared stand-in, not a client's value. */
MODEL (name dims.ref_key_material, kind FULL, grain (input_code, plant_code));
SELECT * FROM (VALUES
  ('TOMATO',    'ECH', 'campaign', 0.0, NULL,  NULL,        NULL,      3.2, 1.06, 'grower contracts settled at intake; last season''s pack dearer'),
  ('PEACH',     'LOX', 'campaign', 0.0, NULL,  NULL,        NULL,      2.2, 0.97, 'intake January to March'),
  ('PEACH',     'ECH', 'campaign', 0.0, NULL,  NULL,        NULL,      2.2, 0.97, 'intake January to March'),
  ('PEAR',      'ECH', 'campaign', 0.0, NULL,  NULL,        NULL,      3.2, 1.02, 'intake February to April'),
  ('PEAR',      'LOX', 'campaign', 0.0, NULL,  NULL,        NULL,      3.2, 1.02, 'intake February to April'),
  ('SUGAR',     'ECH', 'contract', 1.0, 870.0, 'SUGAR_IDX', '2028P06', 1.5, 1.01, 'annual supply contract tied to the sugar index'),
  ('SUGAR',     'LOX', 'contract', 1.0, 870.0, 'SUGAR_IDX', '2028P06', 1.5, 1.01, 'annual supply contract tied to the sugar index'),
  ('BEANS_DRY', 'ECH', 'contract', 2.0, 1360.0, NULL,       '2027P12', 2.5, 1.04, 'fixed-price contract to December; spot after it'),
  ('CAN_410_E', 'ECH', 'contract', 1.0, 0.048, NULL,        '2028P06', 1.0, 1.00, 'can supply agreement, fixed for the year'),
  ('CAN_410_E', 'LOX', 'contract', 1.0, 0.048, NULL,        '2028P06', 1.0, 1.00, 'can supply agreement, fixed for the year'),
  ('CUP_120',   'LOX', 'spot',     1.5, NULL,  NULL,        NULL,      1.5, 1.05, 'imported cups bought spot, landed, with the resin index')
) AS t (input_code, plant_code, source, cover_periods, contract_price, contract_index, contract_through, opening_periods, opening_cost_factor, note)
