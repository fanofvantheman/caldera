/* Roles (DEC-20261124-07 point 4): a role type at one member of each of its dimensions, with its own number — unique,
   never reused — and a name. A role of a single type names no member. The latest row per number stands. */
MODEL (name dims.planning_role, kind FULL, grain (role_no), audits (planning_role_fits_type));
WITH acts AS (
  SELECT role_no::TEXT AS role_no, type_code::TEXT AS type_code, role_name::TEXT AS role_name, COALESCE(purpose::TEXT, '') AS purpose,
         NULLIF(site::TEXT, '') AS site, NULLIF(customer::TEXT, '') AS customer, NULLIF(cost_centre::TEXT, '') AS cost_centre,
         COALESCE(NULLIF(status::TEXT, ''), 'live') AS status, set_by::TEXT AS set_by, set_on::TEXT AS set_on, source_file, file_row_number
  FROM bronze.reg_planning_role
),
latest AS (SELECT * FROM acts QUALIFY ROW_NUMBER() OVER (PARTITION BY role_no ORDER BY set_on DESC, source_file DESC, file_row_number DESC) = 1)
SELECT l.role_no, l.type_code, l.role_name, l.purpose, l.site, l.customer, l.cost_centre, l.status = 'live' AS live, l.set_by, l.set_on,
       l.type_code IN (SELECT type_code FROM dims.planning_role_type) AS type_known,
       (SELECT t.process FROM dims.planning_role_type t WHERE t.type_code = l.type_code) AS process   -- its type's (DEC-20261124-08)
FROM latest l
