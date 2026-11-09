/* What is still open to submit, and whose it is: every node where a subject is open or ready and someone holds the
   submit verb there. The head of demand sees everything open beneath the plan; a unit planner their unit; an account
   manager their account. */
MODEL (name plan.worklist_open_submissions, kind FULL, grain (version_id, subject, node));
SELECT s.version_id, s.subject, s.node, s.level, s.state, s.whose, s.open_below,
       CASE s.subject WHEN 'unit' THEN 'unit demand' WHEN 'plan' THEN 'demand plan' ELSE 'layer ' || SUBSTR(s.subject, 7) || ' ' || l.layer_name END
         || ' at ' || s.node || ' is ' || s.state || CASE WHEN s.state = 'submitted' THEN ' with ' || s.open_below || ' open beneath' ELSE '' END || ' on ' || s.version_id AS item
FROM plan.submission_state s
LEFT JOIN plan.ref_layer l ON 'layer:' || l.layer_no = s.subject
JOIN dims.ctl_version v ON v.version_id = s.version_id AND v.status = 'open'
WHERE (s.state IN ('open', 'ready') OR (s.state = 'submitted' AND s.open_below > 0)) AND s.whose IS NOT NULL
