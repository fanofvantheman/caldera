/* Each stage's state on each Plan (DEC-20261118-04 points 2, 5, 6): read from the register of acts — hand over, reopen —
   by the holder of the stage's right. A run of stages whose handovers are compressed is one unit, handed over by its last
   stage. A unit is
     open          never handed over, or reopened since
     handed over   its latest act is a handover
     behind        handed over, and the unit before it has been handed over again since — its proposal is new, its
                   owner's interventions stand beside it, nothing typed is recalculated over
   A closed Plan reads every stage handed over. `snapshot` says whether the latest handover or reopen took the figures the
   stage after reads (the onboarding handover took none: until it is handed over again the stage after reads it as it stands). */
MODEL (name plan.stage_state, kind FULL, grain (version_id, stage));
WITH acts AS (
  SELECT act_id::TEXT AS act_id, version_id::TEXT AS version_id, stage::TEXT AS stage, action::TEXT AS action, reason::TEXT AS reason,
         entered_by::TEXT AS entered_by, entered_at::TEXT AS entered_at, COALESCE(snapshot::TEXT, '') <> '' AS snapshot, source_file, file_row_number
  FROM bronze.reg_stage_act
),
set AS (SELECT * FROM plan.stage_setting),
unit AS (                                              -- a stage's unit: the first stage after the last kept handover before it
  SELECT s.ord, s.stage, s.stage_name, s.handover_kept,
         COALESCE((SELECT MAX(p.ord) + 1 FROM set p WHERE p.ord < s.ord AND p.handover_kept), 1) AS unit_from,
         (SELECT MIN(n.ord) FROM set n WHERE n.ord >= s.ord AND n.handover_kept) AS unit_to
  FROM set s
),
versions AS (SELECT v.version_id, s.state AS plan_state FROM dims.ctl_version v LEFT JOIN plan.version_state s USING (version_id) WHERE v.version_kind <> 'actual'),
last AS (
  SELECT a.*, r.ord FROM acts a JOIN dims.ref_stage r USING (stage)
  QUALIFY ROW_NUMBER() OVER (PARTITION BY a.version_id, a.stage ORDER BY a.entered_at DESC, a.source_file DESC, a.file_row_number DESC) = 1
),
handed AS (                                            -- each unit's last handover, read at its last stage
  SELECT a.version_id, r.ord, MAX(a.entered_at) AS handed_at FROM acts a JOIN dims.ref_stage r USING (stage) WHERE a.action = 'hand_over' GROUP BY ALL
),
grid AS (
  SELECT v.version_id, v.plan_state, u.*, l.action AS last_action, l.entered_at AS last_at, l.entered_by AS last_by, l.reason AS last_reason, l.snapshot,
         h.handed_at
  FROM versions v CROSS JOIN unit u
  LEFT JOIN last l ON l.version_id = v.version_id AND l.ord = u.unit_to
  LEFT JOIN handed h ON h.version_id = v.version_id AND h.ord = u.unit_to
)
SELECT g.version_id, g.ord, g.stage, g.stage_name, g.handover_kept, g.unit_from, g.unit_to,
       CASE WHEN g.plan_state = 'closed' THEN 'handed over'
            WHEN g.last_action IS NULL OR g.last_action = 'reopen' THEN 'open'
            WHEN p.handed_at IS NOT NULL AND p.handed_at > g.handed_at THEN 'behind'
            ELSE 'handed over' END AS state,
       g.last_action, g.last_at, g.last_by, g.last_reason, g.handed_at, COALESCE(g.snapshot, FALSE) AS snapshot,
       p.handed_at AS before_handed_at
FROM grid g
LEFT JOIN grid p ON p.version_id = g.version_id AND p.unit_to = g.unit_from - 1 AND p.ord = p.unit_to
