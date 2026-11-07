/* Roles: each a bundle of actions the plan actually has. */
MODEL (name dims.ctl_role_definition, kind FULL, grain (role_code));
SELECT role_code::TEXT AS role_code, role_name::TEXT AS role_name, built_in::TEXT = 'Y' AS built_in, description::TEXT AS description
FROM bronze.ctl_role_definition
