/* Storage capacity (DEC-20261117-03 points 1, 6): pallet positions by node × storage class × tier — own, then overflow at
   a rate a pallet a week (capacities.md: the tier's step is the cost of running out of room) — and each node's working
   limit, the share of its own positions past which a store is full enough to hurt, shown as a line, never priced.
   Specimen figures: Caldera loads no warehouse register. A class a node does not declare holds nothing. */
MODEL (name dims.ref_storage_capacity, kind FULL, grain (node_code, storage_class, tier));
SELECT * FROM (VALUES
  ('ECH', 'ambient', 'own',      9000, NULL, 0.85),
  ('ECH', 'ambient', 'overflow', 4000, 3.20, 0.85),
  ('ECH', 'chilled', 'own',      600, NULL, 0.85),
  ('ECH', 'chilled', 'overflow', 1500, 6.50, 0.85),
  ('ECH', 'frozen',  'own',      150, NULL, 0.85),
  ('LOX', 'ambient', 'own',      11000, NULL, 0.85),
  ('LOX', 'ambient', 'overflow', 3000, 3.20, 0.85),
  ('LOX', 'chilled', 'own',      400, NULL, 0.85),
  ('LOX', 'chilled', 'overflow', 1000, 6.50, 0.85),
  ('MEL', 'ambient', 'own',      950, NULL, 0.90),
  ('MEL', 'ambient', 'overflow', 3000, 2.80, 0.90),
  ('SYD', 'ambient', 'own',      950, NULL, 0.90),
  ('SYD', 'ambient', 'overflow', 3000, 2.80, 0.90),
  ('BNE', 'ambient', 'own',      420, NULL, 0.90),
  ('BNE', 'ambient', 'overflow', 2000, 2.80, 0.90)
) AS t (node_code, storage_class, tier, pallets, rate_per_pallet_week, working_limit)
