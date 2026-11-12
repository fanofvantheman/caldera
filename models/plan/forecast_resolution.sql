/* What people have decided about the disagreements between the forecasting system's structures and the plan's: a log,
   one row per act; the latest act per item is in force and stands for every later run until someone acts again.
   Two kinds of item. Theirs, not ours — a material code the plan does not have (keyed by the code, whatever accounts it
   was sent for): the same as one of ours, placed under a product, or left out. Ours, not theirs — a material × account
   the plan calculates and the run does not carry: keep our calculation, or zero on purpose. */
MODEL (name plan.forecast_resolution, kind FULL, grain (sender, kind, item_code, account_code), audits (forecast_resolution_vocabulary, forecast_resolution_target_known));
WITH acts AS (
  SELECT r.*, ROW_NUMBER() OVER (PARTITION BY r.sender, r.kind, r.item_code, r.account_code
                                 ORDER BY r.acted_at DESC, r.source_file DESC, r.file_row_number DESC) AS recency,
         COUNT(*) OVER (PARTITION BY r.sender, r.kind, r.item_code, r.account_code) AS acts
  FROM bronze.reg_fcst_resolution r
)
SELECT a.resolution_id::TEXT AS resolution_id, a.sender::TEXT AS sender, a.kind::TEXT AS kind, a.item_code::TEXT AS item_code,
       a.account_code::TEXT AS account_code, a.resolution::TEXT AS resolution, NULLIF(a.target_code::TEXT, '') AS target_code,
       COALESCE(m.material_name, p.product_name) AS target_name, NULLIF(a.reason::TEXT, '') AS reason,
       a.acted_by::TEXT AS acted_by, a.acted_at::TIMESTAMP AS acted_at, a.acts,
       CASE a.resolution WHEN 'same_as' THEN m.material_code IS NOT NULL WHEN 'place_under' THEN p.product_code IS NOT NULL ELSE TRUE END AS target_known
FROM acts a
LEFT JOIN dims.dim_material m ON a.resolution = 'same_as' AND m.material_code = a.target_code
LEFT JOIN (SELECT DISTINCT product_code, product_name FROM dims.dim_material) p ON a.resolution = 'place_under' AND p.product_code = a.target_code
WHERE a.recency = 1
