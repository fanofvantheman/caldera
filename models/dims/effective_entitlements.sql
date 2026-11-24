/* The derived (principal, action, dimension, node, kind of plan) surface: every assignment expanded through its role's
   actions and down its hierarchy; version_kind null means held for every kind of plan. A right a planning fact names (dims.ref_fact)
   comes from the planning roles — whoever is assigned a role whose type prepares the fact — not from a role's own rights. Nothing is enforced here; faces and platforms read it. */
MODEL (name dims.effective_entitlements, kind FULL, grain (principal, action, scope_dimension, node, version_kind), audits (signal_segregation));
WITH bridges AS (
  SELECT 'material' AS scope_dimension, ancestor_code, descendant_code FROM dims.dim_material_hierarchy
  UNION ALL SELECT 'customer', ancestor_code, descendant_code FROM dims.dim_customer_hierarchy
  UNION ALL SELECT 'location', ancestor_code, descendant_code FROM dims.dim_location_hierarchy
  UNION ALL SELECT 'organisation', ancestor_code, descendant_code FROM dims.dim_organisation_hierarchy
)
SELECT DISTINCT a.principal, ra.action, a.scope_dimension, b.descendant_code AS node, a.role_code, a.version_kind
FROM dims.ctl_role_assignment a
JOIN dims.ctl_role_action ra ON ra.role_code = a.role_code
JOIN bridges b ON b.scope_dimension = a.scope_dimension AND b.ancestor_code = a.scope_node
WHERE (a.valid_to IS NULL OR a.valid_to >= CURRENT_DATE)
  AND ra.action NOT IN (SELECT right_verb FROM dims.ref_fact WHERE right_verb IS NOT NULL)
UNION
-- a right a planning fact names is held through the role architecture and nowhere else (DEC-20261124-07): by whoever
-- is assigned a role whose type prepares the fact, at the role's site and beneath (a role naming no site: everywhere)
SELECT DISTINCT pa.person, f.right_verb, 'location', b.descendant_code, pa.type_code, NULL
FROM dims.planning_authority pa
JOIN dims.ref_fact f ON f.fact = pa.fact AND f.right_verb IS NOT NULL
JOIN bridges b ON b.scope_dimension = 'location' AND b.ancestor_code = COALESCE(pa.site, 'ALL')
WHERE pa.level = 'prepare'
