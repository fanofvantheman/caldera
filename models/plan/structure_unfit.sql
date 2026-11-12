/* Members of the plan's structures not yet fit to plan: each with what it lacks and the role that owns the fix. A
   material with no price on any list cannot be valued; with no route it cannot be made or costed; with no product above
   it it rolls nowhere; an account with no ship-to cannot be shipped to. Read, never repaired — the page says whom to ask. */
MODEL (name plan.structure_unfit, kind FULL, grain (structure, member_code, lacks));
WITH priced AS (SELECT DISTINCT material_code FROM history.price_list),
routed AS (SELECT DISTINCT material_code FROM dims.ref_route),
products AS (SELECT DISTINCT product_code FROM bronze.dim_product),
gaps AS (
  SELECT 'materials' AS structure, m.material_code AS member_code, m.material_name AS member_name, m.lifecycle_status AS note,
         'a price on a list' AS lacks, 'register.price_list.maintain' AS owner_verb
  FROM dims.dim_material m WHERE m.material_code NOT IN (SELECT material_code FROM priced)
  UNION ALL
  SELECT 'materials', m.material_code, m.material_name, m.lifecycle_status, 'a route at a plant', 'register.routes.maintain'
  FROM dims.dim_material m WHERE m.material_code NOT IN (SELECT material_code FROM routed)
  UNION ALL
  SELECT 'materials', m.material_code, m.material_name, m.lifecycle_status, 'a product above it', 'structure.material.maintain'
  FROM dims.dim_material m WHERE m.product_code IS NULL OR m.product_code NOT IN (SELECT product_code FROM products)
  UNION ALL
  SELECT 'customers', a.account_code, a.account_name, a.channel, 'a ship-to', 'structure.customer.maintain'
  FROM dims.dim_account a WHERE a.account_code NOT IN (SELECT account_code FROM dims.dim_ship_to)
)
SELECT g.*, (SELECT STRING_AGG(DISTINCT e.principal, ', ' ORDER BY e.principal) FROM dims.effective_entitlements e WHERE e.action = g.owner_verb) AS owners
FROM gaps g
