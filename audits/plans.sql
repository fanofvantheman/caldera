AUDIT (name plan_figure_one_owner);
/* blocking: a key figure has exactly one owning plan (DEC-20261124-05 point 2) — owned by two, it has two numbers */
SELECT key_figure, COUNT(*) AS owners FROM @this_model WHERE relation = 'owns' GROUP BY key_figure HAVING COUNT(*) > 1;

AUDIT (name plan_figure_read_from_owner);
/* blocking: a figure read from a plan kind is read from the kind that owns it; a kind does not read what it owns; a
   figure is read from a plan kind, an IBP stage, the record or the IBP plan's assumption */
SELECT r.plan_kind, r.key_figure, r.read_from FROM @this_model r
WHERE r.relation = 'reads' AND (
      (r.read_from_plan AND NOT EXISTS (SELECT 1 FROM @this_model o WHERE o.relation = 'owns' AND o.plan_kind = r.read_from AND o.key_figure = r.key_figure))
   OR EXISTS (SELECT 1 FROM @this_model o WHERE o.relation = 'owns' AND o.plan_kind = r.plan_kind AND o.key_figure = r.key_figure)
   OR NOT r.read_from_known);

AUDIT (name plan_figure_kind_known);
/* blocking: a row for a plan kind the list does not have, or a relation that is neither */
SELECT plan_kind, key_figure, relation FROM @this_model WHERE NOT kind_known OR relation NOT IN ('owns', 'reads');
