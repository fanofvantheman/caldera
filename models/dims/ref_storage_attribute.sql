/* What each thing stored takes (DEC-20261117-03 point 2): its storage class and how many go to a pallet position.
   Finished goods: every Caldera material is ambient, its cases a pallet from its case weight at 800 kg net a position.
   Key raw materials (the only inputs with a stock): by input, a declared class and units a position — specimen figures,
   a row to change. The purchase plan holds a campaign fruit's season as one stock; it is stored processed (paste, bright
   stock), so it takes ambient positions at its fresh-fruit equivalent. A class with nothing in it is shown empty, not
   hidden — the plants declare cool and frozen rooms Caldera's plan puts nothing in. */
MODEL (name dims.ref_storage_attribute, kind FULL, grain (item_kind, item_code));
SELECT 'finished' AS item_kind, m.material_code AS item_code, 'ambient' AS storage_class,
       GREATEST(1, FLOOR(800.0 / NULLIF(m.case_net_kg, 0)))::DOUBLE AS units_per_pallet, 'cases' AS unit
FROM dims.dim_material m
UNION ALL
SELECT 'input', item_code, storage_class, units_per_pallet, unit FROM (VALUES
  ('TOMATO',    'ambient', 6.00,   't fresh — held after intake as paste in drums, about six tonnes of fruit a position'),
  ('PEACH',     'ambient', 1.00,   't fresh — held after intake as bright stock, about a tonne of fruit a position'),
  ('PEAR',      'ambient', 1.00,   't fresh — held after intake as bright stock, about a tonne of fruit a position'),
  ('SUGAR',     'ambient', 1.00,   't — bulk bags'),
  ('BEANS_DRY', 'ambient', 1.00,   't — bulk bags'),
  ('CAN_410_E', 'ambient', 9000.0, 'cans and ends'),
  ('CUP_120',   'ambient', 24000.0, 'cups with lidding')
) AS t (item_code, storage_class, units_per_pallet, unit)
