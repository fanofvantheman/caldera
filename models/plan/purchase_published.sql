/* Purchasing's receipts as last published on a Plan (DEC-20261123-01 points 12–13): the copy made when supply's second
   sign-off was given — or, on a Plan started from another, what was carried across — one file of the register named
   published-purchasing-<plan>-…, replaced whole at the next publication. The stages after supply read these and not
   the receipts as sent (plan.purchase_act): a send moves nothing after supply until supply is published again. */
MODEL (name plan.purchase_published, kind FULL, grain (version_id, input_code, plant_code, period));
SELECT act_id::TEXT AS act_id, version_id::TEXT AS version_id, input_code::TEXT AS input_code, plant_code::TEXT AS plant_code, period::TEXT AS period,
       TRY_CAST(NULLIF(quantity::TEXT, '') AS DOUBLE) AS quantity, TRY_CAST(NULLIF(price::TEXT, '') AS DOUBLE) AS price,
       reason::TEXT AS reason, entered_by::TEXT AS entered_by, entered_at::TEXT AS entered_at
FROM bronze.reg_purchase_act
WHERE COALESCE(source_file, '') LIKE 'published-%' AND action::TEXT = 'set'
QUALIFY ROW_NUMBER() OVER (PARTITION BY version_id::TEXT, input_code::TEXT, plant_code::TEXT, period::TEXT ORDER BY entered_at::TEXT DESC, source_file DESC, file_row_number DESC) = 1
