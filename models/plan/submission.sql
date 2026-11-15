/* The latest submission act per subject and node on a version. A subject is a layer ('layer:4'), a unit's demand
   ('unit'), the plan ('plan') or a step of a process ('step:opex', plan.ref_step); a node is where on the step's
   dimension the act was made — the customer structure for the demand plan, the plan's cost centres for the cost side.
   The state is the act: submitted, reopened, accepted or sent back (DEC-20261115-03 point 4: the demand plan's
   submission, made general). Nothing is set here; the files say what happened and the last word stands. A due date
   (`due`) is not an act on a node and is read by plan.step_state. */
MODEL (name plan.submission, kind FULL, grain (version_id, subject, scope_node));
WITH rows_ AS (
  SELECT s.*, r.dimension, r.submit_verb, r.decide_verb
  FROM bronze.reg_submission s
  LEFT JOIN plan.ref_step r ON r.subject = s.subject AND s.subject LIKE 'step:%'
  WHERE s.action <> 'due'
)
SELECT s.version_id::TEXT AS version_id, s.subject::TEXT AS subject, s.scope_node::TEXT AS scope_node,
       CASE s.action WHEN 'submit' THEN 'submitted' WHEN 'accept' THEN 'accepted' WHEN 'send_back' THEN 'sent_back' ELSE 'reopened' END AS state,
       s.action::TEXT AS action, s.submitted_by::TEXT AS acted_by, s.submitted_on::DATE AS acted_on, NULLIF(s.note::TEXT, '') AS note, s.source_file, s.file_row_number,
       EXISTS (SELECT 1 FROM dims.ctl_version v WHERE v.version_id = s.version_id) AS version_known,
       CASE WHEN s.dimension = 'organisation' THEN EXISTS (SELECT 1 FROM dims.dim_organisation_hierarchy h WHERE h.ancestor_code = s.scope_node)
            ELSE EXISTS (SELECT 1 FROM dims.dim_customer_hierarchy h WHERE h.ancestor_code = s.scope_node) END AS node_known,
       CASE WHEN s.subject LIKE 'step:%' THEN EXISTS (
              SELECT 1 FROM dims.effective_entitlements x
              WHERE x.principal = s.submitted_by AND x.scope_dimension = s.dimension
                AND x.action = CASE WHEN s.action = 'submit' THEN s.submit_verb WHEN s.action = 'reopen' THEN x.action ELSE s.decide_verb END
                AND (s.action <> 'reopen' OR x.action IN (s.submit_verb, s.decide_verb))
                AND EXISTS (SELECT 1 FROM dims.dim_organisation_hierarchy h WHERE h.ancestor_code = x.node AND h.descendant_code = s.scope_node
                            UNION ALL SELECT 1 FROM dims.dim_customer_hierarchy h WHERE h.ancestor_code = x.node AND h.descendant_code = s.scope_node))
            WHEN s.action IN ('accept', 'send_back') THEN EXISTS (SELECT 1 FROM dims.effective_entitlements x WHERE x.principal = s.submitted_by
              AND x.action = 'review.demand.close' AND (x.node = s.scope_node OR x.node = 'ALL'))
            WHEN s.subject LIKE 'layer:%' THEN EXISTS (SELECT 1 FROM dims.effective_entitlements x WHERE x.principal = s.submitted_by
              AND x.action = 'layer.' || SUBSTR(s.subject, 7) || '.' || s.action AND ((x.scope_dimension = 'customer' AND x.node = s.scope_node) OR (s.scope_node = 'ALL' AND x.node = 'ALL')))
            ELSE EXISTS (SELECT 1 FROM dims.effective_entitlements x WHERE x.principal = s.submitted_by
              AND x.action = 'demand.' || s.subject || '.' || s.action AND ((x.scope_dimension = 'customer' AND x.node = s.scope_node) OR (s.scope_node = 'ALL' AND x.node = 'ALL'))) END AS acted_by_holder
FROM rows_ s
QUALIFY ROW_NUMBER() OVER (PARTITION BY s.version_id, s.subject, s.scope_node ORDER BY s.submitted_on DESC, s.source_file DESC, s.file_row_number DESC) = 1
