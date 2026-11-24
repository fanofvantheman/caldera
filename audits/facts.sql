AUDIT (name fact_relation_known);
/* blocking: a relation between facts the list does not have, or of a kind that is neither */
SELECT fact, relation, other_fact FROM @this_model WHERE NOT facts_known OR relation NOT IN ('uses', 'reconciled_with') OR fact = other_fact;

AUDIT (name fact_uses_no_loop);
/* blocking: two facts each using the other, directly or through others — neither could ever run first */
WITH RECURSIVE reach (fact, other_fact, depth) AS (
  SELECT fact, other_fact, 1 FROM @this_model WHERE relation = 'uses'
  UNION
  SELECT r.fact, m.other_fact, r.depth + 1 FROM reach r JOIN @this_model m ON m.fact = r.other_fact AND m.relation = 'uses' WHERE r.depth < 40
)
SELECT DISTINCT fact FROM reach WHERE fact = other_fact;

AUDIT (name planning_one_preparer);
/* blocking: exactly one role type prepares a fact (DEC-20261124-07 point 2) — with two it has two owners, with none nobody answers for it */
SELECT f.fact, COUNT(m.type_code) AS preparers FROM dims.ref_fact f LEFT JOIN @this_model m ON m.fact = f.fact AND m.level = 'prepare'
GROUP BY f.fact HAVING COUNT(m.type_code) <> 1;

AUDIT (name planning_entitlement_known);
/* blocking: an entitlement for a fact or a role type the plan does not have */
SELECT fact, type_code FROM @this_model WHERE NOT fact_known OR NOT type_known;

AUDIT (name planning_role_fits_type);
/* blocking: a role of a type the plan does not have; a second live role of a Single type; or two live roles of a type at the same place */
SELECT role_no FROM @this_model r WHERE live AND (
      NOT type_known
   OR (SELECT COUNT(*) FROM @this_model x WHERE x.live AND x.type_code = r.type_code
         AND COALESCE(x.site, '') = COALESCE(r.site, '') AND COALESCE(x.customer, '') = COALESCE(r.customer, '') AND COALESCE(x.cost_centre, '') = COALESCE(r.cost_centre, '')) > 1);

AUDIT (name planning_entitlement_one_process);
/* blocking: an entitlement across a process boundary — a fact of one planning process and a role type of another (DEC-20261124-08 point 5) */
SELECT fact, type_code, process, type_process FROM @this_model WHERE fact_known AND type_known AND process IS DISTINCT FROM type_process;

AUDIT (name fact_process_known);
/* blocking: a planning fact of no process, or of one the list does not have */
SELECT fact, process FROM @this_model WHERE process IS NULL OR NOT process_known;

AUDIT (name planning_type_process_known);
/* blocking: a role type of a process the list does not have */
SELECT type_code, process FROM @this_model WHERE NOT process_known;
