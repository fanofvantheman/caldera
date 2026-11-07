/* The location hierarchy as a bridge: ALL → node → (plant) area → line, with self rows. Capacity kinds attach at
   different levels of it: machine at line, labour at area or plant, storage at node. */
MODEL (name dims.dim_location_hierarchy, kind FULL, grain (ancestor_code, descendant_code), audits (hierarchy_every_member_reaches_root));
WITH RECURSIVE members AS (
  SELECT 'ALL' AS member_code, NULL AS parent_code, 'all' AS level_name, 0 AS level_no
  UNION ALL SELECT node_code, 'ALL', 'node', 1 FROM bronze.dim_node
  UNION ALL SELECT area_code, plant_code, 'area', 2 FROM bronze.dim_plant_area
  UNION ALL SELECT line_code, area_code, 'line', 3 FROM bronze.dim_line
),
paths AS (
  SELECT member_code AS descendant_code, member_code AS ancestor_code, 0 AS depth FROM members
  UNION ALL
  SELECT p.descendant_code, m.parent_code, p.depth + 1 FROM paths p JOIN members m ON m.member_code = p.ancestor_code WHERE m.parent_code IS NOT NULL
)
SELECT p.ancestor_code::TEXT AS ancestor_code, p.descendant_code::TEXT AS descendant_code, p.depth::INT AS depth,
       a.level_name::TEXT AS ancestor_level, d.level_name::TEXT AS descendant_level,
       NOT EXISTS (SELECT 1 FROM members c WHERE c.parent_code = d.member_code) AS descendant_is_leaf,
       BOOL_OR(p.ancestor_code = 'ALL') OVER (PARTITION BY p.descendant_code) AS reaches_root
FROM paths p JOIN members a ON a.member_code = p.ancestor_code JOIN members d ON d.member_code = p.descendant_code
