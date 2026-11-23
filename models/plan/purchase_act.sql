/* The receipts a Plan takes as fixed (DEC-20261116-04 point 3, DEC-20261121-01 points 7–10): a key material × plant ×
   period on a plan, a quantity and a price.
   On a Plan where purchasing's copy stands — one file of the register named standing-purchasing-<plan>-…, with a marker
   row so an empty copy still stands — the receipts are that copy's, and over it what was typed in the Plan since the copy
   was placed (DEC-20261121-03 (a)): an act of the register entered after the copy's marker; a receipt absent from the
   copy and not typed since is gone. On a Plan with none, the register as a log: the latest act per cell stands; a withdrawal names an act
   and takes it out, and the one before it stands again.
   These are the receipts as sent — what the plans feeding supply work from. The stages after supply read the receipts
   as last published (plan.purchase_published, DEC-20261123-01 point 13); a published-… file is not read here. */
MODEL (name plan.purchase_act, kind FULL, grain (version_id, input_code, plant_code, period));
WITH acts AS (
  SELECT act_id::TEXT AS act_id, action::TEXT AS action, NULLIF(withdraws::TEXT, '') AS withdraws, version_id::TEXT AS version_id,
         input_code::TEXT AS input_code, plant_code::TEXT AS plant_code, period::TEXT AS period,
         TRY_CAST(NULLIF(quantity::TEXT, '') AS DOUBLE) AS quantity, TRY_CAST(NULLIF(price::TEXT, '') AS DOUBLE) AS price,
         reason::TEXT AS reason, entered_by::TEXT AS entered_by, entered_at::TEXT AS entered_at, source_file, file_row_number,
         COALESCE(source_file, '') LIKE 'standing-%' AS standing
  FROM bronze.reg_purchase_act
  WHERE COALESCE(source_file, '') NOT LIKE 'published-%'
),
stands AS (SELECT version_id, MAX(CASE WHEN action = 'stand' THEN entered_at END) AS stood_at FROM acts WHERE standing GROUP BY version_id)
SELECT a.act_id, a.version_id, a.input_code, a.plant_code, a.period, a.quantity, a.price, a.reason, a.entered_by, a.entered_at
FROM acts a
WHERE a.action = 'set' AND a.act_id NOT IN (SELECT withdraws FROM acts WHERE action = 'withdraw' AND withdraws IS NOT NULL)
  AND (a.standing OR a.version_id NOT IN (SELECT version_id FROM stands)
       OR a.entered_at > (SELECT s.stood_at FROM stands s WHERE s.version_id = a.version_id))
QUALIFY ROW_NUMBER() OVER (PARTITION BY a.version_id, a.input_code, a.plant_code, a.period ORDER BY a.entered_at DESC, a.source_file DESC, a.file_row_number DESC) = 1
