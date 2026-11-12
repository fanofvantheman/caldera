/* The runs the forecasting system has sent and someone has taken in: one row per run, saying what its numbers are —
   when it was made, the last week of history it used, how far it reaches, its grain, whether promotions are in or out,
   what history it was fitted on. A run replaces the one before it whole: the latest taken in per version is in force. A
   run that does not declare itself baseline only is refused at the door; one that reached the landing anyway stops the
   run here, because with promotions left in the plan would count every event twice. */
MODEL (name plan.forecast_run, kind FULL, grain (run_id), audits (forecast_run_baseline_only));
WITH acts AS (
  SELECT r.*, ROW_NUMBER() OVER (PARTITION BY r.run_id ORDER BY r.taken_in_at DESC, r.file_row_number DESC) AS recency
  FROM bronze.fcst_run r
)
SELECT a.sender::TEXT AS sender, a.run_id::TEXT AS run_id, a.version_id::TEXT AS version_id, a.made_on::DATE AS made_on,
       a.last_history_week::TEXT AS last_history_week, a.first_week::DATE AS first_week, a.horizon_weeks::INT AS horizon_weeks,
       (a.first_week::DATE + (a.horizon_weeks::INT * 7 - 1))::DATE AS last_day,
       a.grain::TEXT AS grain, a.content::TEXT AS content, a.history_basis::TEXT AS history_basis, a.method_note::TEXT AS method_note,
       a.taken_in_at::TIMESTAMP AS taken_in_at, a.taken_in_by::TEXT AS taken_in_by,
       ROW_NUMBER() OVER (PARTITION BY a.version_id ORDER BY a.taken_in_at::TIMESTAMP DESC, a.run_id DESC) = 1 AS in_force
FROM acts a WHERE a.recency = 1
