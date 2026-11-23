/* The key figures each plan owns and reads (DEC-20261124-05 points 1–2, 6): a row per plan kind and key figure — its
   grain, whether the kind owns it (typed there, sent from there) or reads it (a copy taken in), and for a figure read,
   where from: a plan kind that owns it, an IBP stage no plan kind is built for yet, `record` (the actuals at the plan's
   close) or `assumption` (the IBP plan's assumption, the price in force — not managed by any plan, DEC-20261121-01 point
   11). `fields` is what a send carries and a seed takes back, for a figure owned. A key figure has exactly one owning
   plan; the audits refuse a list that fails it. */
MODEL (name dims.ref_plan_figure, kind FULL, grain (plan_kind, key_figure), audits (plan_figure_one_owner, plan_figure_read_from_owner, plan_figure_kind_known));
WITH f AS (SELECT * FROM (VALUES
  ('purchasing', 'additional_receipts', 'additional receipts', 'material × plant × period', 'owns',  NULL,         'quantity, price, note', 1),
  ('purchasing', 'consumption',         'consumption',         'material × plant × period', 'reads', 'production', NULL,                    2),
  ('purchasing', 'price_in_force',      'price in force',      'material × period',         'reads', 'assumption', NULL,                    3),
  ('purchasing', 'contracted_receipts', 'contracted receipts', 'material × plant × period', 'reads', 'record',     NULL,                    4),
  ('purchasing', 'opening_stock',       'opening stock',       'material × plant',          'reads', 'record',     NULL,                    5)
) AS t (plan_kind, key_figure, figure_name, grain, relation, read_from, fields, ord))
SELECT f.*, f.plan_kind IN (SELECT plan_kind FROM dims.ref_plan_kind) AS kind_known,
       f.read_from IN (SELECT plan_kind FROM dims.ref_plan_kind) AS read_from_plan,
       f.read_from IN (SELECT plan_kind FROM dims.ref_plan_kind) OR f.read_from IN (SELECT stage FROM dims.ref_stage) OR f.read_from IN ('record', 'assumption') AS read_from_known
FROM f
