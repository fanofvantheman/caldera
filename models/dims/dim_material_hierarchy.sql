/* The material hierarchy as a bridge: ALL → category → product → material (variants under their parent material),
   every ancestor–descendant pair plus a self row for every member, so a reading at any node sums its leaves and every
   leaf is judged for reaching the root. */
MODEL (name dims.dim_material_hierarchy, kind FULL, grain (ancestor_code, descendant_code), audits (hierarchy_every_member_reaches_root));
WITH RECURSIVE members AS (
  SELECT 'ALL' AS member_code, NULL AS parent_code, 'all' AS level_name, 0 AS level_no
  UNION ALL SELECT category_code, 'ALL', 'category', 1 FROM bronze.dim_category
  UNION ALL SELECT product_code, category_code, 'product', 2 FROM bronze.dim_product
  UNION ALL SELECT material_code, COALESCE(NULLIF(parent_material, ''), product_code), 'material', 3 FROM bronze.dim_material
),
paths AS (
  SELECT member_code AS descendant_code, member_code AS ancestor_code, 0 AS depth, level_no AS descendant_level
  FROM members
  UNION ALL
  SELECT p.descendant_code, m.parent_code, p.depth + 1, p.descendant_level
  FROM paths p JOIN members m ON m.member_code = p.ancestor_code
  WHERE m.parent_code IS NOT NULL
)
SELECT p.ancestor_code::TEXT AS ancestor_code, p.descendant_code::TEXT AS descendant_code, p.depth::INT AS depth,
       a.level_name::TEXT AS ancestor_level, d.level_name::TEXT AS descendant_level,
       d.level_no = 3 AS descendant_is_leaf,
       BOOL_OR(p.ancestor_code = 'ALL') OVER (PARTITION BY p.descendant_code) AS reaches_root
FROM paths p
JOIN members a ON a.member_code = p.ancestor_code
JOIN members d ON d.member_code = p.descendant_code
