/* The forecasting run each version reads, per account. A run is an arrival: it happened once, and any number of versions
   may take it. A version takes one either by an account's planner taking it in for that version (plan.forecast_run), or
   by being named from a base — the base's run in force for each account is recorded on the new version as a `take` in the
   version acts, referenced and never copied. The latest of the two per version × account is the run that version reads;
   the run itself, its series and its header stay keyed as they arrived. */
MODEL (name plan.version_run, kind FULL, grain (version_id, account_code));
WITH takes AS (
  SELECT r.version_id, r.account_code, r.run_id, r.taken_in_at, r.taken_in_at AS acted_at, 'taken in' AS how, NULL::TEXT AS taken_from
  FROM plan.forecast_run r
  UNION ALL
  SELECT t.version_id::TEXT, t.account_code::TEXT, t.arrival_id::TEXT, t.arrival_taken_in_at::TIMESTAMP, t.entered_on::TIMESTAMP,
         'taken at naming', t.source_version::TEXT
  FROM bronze.reg_version_act t WHERE t."act" = 'take' AND t.arrival = 'forecast_run'
)
SELECT t.version_id, t.how, t.taken_from, t.acted_at AS taken_at, r.* EXCLUDE (version_id, in_force)
FROM takes t
JOIN plan.forecast_run r ON r.run_id = t.run_id AND r.account_code = t.account_code AND r.taken_in_at = t.taken_in_at
QUALIFY ROW_NUMBER() OVER (PARTITION BY t.version_id, t.account_code ORDER BY t.acted_at DESC, t.run_id DESC) = 1
