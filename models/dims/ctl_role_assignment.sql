/* A principal holds a role at a scope — a node on one of the hierarchies (material, customer, location, organisation) —
   for a validity window, and for a kind of plan (a budget, a forecast …; blank: every kind). The scope inherits down that
   hierarchy. ALL is every hierarchy's root. */
MODEL (name dims.ctl_role_assignment, kind FULL, grain (principal, role_code, scope_dimension, scope_node, valid_from),
       audits (role_scope_is_a_node, role_assignment_role_exists));
WITH nodes AS (
  SELECT 'material' AS scope_dimension, descendant_code AS node FROM dims.dim_material_hierarchy WHERE depth = 0
  UNION ALL SELECT 'customer', descendant_code FROM dims.dim_customer_hierarchy WHERE depth = 0
  UNION ALL SELECT 'location', descendant_code FROM dims.dim_location_hierarchy WHERE depth = 0
  UNION ALL SELECT 'organisation', descendant_code FROM dims.dim_organisation_hierarchy WHERE depth = 0
)
SELECT a.principal::TEXT AS principal, a.principal_type::TEXT AS principal_type, a.role_code::TEXT AS role_code,
       a.scope_dimension::TEXT AS scope_dimension, a.scope_node::TEXT AS scope_node,
       NULLIF(a.version_kind::TEXT, '') AS version_kind, a.valid_from::DATE AS valid_from, NULLIF(a.valid_to::TEXT, '')::DATE AS valid_to, a.assigned_by::TEXT AS assigned_by, a.assigned_on::DATE AS assigned_on,
       EXISTS (SELECT 1 FROM nodes n WHERE n.scope_dimension = a.scope_dimension AND n.node = a.scope_node) AS scope_is_node,
       EXISTS (SELECT 1 FROM dims.ctl_role_definition d WHERE d.role_code = a.role_code) AS role_exists
FROM bronze.ctl_role_assignment a
