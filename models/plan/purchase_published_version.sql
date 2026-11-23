/* The Plans on which a copy of purchasing's receipts has been published, and when and by whom: the marker row of the
   published-… file, so a copy published empty still counts. A Plan not here has never been published or started from
   another, and the stages after supply read its receipts as they stand. */
MODEL (name plan.purchase_published_version, kind FULL, grain (version_id));
SELECT version_id::TEXT AS version_id, entered_at::TEXT AS published_at, entered_by::TEXT AS published_by, reason::TEXT AS says
FROM bronze.reg_purchase_act
WHERE COALESCE(source_file, '') LIKE 'published-%' AND action::TEXT = 'publish'
QUALIFY ROW_NUMBER() OVER (PARTITION BY version_id::TEXT ORDER BY entered_at::TEXT DESC, source_file DESC) = 1
