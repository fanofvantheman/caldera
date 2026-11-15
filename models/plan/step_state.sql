/* The state of every step of every process, at every node of the dimension it is scoped on, on every plan version
   (DEC-20261115-03 points 3–5): nothing yet · open · submitted · accepted · sent back — read from the acts (plan.submission,
   the latest act standing), never set. A node with no act of its own reads open where it has figures and nothing where it
   has none; beneath it, how many of the cost centres with figures are in. The demand step is the demand plan's own
   submission, read from its matrix. The due date is the step's on the version, set on its process's administration page.
   Nothing reads this to decide what to calculate: the workflow records, shows and locks entry (point 6). */
MODEL (name plan.step_state, kind FULL, grain (version_id, step, node));
WITH versions AS (SELECT version_id FROM dims.ctl_version WHERE version_kind <> 'actual'),
org AS (SELECT cost_centre_code AS node, parent_code AS parent, kind NOT IN ('company', 'function') AS is_leaf FROM plan.planning_cost_centre),
has AS (
  SELECT DISTINCT version_id, 'opex' AS step, cost_centre_code AS node FROM plan.opex_schedule
  UNION SELECT DISTINCT version_id, 'labour', cost_centre_code FROM plan.labour_cost
  UNION SELECT DISTINCT version_id, 'capital', cost_centre_code FROM plan.capex_line WHERE kind <> 'asset'
),
acts AS (SELECT * FROM plan.submission WHERE subject LIKE 'step:%' AND acted_by_holder),
due AS (
  SELECT version_id, subject, NULLIF(due_on::TEXT, '') AS due_on FROM bronze.reg_submission WHERE action = 'due'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY version_id, subject ORDER BY submitted_on DESC, source_file DESC, file_row_number DESC) = 1
),
org_steps AS (
  SELECT v.version_id, s.process, s.ord, s.step, s.step_label, s.subject, o.node, o.parent, o.is_leaf,
         EXISTS (SELECT 1 FROM has h JOIN dims.dim_organisation_hierarchy x ON x.descendant_code = h.node AND x.ancestor_code = o.node
                 WHERE h.version_id = v.version_id AND h.step = s.step) AS has_figures,
         (SELECT COUNT(DISTINCT h.node) FROM has h JOIN dims.dim_organisation_hierarchy x ON x.descendant_code = h.node AND x.ancestor_code = o.node
          WHERE h.version_id = v.version_id AND h.step = s.step) AS n_beneath
  FROM versions v CROSS JOIN plan.ref_step s CROSS JOIN org o WHERE s.dimension = 'organisation'
),
cust_steps AS (
  SELECT v.version_id, s.process, s.ord, s.step, s.step_label, s.subject, 'ALL' AS node, NULL::TEXT AS parent, TRUE AS is_leaf, s.built AS has_figures,
         CASE WHEN s.built THEN 1 ELSE 0 END AS n_beneath
  FROM versions v CROSS JOIN plan.ref_step s WHERE s.dimension IN ('customer', 'location') AND s.step <> 'demand'
),
steps AS (SELECT * FROM org_steps UNION ALL SELECT * FROM cust_steps),
explicit AS (
  SELECT s.*, a.state AS act_state, a.acted_by, a.acted_on, a.note
  FROM steps s LEFT JOIN acts a ON a.version_id = s.version_id AND a.subject = s.subject AND a.scope_node = s.node
),
stated AS (
  SELECT e.*, CASE WHEN e.act_state IN ('submitted', 'accepted', 'sent_back') THEN e.act_state
                   WHEN e.has_figures THEN 'open' ELSE 'nothing' END AS state FROM explicit e
),
counted AS (
  SELECT t.*,
         (SELECT COUNT(*) FROM stated b JOIN dims.dim_organisation_hierarchy x ON x.descendant_code = b.node AND x.ancestor_code = t.node
          WHERE b.version_id = t.version_id AND b.step = t.step AND b.is_leaf AND b.has_figures AND b.state IN ('submitted', 'accepted')) AS n_in
  FROM stated t
),
demand AS (                                   -- the demand plan's own submission: the units and the plan, from its matrix
  SELECT d.version_id, 'ibp' AS process, 1 AS ord, 'demand' AS step, 'Demand' AS step_label, d.subject, d.node, CASE WHEN d.node = 'ALL' THEN NULL ELSE 'ALL' END AS parent,
         d.node <> 'ALL' AS is_leaf, d.state <> 'nothing' AS has_figures, NULL::BIGINT AS n_beneath, a.state AS act_state, d.acted_by, d.acted_on, a.note,
         CASE WHEN a.state IN ('accepted', 'sent_back') AND d.node = 'ALL' THEN a.state
              WHEN d.state IN ('submitted', 'rolled_up') THEN 'submitted' WHEN d.state IN ('open', 'ready') THEN 'open' ELSE 'nothing' END AS state,
         NULL::BIGINT AS n_in
  FROM plan.submission_state d
  LEFT JOIN plan.submission a ON a.version_id = d.version_id AND a.subject = d.subject AND a.scope_node = d.node AND a.acted_by_holder
  WHERE d.subject = 'plan' OR (d.subject = 'unit' AND d.level = 'planning_unit')
)
SELECT c.version_id, c.process, c.ord, c.step, c.step_label, c.subject, c.node, c.parent, c.is_leaf, c.has_figures, c.n_beneath, c.n_in,
       c.state, c.acted_by, c.acted_on, c.note, du.due_on
FROM counted c LEFT JOIN due du ON du.version_id = c.version_id AND du.subject = c.subject
UNION ALL
SELECT d.version_id, d.process, d.ord, d.step, d.step_label, d.subject, d.node, d.parent, d.is_leaf, d.has_figures, d.n_beneath, d.n_in,
       d.state, d.acted_by, d.acted_on, d.note, du.due_on
FROM demand d LEFT JOIN due du ON du.version_id = d.version_id AND du.subject = 'plan'
