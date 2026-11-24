/* Entitlements (DEC-20261124-07 point 2): the authority a role type has over a planning fact — read (uses it once
   published), review (also sees it once sent) or prepare (also enters it and sends it), each including the one before.
   Set on the type, never on a role. Exactly one type prepares a fact. The latest cell per fact and type stands; an empty
   one clears it. An entitlement joins a fact and a role type of the same process (DEC-20261124-08 point 5): across a process
   boundary there is none. */
MODEL (name dims.planning_entitlement, kind FULL, grain (fact, type_code), audits (planning_one_preparer, planning_entitlement_known, planning_entitlement_one_process));
WITH acts AS (
  SELECT fact::TEXT AS fact, type_code::TEXT AS type_code, COALESCE(level::TEXT, '') AS level, set_by::TEXT AS set_by, set_on::TEXT AS set_on,
         source_file, file_row_number
  FROM bronze.reg_planning_entitlement
),
latest AS (SELECT * FROM acts QUALIFY ROW_NUMBER() OVER (PARTITION BY fact, type_code ORDER BY set_on DESC, source_file DESC, file_row_number DESC) = 1)
SELECT l.fact, l.type_code, l.level, l.set_by, l.set_on,
       l.fact IN (SELECT fact FROM dims.ref_fact) AS fact_known,
       l.type_code IN (SELECT type_code FROM dims.planning_role_type) AS type_known,
       f.process AS process, t.process AS type_process
FROM latest l LEFT JOIN dims.ref_fact f ON f.fact = l.fact LEFT JOIN dims.planning_role_type t ON t.type_code = l.type_code WHERE l.level IN ('read', 'review', 'prepare')
