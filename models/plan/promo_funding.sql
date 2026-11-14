/* The funding package of every event the promotions sender has on file in force (the latest send of each event within
   the version, of the files the version reads — plan.version_sender_file): one row per line, the sender's fund type beside the type it maps to, and whether the financialisation
   prices it. A line on a type nobody prices yet is carried and shown, never dropped. */
MODEL (name plan.promo_funding, kind FULL, grain (version_id, event_id, line_no));
WITH taken AS (
  SELECT e.* REPLACE (t.version_id AS version_id), t.source_version
  FROM bronze.tpm_event e
  JOIN plan.version_sender_file t ON t.source_version = e.version_id AND t.sender_file = e.sender_file AND t.taken_in_at = e.taken_in_at::TEXT
),
latest AS (
  SELECT version_id, source_version, event_id, sender, sender_file, taken_in_at
  FROM (SELECT e.*, ROW_NUMBER() OVER (PARTITION BY e.version_id, e.event_id ORDER BY e.taken_in_at DESC, e.source_file DESC, e.file_row_number DESC) AS r
        FROM taken e) WHERE r = 1
)
SELECT l.version_id::TEXT AS version_id, f.event_id::TEXT AS event_id, f.line_no::INT AS line_no, f.sender::TEXT AS sender,
       f.fund_type::TEXT AS local_fund_type, f.fund_type_name::TEXT AS local_fund_type_name, f.rate_basis::TEXT AS rate_basis,
       f.rate::DOUBLE AS rate, m.target_code AS funding_type, COALESCE(m.in_force, FALSE) AS mapping_in_force, m.review_state,
       COALESCE(t.priced, FALSE) AND COALESCE(m.in_force, FALSE) AS priced, t.event_column
FROM bronze.tpm_funding f
JOIN latest l ON l.source_version = f.version_id AND l.event_id = f.event_id AND l.sender_file = f.sender_file AND l.taken_in_at = f.taken_in_at
LEFT JOIN plan.promo_mapping m ON m.sender = f.sender AND m.subject = 'funding_type' AND m.local_code = f.fund_type
LEFT JOIN dims.ref_funding_type t ON t.funding_type = m.target_code
