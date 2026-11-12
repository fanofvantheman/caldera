/* The mapping of the promotions sender's codes onto ours, in force: five subjects — mechanic (their tactic), funding
   type, status, customer (their planning account → our account) and material (their product group → our promo group).
   Read from the doors' act register (door TPM, one kind per subject): the latest act per code is the mapping. A row is
   in force when a person has accepted or altered it; a first-pass proposal waits for review and holds every event that
   uses the code. Each row says where it came from (first pass, person) and, for a proposal, the confidence and why. */
MODEL (name plan.promo_mapping, kind FULL, grain (sender, subject, local_code), audits (promo_mapping_vocabulary, promo_mapping_target_known));
WITH targets AS (
  SELECT 'mechanic' AS subject, mechanic AS target_code, mechanic_name AS target_name FROM dims.ref_mechanic
  UNION ALL SELECT 'funding_type', funding_type, funding_type_name FROM dims.ref_funding_type
  UNION ALL SELECT 'status', status, status_name FROM dims.ref_promo_status
  UNION ALL SELECT 'customer', account_code, account_name FROM dims.dim_account
  UNION ALL SELECT 'material', promo_group_code, ANY_VALUE(promo_group_name) FROM dims.ref_promo_group GROUP BY ALL
)
SELECT a.door AS sender, a.kind AS subject, a.item_code AS local_code, a.item_description AS local_description,
       a.target_code, t.target_name, a.origin,
       CASE WHEN a.state = 'proposed' THEN 'proposed' WHEN a.resolution = 'accept' THEN 'accepted' ELSE 'altered' END AS review_state,
       a.confidence, a.rationale, a.acted_by, a.acted_at::TEXT AS acted_at, a.reason, a.acts,
       a.in_force AND t.target_code IS NOT NULL AS in_force,
       t.target_code IS NOT NULL AS target_known
FROM plan.door_act a
LEFT JOIN targets t ON t.subject = a.kind AND t.target_code = a.target_code
WHERE a.door = 'TPM'
