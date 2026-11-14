/* The series of the run each version reads for each account (plan.version_run), as sent — never copied: a version named
   from a base reads the same rows — material × account × week, cases — each with what the plan makes of it.
   The codes are the ERP's, as ours are, so a series either names a material the plan has or it does not. in: the
   material is ours (or a person has said it is the same as one of ours) and the account takes its baseline from the
   forecasting system. held: the plan has no such material and nobody has decided — it has cases and nowhere to put
   them. placed: a person has put it under a product; it stays outside the plan until the structure carries it, because
   it has no price and no route. left_out: a person has said the plan does not carry it, with the reason. refused: sent
   for an account whose baseline is calculated in the plan, or for a week the calendar does not have. */
MODEL (name plan.forecast_series, kind FULL, grain (version_id, run_id, sent_code, account_code, week_start));
WITH run AS (SELECT * FROM plan.version_run),
sent AS (
  SELECT r.version_id, r.run_id, s.material_code::TEXT AS sent_code, ANY_VALUE(s.material_description::TEXT) AS sent_description,
         ANY_VALUE(s.sender_hierarchy::TEXT) AS sender_hierarchy, s.account_code::TEXT AS account_code, s.week_start::DATE AS week_start,
         SUM(s.cases::DOUBLE) AS cases
  FROM bronze.fcst_series s JOIN run r ON r.run_id = s.run_id::TEXT AND r.account_code = s.account_code::TEXT AND r.taken_in_at = s.taken_in_at::TIMESTAMP
  GROUP BY ALL
)
SELECT s.version_id, s.run_id, s.sent_code, s.sent_description, s.sender_hierarchy, s.account_code, s.week_start, w.week_id, w.period, s.cases,
       m.material_code IS NOT NULL AS material_known, COALESCE(a.baseline_source = 'FORECAST', FALSE) AS account_takes,
       res.resolution, res.target_code,
       CASE WHEN m.material_code IS NOT NULL THEN s.sent_code WHEN res.resolution = 'same_as' AND res.target_known THEN res.target_code END AS material_code,
       CASE WHEN NOT COALESCE(a.baseline_source = 'FORECAST', FALSE) OR w.week_id IS NULL THEN 'refused'
            WHEN m.material_code IS NOT NULL THEN 'in'
            WHEN res.resolution = 'same_as' AND res.target_known THEN 'in'
            WHEN res.resolution = 'leave_out' THEN 'left_out'
            WHEN res.resolution = 'place_under' THEN 'placed'
            ELSE 'held' END AS state
FROM sent s
LEFT JOIN dims.dim_week w ON w.week_start = s.week_start
LEFT JOIN dims.dim_material m ON m.material_code = s.sent_code
LEFT JOIN dims.dim_account a ON a.account_code = s.account_code
LEFT JOIN plan.forecast_resolution res ON res.kind = 'theirs_not_ours' AND res.item_code = s.sent_code
