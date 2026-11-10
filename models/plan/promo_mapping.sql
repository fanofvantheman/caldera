/* The mapping of the promotions sender's codes onto ours, in force: five subjects — mechanic (their tactic), funding
   type, status, customer (their planning account → our account) and material (their product group → our promo group).
   The register is a log, one row per act; the latest row per sender × subject × local code is the mapping. A row is in
   force when a person has accepted or altered it; a first-pass proposal waits for review and holds every event that
   uses the code. Each row says where it came from (first pass, person) and, for a proposal, the confidence and why. */
MODEL (name plan.promo_mapping, kind FULL, grain (sender, subject, local_code), audits (promo_mapping_vocabulary, promo_mapping_target_known));
WITH acts AS (
  SELECT m.*, ROW_NUMBER() OVER (PARTITION BY m.sender, m.subject, m.local_code
                                 ORDER BY m.acted_at DESC, m.source_file DESC, m.file_row_number DESC) AS recency,
         COUNT(*) OVER (PARTITION BY m.sender, m.subject, m.local_code) AS acts
  FROM bronze.reg_promo_mapping m
),
targets AS (
  SELECT 'mechanic' AS subject, mechanic AS target_code, mechanic_name AS target_name FROM dims.ref_mechanic
  UNION ALL SELECT 'funding_type', funding_type, funding_type_name FROM dims.ref_funding_type
  UNION ALL SELECT 'status', status, status_name FROM dims.ref_promo_status
  UNION ALL SELECT 'customer', account_code, account_name FROM dims.dim_account
  UNION ALL SELECT 'material', promo_group_code, ANY_VALUE(promo_group_name) FROM dims.ref_promo_group GROUP BY ALL
)
SELECT a.sender::TEXT AS sender, a.subject::TEXT AS subject, a.local_code::TEXT AS local_code, a.local_description::TEXT AS local_description,
       a.target_code::TEXT AS target_code, t.target_name, a.origin::TEXT AS origin, a.review_state::TEXT AS review_state,
       NULLIF(a.confidence::TEXT, '') AS confidence, NULLIF(a.rationale::TEXT, '') AS rationale,
       a.acted_by::TEXT AS acted_by, a.acted_at::TEXT AS acted_at, NULLIF(a.reason::TEXT, '') AS reason, a.acts,
       a.review_state IN ('accepted', 'altered') AND t.target_code IS NOT NULL AS in_force,
       t.target_code IS NOT NULL AS target_known
FROM acts a
LEFT JOIN targets t ON t.subject = a.subject AND t.target_code = a.target_code
WHERE a.recency = 1
