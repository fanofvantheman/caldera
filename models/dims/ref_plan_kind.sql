/* The plans that feed the IBP plan (DEC-20261124-05 point 3): a row per kind of plan — its name, the IBP stage it feeds
   (dims.ref_stage), the right whose holders own a plan of the kind (the build composes roles from rights), and whether
   what it owns is taken by copy, unasked, or by request (DEC-20261121-01 point 5). The IBP plan is not a kind: it owns no
   key figure; it holds what was sent to it and published in it (point 4). A kind gains its row when it is built (point 6). */
MODEL (name dims.ref_plan_kind, kind FULL, grain (plan_kind));
SELECT * FROM (VALUES
  ('purchasing', 'Purchasing plan', 'materials', 'register.supply_plan.maintain', 'copy', 'purchasing')
) AS t (plan_kind, plan_kind_name, stage, owner_verb, taken_by, submitter)
