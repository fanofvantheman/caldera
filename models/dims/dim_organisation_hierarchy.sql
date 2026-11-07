/* The organisation as a bridge over cost centres (company → function → cost centre), with self rows. The budget
   holder's scope is a node here. */
MODEL (name dims.dim_organisation_hierarchy, kind FULL, grain (ancestor_code, descendant_code), audits (hierarchy_every_member_reaches_root));
WITH RECURSIVE members AS (
  SELECT cost_centre_code AS member_code, NULLIF(parent_code, '') AS parent_code, kind AS level_name FROM bronze.dim_cost_centre
),
root AS (SELECT member_code FROM members WHERE parent_code IS NULL),
paths AS (
  SELECT member_code AS descendant_code, member_code AS ancestor_code, 0 AS depth FROM members
  UNION ALL
  SELECT p.descendant_code, m.parent_code, p.depth + 1 FROM paths p JOIN members m ON m.member_code = p.ancestor_code WHERE m.parent_code IS NOT NULL
)
SELECT p.ancestor_code::TEXT AS ancestor_code, p.descendant_code::TEXT AS descendant_code, p.depth::INT AS depth,
       a.level_name::TEXT AS ancestor_level, d.level_name::TEXT AS descendant_level,
       NOT EXISTS (SELECT 1 FROM members c WHERE c.parent_code = d.member_code) AS descendant_is_leaf,
       BOOL_OR(p.ancestor_code IN (SELECT member_code FROM root)) OVER (PARTITION BY p.descendant_code) AS reaches_root
FROM paths p JOIN members a ON a.member_code = p.ancestor_code JOIN members d ON d.member_code = p.descendant_code
