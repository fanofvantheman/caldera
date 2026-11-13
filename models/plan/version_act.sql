/* Closing and reopening a version: one row per act, in the order taken — who, when, why. A version's state is read from
   this register (plan.version_state), never edited in place; the face places an act as a file in the landing and the
   generator writes the acts the business took before the build began. */
MODEL (name plan.version_act, kind FULL, grain (act_id));
SELECT a.act_id::TEXT AS act_id, a.version_id::TEXT AS version_id, a."act"::TEXT AS "act", NULLIF(a.reason::TEXT, '') AS reason,
       a.entered_by::TEXT AS entered_by, a.entered_on::TEXT AS entered_on,
       CASE WHEN a.source_file LIKE '20%' THEN a.source_file END AS placed_by_file, a.file_row_number
FROM bronze.reg_version_act a
