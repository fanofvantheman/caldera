/* The latest submission act per subject and node on a version. A subject is a layer ('layer:4'), a unit's demand
   ('unit') or the plan ('plan'); a node is where on the customer structure the act was made. The state is the act:
   submitted or reopened. Nothing is set here; the files say what happened and the last word stands. */
MODEL (name plan.submission, kind FULL, grain (version_id, subject, scope_node));
SELECT s.version_id::TEXT AS version_id, s.subject::TEXT AS subject, s.scope_node::TEXT AS scope_node,
       CASE s.action WHEN 'submit' THEN 'submitted' ELSE 'reopened' END AS state,
       s.submitted_by::TEXT AS acted_by, s.submitted_on::DATE AS acted_on, NULLIF(s.note::TEXT, '') AS note, s.source_file, s.file_row_number,
       EXISTS (SELECT 1 FROM dims.ctl_version v WHERE v.version_id = s.version_id) AS version_known,
       EXISTS (SELECT 1 FROM dims.dim_customer_hierarchy h WHERE h.ancestor_code = s.scope_node) AS node_known,
       CASE WHEN s.subject LIKE 'layer:%' THEN EXISTS (SELECT 1 FROM dims.effective_entitlements x WHERE x.principal = s.submitted_by
              AND x.action = 'layer.' || SUBSTR(s.subject, 7) || '.' || s.action AND ((x.scope_dimension = 'customer' AND x.node = s.scope_node) OR (s.scope_node = 'ALL' AND x.node = 'ALL')))
            ELSE EXISTS (SELECT 1 FROM dims.effective_entitlements x WHERE x.principal = s.submitted_by
              AND x.action = 'demand.' || s.subject || '.' || s.action AND ((x.scope_dimension = 'customer' AND x.node = s.scope_node) OR (s.scope_node = 'ALL' AND x.node = 'ALL'))) END AS acted_by_holder
FROM bronze.reg_submission s
QUALIFY ROW_NUMBER() OVER (PARTITION BY s.version_id, s.subject, s.scope_node ORDER BY s.submitted_on DESC, s.source_file DESC, s.file_row_number DESC) = 1
