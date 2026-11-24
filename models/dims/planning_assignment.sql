/* Assignments (DEC-20261124-07 point 5): a role given to a person, with dates. People change; the role does not — cover
   and handover are another assignment to the same role, so a role may be held by several and a person may hold several.
   The latest row per person and role stands; ending one writes its last day. */
MODEL (name dims.planning_assignment, kind FULL, grain (person, role_no));
WITH acts AS (
  SELECT person::TEXT AS person, role_no::TEXT AS role_no, NULLIF(valid_from::TEXT, '')::DATE AS valid_from, NULLIF(valid_to::TEXT, '')::DATE AS valid_to,
         set_by::TEXT AS set_by, set_on::TEXT AS set_on, source_file, file_row_number
  FROM bronze.reg_planning_assignment
),
latest AS (SELECT * FROM acts QUALIFY ROW_NUMBER() OVER (PARTITION BY person, role_no ORDER BY set_on DESC, source_file DESC, file_row_number DESC) = 1)
SELECT l.person, l.role_no, l.valid_from, l.valid_to, l.set_by, l.set_on,
       (l.valid_from IS NULL OR l.valid_from <= CURRENT_DATE) AND (l.valid_to IS NULL OR l.valid_to >= CURRENT_DATE) AS live
FROM latest l
