/* The table of facts against roles (DEC-20261124-06 point 2): a cell says the role *owns* the fact — enters it and
   sends it — or *receives* it once published; the latest cell set for a fact and a role stands, an empty one clears it.
   A fact has exactly one owner: the page refuses a table that fails it, and so does the run. */
MODEL (name dims.fact_role, kind FULL, grain (fact, role_code), audits (fact_one_owner, fact_role_known));
WITH acts AS (
  SELECT fact::TEXT AS fact, role_code::TEXT AS role_code, COALESCE(cell::TEXT, '') AS cell, set_by::TEXT AS set_by, set_on::TEXT AS set_on,
         source_file, file_row_number
  FROM bronze.reg_fact_role
),
latest AS (SELECT * FROM acts QUALIFY ROW_NUMBER() OVER (PARTITION BY fact, role_code ORDER BY set_on DESC, source_file DESC, file_row_number DESC) = 1)
SELECT l.fact, l.role_code, l.cell, l.set_by, l.set_on,
       l.fact IN (SELECT fact FROM dims.ref_fact) AS fact_known,
       l.role_code IN (SELECT role_code FROM dims.ctl_role_definition) AS role_known
FROM latest l WHERE l.cell IN ('owns', 'receives')
