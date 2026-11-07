/* The derived (principal, action, dimension, node) surface: every assignment expanded through its role's actions and down
   its hierarchy. Nothing is enforced here; faces and platforms read it. */
MODEL (name dims.effective_entitlements, kind FULL, grain (principal, action, scope_dimension, node), audits (signal_segregation));
WITH bridges AS (
  SELECT 'material' AS scope_dimension, ancestor_code, descendant_code FROM dims.dim_material_hierarchy
  UNION ALL SELECT 'customer', ancestor_code, descendant_code FROM dims.dim_customer_hierarchy
  UNION ALL SELECT 'location', ancestor_code, descendant_code FROM dims.dim_location_hierarchy
  UNION ALL SELECT 'organisation', ancestor_code, descendant_code FROM dims.dim_organisation_hierarchy
)
SELECT DISTINCT a.principal, ra.action, a.scope_dimension, b.descendant_code AS node, a.role_code
FROM dims.ctl_role_assignment a
JOIN dims.ctl_role_action ra ON ra.role_code = a.role_code
JOIN bridges b ON b.scope_dimension = a.scope_dimension AND b.ancestor_code = a.scope_node
WHERE a.valid_to IS NULL OR a.valid_to >= CURRENT_DATE
