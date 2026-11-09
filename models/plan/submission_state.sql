/* The submission matrix: for every open or frozen version, every layer present and the unit and plan subjects, at every
   account, planning unit and the root — a state the run derived from the acts and the entries.
     submitted  the holder at this node (or above it) submitted
     rolled_up  nothing explicit here, but every account or unit beneath with anything to submit is submitted
     ready      every layer beneath this unit (or every unit beneath the plan) is in; the unit or plan act is missing
     open       there is something here — entries, or open children — and no submission covers it
     nothing    no entries anywhere beneath, no act
     n/a        this layer does not submit at this level
   States roll up; acts do not. A parent submitting over open children is an act on file, and the children stay open
   beneath it for everyone to see. */
MODEL (name plan.submission_state, kind FULL, grain (version_id, subject, node));
WITH versions AS (SELECT version_id FROM dims.ctl_version WHERE version_kind <> 'actual'),
nodes AS (
  SELECT DISTINCT ancestor_code AS node, ancestor_level AS level FROM dims.dim_customer_hierarchy WHERE ancestor_level IN ('all', 'planning_unit', 'account')
),
layers AS (SELECT layer_no, 'layer:' || layer_no AS subject, submits_at FROM plan.ref_layer WHERE present_at_this_stage AND submits_at <> 'none'),
-- what each layer has beneath each node: a usable entry whose customer scope is at, beneath, or above the node
presence AS (
  SELECT v.version_id, l.subject, n.node,
         EXISTS (SELECT 1 FROM plan.layer_entry e
                 WHERE e.version_id = v.version_id AND e.layer_no = l.layer_no AND e.entered_by_owner AND e.version_known
                   AND NOT (e.withdrawn AND e.withdrawn_by_owner)
                   AND (EXISTS (SELECT 1 FROM dims.dim_customer_hierarchy h WHERE h.ancestor_code = n.node AND h.descendant_code = e.scope_customer)
                     OR EXISTS (SELECT 1 FROM dims.dim_customer_hierarchy h WHERE h.ancestor_code = e.scope_customer AND h.descendant_code = n.node))) AS has_entries
  FROM versions v CROSS JOIN layers l CROSS JOIN nodes n
),
-- an explicit submission covering the node: at the node or any ancestor, latest act submitted
covered AS (
  SELECT p.version_id, p.subject, p.node, s.acted_by, s.acted_on, s.scope_node AS covered_from
  FROM presence p
  JOIN dims.dim_customer_hierarchy h ON h.descendant_code = p.node
  JOIN plan.submission s ON s.version_id = p.version_id AND s.subject = p.subject AND s.scope_node = h.ancestor_code AND s.state = 'submitted' AND s.acted_by_holder
  QUALIFY ROW_NUMBER() OVER (PARTITION BY p.version_id, p.subject, p.node ORDER BY h.depth) = 1
),
-- account level: explicit, open, or nothing
acct AS (
  SELECT p.version_id, p.subject, p.node, n.level, l.submits_at,
         CASE WHEN l.submits_at <> 'account' THEN 'n/a'
              WHEN c.node IS NOT NULL THEN 'submitted'
              WHEN p.has_entries THEN 'open' ELSE 'nothing' END AS state, c.acted_by, c.acted_on
  FROM presence p JOIN nodes n ON n.node = p.node JOIN layers l ON l.subject = p.subject LEFT JOIN covered c ON c.version_id = p.version_id AND c.subject = p.subject AND c.node = p.node
  WHERE n.level = 'account'
),
-- unit level: explicit; else rolled up from accounts (account layers) or open/nothing (unit layers); n/a for all-level layers
unit AS (
  SELECT p.version_id, p.subject, p.node, n.level, l.submits_at,
         CASE WHEN l.submits_at = 'all' THEN 'n/a'
              WHEN c.node IS NOT NULL THEN 'submitted'
              WHEN l.submits_at = 'account' THEN
                CASE WHEN NOT EXISTS (SELECT 1 FROM acct a JOIN dims.dim_customer_hierarchy h ON h.descendant_code = a.node AND h.ancestor_code = p.node AND h.depth = 1
                                      WHERE a.version_id = p.version_id AND a.subject = p.subject AND a.state <> 'nothing') THEN 'nothing'
                     WHEN NOT EXISTS (SELECT 1 FROM acct a JOIN dims.dim_customer_hierarchy h ON h.descendant_code = a.node AND h.ancestor_code = p.node AND h.depth = 1
                                      WHERE a.version_id = p.version_id AND a.subject = p.subject AND a.state = 'open') THEN 'rolled_up'
                     ELSE 'open' END
              WHEN p.has_entries THEN 'open' ELSE 'nothing' END AS state, c.acted_by, c.acted_on
  FROM presence p JOIN nodes n ON n.node = p.node JOIN layers l ON l.subject = p.subject LEFT JOIN covered c ON c.version_id = p.version_id AND c.subject = p.subject AND c.node = p.node
  WHERE n.level = 'planning_unit'
),
-- root: explicit; else rolled up from the units (account and unit layers) or open/nothing (all-level layers)
root AS (
  SELECT p.version_id, p.subject, p.node, n.level, l.submits_at,
         CASE WHEN c.node IS NOT NULL THEN 'submitted'
              WHEN l.submits_at IN ('account', 'unit') THEN
                CASE WHEN NOT EXISTS (SELECT 1 FROM unit u WHERE u.version_id = p.version_id AND u.subject = p.subject AND u.state <> 'nothing') THEN 'nothing'
                     WHEN NOT EXISTS (SELECT 1 FROM unit u WHERE u.version_id = p.version_id AND u.subject = p.subject AND u.state = 'open') THEN 'rolled_up'
                     ELSE 'open' END
              WHEN p.has_entries THEN 'open' ELSE 'nothing' END AS state, c.acted_by, c.acted_on
  FROM presence p JOIN nodes n ON n.node = p.node JOIN layers l ON l.subject = p.subject LEFT JOIN covered c ON c.version_id = p.version_id AND c.subject = p.subject AND c.node = p.node
  WHERE n.level = 'all'
),
layer_states AS (SELECT * FROM acct UNION ALL SELECT * FROM unit UNION ALL SELECT * FROM root),
-- the unit's demand: an explicit unit act, else ready when every layer at the unit is in, else open
unit_demand AS (
  SELECT v.version_id, 'unit' AS subject, n.node, n.level, 'unit' AS submits_at,
         CASE WHEN s.state = 'submitted' AND s.acted_by_holder THEN 'submitted'
              WHEN NOT EXISTS (SELECT 1 FROM layer_states ls WHERE ls.version_id = v.version_id AND ls.node = n.node AND ls.state <> 'nothing' AND ls.state <> 'n/a') THEN 'nothing'
              WHEN NOT EXISTS (SELECT 1 FROM layer_states ls WHERE ls.version_id = v.version_id AND ls.node = n.node AND ls.state = 'open') THEN 'ready'
              ELSE 'open' END AS state, s.acted_by, s.acted_on
  FROM versions v CROSS JOIN nodes n LEFT JOIN plan.submission s ON s.version_id = v.version_id AND s.subject = 'unit' AND s.scope_node = n.node
  WHERE n.level = 'planning_unit'
),
plan_demand AS (
  SELECT v.version_id, 'plan' AS subject, 'ALL' AS node, 'all' AS level, 'all' AS submits_at,
         CASE WHEN s.state = 'submitted' AND s.acted_by_holder THEN 'submitted'
              WHEN NOT EXISTS (SELECT 1 FROM unit_demand u WHERE u.version_id = v.version_id AND u.state <> 'nothing') THEN 'nothing'
              WHEN NOT EXISTS (SELECT 1 FROM unit_demand u WHERE u.version_id = v.version_id AND u.state IN ('open', 'ready'))
                   AND NOT EXISTS (SELECT 1 FROM root r WHERE r.version_id = v.version_id AND r.state = 'open') THEN 'ready'
              ELSE 'open' END AS state, s.acted_by, s.acted_on
  FROM versions v LEFT JOIN plan.submission s ON s.version_id = v.version_id AND s.subject = 'plan' AND s.scope_node = 'ALL'
),
everything AS (
  SELECT version_id, subject, node, level, submits_at, state, acted_by, acted_on FROM layer_states
  UNION ALL SELECT version_id, subject, node, level, submits_at, state, acted_by, acted_on FROM unit_demand
  UNION ALL SELECT version_id, subject, node, level, submits_at, state, acted_by, acted_on FROM plan_demand
)
SELECT e.*,
       CASE WHEN e.subject LIKE 'layer:%' THEN
              (SELECT COUNT(*) FROM everything b JOIN dims.dim_customer_hierarchy h ON h.descendant_code = b.node AND h.ancestor_code = e.node AND h.depth > 0
               WHERE b.version_id = e.version_id AND b.subject = e.subject AND b.state = 'open')
            WHEN e.subject = 'unit' THEN
              (SELECT COUNT(*) FROM everything b JOIN dims.dim_customer_hierarchy h ON h.descendant_code = b.node AND h.ancestor_code = e.node
               WHERE b.version_id = e.version_id AND b.subject LIKE 'layer:%' AND b.state = 'open')
            ELSE (SELECT COUNT(*) FROM everything b WHERE b.version_id = e.version_id AND b.subject <> 'plan' AND b.state = 'open') END AS open_below,
       CASE WHEN e.subject LIKE 'layer:%' THEN 'layer.' || SUBSTR(e.subject, 7) || '.submit' ELSE 'demand.' || e.subject || '.submit' END AS submit_verb,
       (SELECT STRING_AGG(DISTINCT x.principal, ', ') FROM dims.effective_entitlements x
        WHERE ((x.scope_dimension = 'customer' AND x.node = e.node) OR (e.node = 'ALL' AND x.node = 'ALL'))
          AND x.action = CASE WHEN e.subject LIKE 'layer:%' THEN 'layer.' || SUBSTR(e.subject, 7) || '.submit' ELSE 'demand.' || e.subject || '.submit' END) AS whose
FROM everything e
