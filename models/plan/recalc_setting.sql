/* How the models after an override or a port are recalculated (DEC-20261119-01 point 5): automatic — placing it runs
   every model after it at once — or manual — the stages after it are marked behind and recalculated when someone asks.
   One setting for every Plan, kept by the plan administrator beside the compression of stages, as acts; the latest act
   stands; manual until one is taken. */
MODEL (name plan.recalc_setting, kind FULL, grain mode);
WITH acts AS (
  SELECT act_id::TEXT AS act_id, mode::TEXT AS mode, reason::TEXT AS reason, entered_by::TEXT AS entered_by, entered_at::TEXT AS entered_at,
         source_file, file_row_number
  FROM bronze.reg_recalc_setting WHERE mode::TEXT IN ('automatic', 'manual')
),
latest AS (SELECT * FROM acts QUALIFY ROW_NUMBER() OVER (ORDER BY entered_at DESC, source_file DESC, file_row_number DESC) = 1)
SELECT COALESCE(l.mode, 'manual') AS mode, l.reason, l.entered_by, l.entered_at, l.act_id
FROM (SELECT 1) d LEFT JOIN latest l ON TRUE
