/* Role types (DEC-20261124-07 point 1): the kinds of job an organisation plans with. Each says its cardinality — single,
   one role for the whole business, or multiple — and, when multiple, the level of each dimension that tells its roles
   apart (blank: not a dimension of the type). Each type belongs to one planning process (DEC-20261124-08) — a type with
   none said is integrated business planning; types of the same name in two processes are two types. The latest row per
   type stands. */
MODEL (name dims.planning_role_type, kind FULL, grain (type_code), audits (planning_type_process_known));
WITH acts AS (
  SELECT type_code::TEXT AS type_code, type_name::TEXT AS type_name, COALESCE(purpose::TEXT, '') AS purpose, cardinality::TEXT AS cardinality,
         NULLIF(site_level::TEXT, '') AS site_level, NULLIF(customer_level::TEXT, '') AS customer_level, NULLIF(cost_centre_level::TEXT, '') AS cost_centre_level,
         COALESCE(NULLIF(process::TEXT, ''), 'ibp') AS process, set_by::TEXT AS set_by, set_on::TEXT AS set_on, source_file, file_row_number
  FROM bronze.reg_role_type
)
SELECT type_code, type_name, purpose, cardinality, site_level, customer_level, cost_centre_level, process, set_by, set_on,
       process IN (SELECT process FROM dims.ref_process) AS process_known
FROM acts QUALIFY ROW_NUMBER() OVER (PARTITION BY type_code ORDER BY set_on DESC, source_file DESC, file_row_number DESC) = 1
