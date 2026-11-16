/* A buyer's acts on the purchase plan (DEC-20261116-04 point 3): a quantity or a price typed over the calculated one at
   a key material × plant × period on a plan — the latest act per cell stands; a withdrawal names an act and takes it out,
   and the one before it stands again. */
MODEL (name plan.purchase_act, kind FULL, grain (version_id, input_code, plant_code, period));
WITH acts AS (
  SELECT act_id::TEXT AS act_id, action::TEXT AS action, NULLIF(withdraws::TEXT, '') AS withdraws, version_id::TEXT AS version_id,
         input_code::TEXT AS input_code, plant_code::TEXT AS plant_code, period::TEXT AS period,
         TRY_CAST(NULLIF(quantity::TEXT, '') AS DOUBLE) AS quantity, TRY_CAST(NULLIF(price::TEXT, '') AS DOUBLE) AS price,
         reason::TEXT AS reason, entered_by::TEXT AS entered_by, entered_at::TEXT AS entered_at, source_file, file_row_number
  FROM bronze.reg_purchase_act
)
SELECT a.act_id, a.version_id, a.input_code, a.plant_code, a.period, a.quantity, a.price, a.reason, a.entered_by, a.entered_at
FROM acts a
WHERE a.action = 'set' AND a.act_id NOT IN (SELECT withdraws FROM acts WHERE action = 'withdraw' AND withdraws IS NOT NULL)
QUALIFY ROW_NUMBER() OVER (PARTITION BY a.version_id, a.input_code, a.plant_code, a.period ORDER BY a.entered_at DESC, a.source_file DESC, a.file_row_number DESC) = 1
