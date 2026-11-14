/* Roles: each a named set of the rights the plan has. The shipped set, and beside it the client's own — composed from the
   same rights (plan/reg_role, the latest composition of a role standing), marked as its own and held to the same audits. */
MODEL (name dims.ctl_role_definition, kind FULL, grain (role_code));
WITH own AS (
  SELECT role_code::TEXT AS role_code, ANY_VALUE(role_name::TEXT) AS role_name, ANY_VALUE(description::TEXT) AS description,
         ANY_VALUE(composed_by::TEXT) AS composed_by, MAX(composed_on::TEXT) AS composed_on
  FROM bronze.reg_role r
  WHERE (CASE WHEN source_file LIKE '20%' THEN source_file ELSE '0' END) = (SELECT MAX(CASE WHEN x.source_file LIKE '20%' THEN x.source_file ELSE '0' END) FROM bronze.reg_role x WHERE x.role_code = r.role_code)
  GROUP BY 1
)
SELECT role_code::TEXT AS role_code, role_name::TEXT AS role_name, built_in::TEXT = 'Y' AS built_in, description::TEXT AS description,
       FALSE AS own, NULL::TEXT AS composed_by, NULL::TEXT AS composed_on
FROM bronze.ctl_role_definition
UNION ALL
SELECT role_code, role_name, FALSE, description, TRUE, composed_by, composed_on FROM own
WHERE role_code NOT IN (SELECT role_code::TEXT FROM bronze.ctl_role_definition)
