/* The customer hierarchy as a bridge: ALL → account → ship-to, with self rows. Channel is an alternate rollup over
   accounts, read as an attribute, not a second tree. */
MODEL (name dims.dim_customer_hierarchy, kind FULL, grain (ancestor_code, descendant_code), audits (hierarchy_every_member_reaches_root));
WITH RECURSIVE members AS (
  SELECT 'ALL' AS member_code, NULL AS parent_code, 'all' AS level_name, 0 AS level_no
  UNION ALL SELECT account_code, 'ALL', 'account', 1 FROM bronze.dim_account
  UNION ALL SELECT ship_to_code, account_code, 'ship_to', 2 FROM bronze.dim_ship_to
),
paths AS (
  SELECT member_code AS descendant_code, member_code AS ancestor_code, 0 AS depth FROM members
  UNION ALL
  SELECT p.descendant_code, m.parent_code, p.depth + 1 FROM paths p JOIN members m ON m.member_code = p.ancestor_code WHERE m.parent_code IS NOT NULL
)
SELECT p.ancestor_code::TEXT AS ancestor_code, p.descendant_code::TEXT AS descendant_code, p.depth::INT AS depth,
       a.level_name::TEXT AS ancestor_level, d.level_name::TEXT AS descendant_level, d.level_no = 2 AS descendant_is_leaf,
       BOOL_OR(p.ancestor_code = 'ALL') OVER (PARTITION BY p.descendant_code) AS reaches_root
FROM paths p JOIN members a ON a.member_code = p.ancestor_code JOIN members d ON d.member_code = p.descendant_code
