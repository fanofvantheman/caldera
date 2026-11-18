/* Which handovers a deployment keeps (DEC-20261118-04 point 6): each handover after a stage is kept unless a set-up act
   compresses it — then the stage and the next are one owner's work, one handover at the end, the steps inside running
   straight through. Adjacent only, never reordered. The latest act per stage stands; the eight, separate, are the default. */
MODEL (name plan.stage_setting, kind FULL, grain stage);
WITH acts AS (
  SELECT stage::TEXT AS stage, kept::TEXT IN ('true', 'True', '1', 'Y') AS kept, reason::TEXT AS reason, entered_by::TEXT AS entered_by,
         entered_at::TEXT AS entered_at, source_file, file_row_number
  FROM bronze.reg_stage_setting
),
latest AS (SELECT * FROM acts QUALIFY ROW_NUMBER() OVER (PARTITION BY stage ORDER BY entered_at DESC, source_file DESC, file_row_number DESC) = 1)
SELECT s.ord, s.stage, s.stage_name, COALESCE(l.kept, TRUE) OR s.ord = 8 AS handover_kept, l.reason, l.entered_by, l.entered_at
FROM dims.ref_stage s LEFT JOIN latest l USING (stage)
