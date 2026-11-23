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

AUDIT (name fact_one_owner);
/* blocking: a fact has exactly one owner (DEC-20261124-06 point 2) — with two it has two numbers, with none nobody answers for it */
SELECT f.fact, COUNT(m.role_code) AS owners FROM dims.ref_fact f LEFT JOIN @this_model m ON m.fact = f.fact AND m.cell = 'owns'
GROUP BY f.fact HAVING COUNT(m.role_code) <> 1;

AUDIT (name fact_role_known);
/* blocking: a cell for a fact or a role the plan does not have */
SELECT fact, role_code FROM @this_model WHERE NOT fact_known OR NOT role_known;
