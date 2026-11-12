/* What changed in each structure between the load before and the latest: one row per member that is new, gone, or
   changed in an attribute the plan reads — and, for a change, which attributes, from what to what. Reported, never
   repaired: the structure's owner is the client's master. */
MODEL (name dims.structure_change, kind FULL, grain (structure, member_code));
WITH mat AS (
  SELECT COALESCE(c.material_code, p.material_code)::TEXT AS member_code, COALESCE(c.material_name, p.material_name)::TEXT AS member_name,
         c.material_code IS NULL AS gone, p.material_code IS NULL AS added,
         CONCAT_WS('; ',
           CASE WHEN c.material_name::TEXT IS DISTINCT FROM p.material_name::TEXT THEN 'name: ' || p.material_name || ' → ' || c.material_name END,
           CASE WHEN c.product_code::TEXT IS DISTINCT FROM p.product_code::TEXT THEN 'product: ' || p.product_code || ' → ' || c.product_code END,
           CASE WHEN c.units_per_case::TEXT IS DISTINCT FROM p.units_per_case::TEXT THEN 'units per case: ' || p.units_per_case || ' → ' || c.units_per_case END,
           CASE WHEN c.lifecycle_status::TEXT IS DISTINCT FROM p.lifecycle_status::TEXT THEN 'lifecycle: ' || p.lifecycle_status || ' → ' || c.lifecycle_status END) AS what
  FROM bronze.dim_material c FULL OUTER JOIN bronze.prior_dim_material p ON p.material_code = c.material_code
),
ship AS (
  SELECT COALESCE(c.ship_to_code, p.ship_to_code)::TEXT, COALESCE(c.ship_to_name, p.ship_to_name)::TEXT, c.ship_to_code IS NULL, p.ship_to_code IS NULL,
         CONCAT_WS('; ',
           CASE WHEN c.account_code::TEXT IS DISTINCT FROM p.account_code::TEXT THEN 'account: ' || p.account_code || ' → ' || c.account_code END,
           CASE WHEN c.ship_to_name::TEXT IS DISTINCT FROM p.ship_to_name::TEXT THEN 'name: ' || p.ship_to_name || ' → ' || c.ship_to_name END,
           CASE WHEN c.serving_node::TEXT IS DISTINCT FROM p.serving_node::TEXT THEN 'served from: ' || p.serving_node || ' → ' || c.serving_node END)
  FROM bronze.dim_ship_to c FULL OUTER JOIN bronze.prior_dim_ship_to p ON p.ship_to_code = c.ship_to_code
),
node AS (
  SELECT COALESCE(c.node_code, p.node_code)::TEXT, COALESCE(c.node_name, p.node_name)::TEXT, c.node_code IS NULL, p.node_code IS NULL,
         CONCAT_WS('; ',
           CASE WHEN c.node_name::TEXT IS DISTINCT FROM p.node_name::TEXT THEN 'name: ' || p.node_name || ' → ' || c.node_name END,
           CASE WHEN c.status::TEXT IS DISTINCT FROM p.status::TEXT THEN 'status: ' || p.status || ' → ' || c.status END)
  FROM bronze.dim_node c FULL OUTER JOIN bronze.prior_dim_node p ON p.node_code = c.node_code
),
lane AS (
  SELECT COALESCE(c.from_node || ' → ' || c.to_code || ' · ' || c.mode, p.from_node || ' → ' || p.to_code || ' · ' || p.mode)::TEXT,
         COALESCE(c.from_node || ' → ' || c.to_code, p.from_node || ' → ' || p.to_code)::TEXT, c.from_node IS NULL, p.from_node IS NULL,
         CONCAT_WS('; ',
           CASE WHEN c.transit_days::TEXT IS DISTINCT FROM p.transit_days::TEXT THEN 'transit days: ' || p.transit_days || ' → ' || c.transit_days END,
           CASE WHEN c.cost_per_pallet::TEXT IS DISTINCT FROM p.cost_per_pallet::TEXT THEN 'cost per pallet: ' || p.cost_per_pallet || ' → ' || c.cost_per_pallet END)
  FROM bronze.ref_lane c FULL OUTER JOIN bronze.prior_ref_lane p ON p.from_node = c.from_node AND p.to_code = c.to_code AND p.mode = c.mode
),
allc AS (
  SELECT 'materials' AS structure, * FROM mat UNION ALL SELECT 'customers', * FROM ship UNION ALL SELECT 'locations', * FROM node UNION ALL SELECT 'lanes', * FROM lane
)
SELECT structure, member_code, member_name, CASE WHEN added THEN 'new' WHEN gone THEN 'gone' ELSE 'changed' END AS change,
       CASE WHEN added OR gone THEN NULL ELSE what END AS what
FROM allc WHERE added OR gone OR COALESCE(what, '') <> ''
