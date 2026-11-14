/* The files from the promotions system each version reads. A file is an arrival: taken in for a version by trade
   marketing, or — for a version named from a base — every file its base had taken, recorded on the new version as a
   `take` in the version acts, referenced and never copied. The calendar reads the sender's rows of these files as the
   version's (plan.promo_sender_event, plan.promo_funding); `source_version` is the version the rows were taken in under. */
MODEL (name plan.version_sender_file, kind FULL, grain (version_id, sender_file, taken_in_at));
SELECT DISTINCT version_id::TEXT AS version_id, sender_file::TEXT AS sender_file, taken_in_at::TEXT AS taken_in_at, version_id::TEXT AS source_version,
       'taken in' AS how
FROM bronze.tpm_event
UNION ALL
SELECT version_id::TEXT, arrival_id::TEXT, arrival_taken_in_at::TEXT, source_version::TEXT, 'taken at naming'
FROM bronze.reg_version_act WHERE "act" = 'take' AND arrival = 'sender_file'
