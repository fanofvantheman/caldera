/* A production quantity typed over the requirement (DEC-20261117-02 point 8; DEC-20261118-04 point 3): the supply plan's
   own delta, at a material × plant × period on a plan, by whoever holds the supply delta's right — an act with a reason,
   the proposal kept beside it. The latest act per cell stands; a withdrawal names an act and the proposal stands again. */
MODEL (name plan.production_act, kind FULL, grain (version_id, material_code, plant_code, period));
WITH acts AS (
  SELECT act_id::TEXT AS act_id, action::TEXT AS action, NULLIF(withdraws::TEXT, '') AS withdraws, version_id::TEXT AS version_id,
         material_code::TEXT AS material_code, plant_code::TEXT AS plant_code, period::TEXT AS period,
         TRY_CAST(NULLIF(quantity::TEXT, '') AS DOUBLE) AS quantity, reason::TEXT AS reason, entered_by::TEXT AS entered_by,
         entered_at::TEXT AS entered_at, source_file, file_row_number
  FROM bronze.reg_production_act
)
SELECT a.act_id, a.version_id, a.material_code, a.plant_code, a.period, a.quantity, a.reason, a.entered_by, a.entered_at
FROM acts a
WHERE a.action = 'set' AND a.quantity IS NOT NULL AND a.act_id NOT IN (SELECT withdraws FROM acts WHERE action = 'withdraw' AND withdraws IS NOT NULL)
QUALIFY ROW_NUMBER() OVER (PARTITION BY a.version_id, a.material_code, a.plant_code, a.period ORDER BY a.entered_at DESC, a.source_file DESC, a.file_row_number DESC) = 1
