/* Each stage's state on each Plan (DEC-20261118-04 point 1, DEC-20261119-01 point 6): read from the register of acts —
   hand over, reopen — by the holder of the stage's right. The state records that the stage's owner has put their work in
   the Plan; it does not gate what the next stage reads: a Plan has one number for each figure, and every stage reads the
   stage before it as it stands. A run of stages whose handovers are compressed is one unit, handed over by its last stage.
     open          never handed over, or reopened since
     handed over   its latest act is a handover — the first sign-off, its owner's: locked, and it takes no more
     published     its latest act is a publication — the second sign-off, the IBP process's: the stages after it use it
                   (DEC-20261123-01 points 12–13; what a lock refuses and what publication moves is built for
                   purchasing's receipts alone)
   A closed Plan reads every stage handed over. Whether a stage is behind — not yet recalculated since an override or a
   port upstream of it, under manual recalculation — is not a state of the stage's owner and is read on the Stages page
   from what waits for a run (face/overrides.py). */
MODEL (name plan.stage_state, kind FULL, grain (version_id, stage));
WITH acts AS (
  SELECT act_id::TEXT AS act_id, version_id::TEXT AS version_id, stage::TEXT AS stage, action::TEXT AS action, reason::TEXT AS reason,
         entered_by::TEXT AS entered_by, entered_at::TEXT AS entered_at, source_file, file_row_number
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
)
SELECT v.version_id, u.ord, u.stage, u.stage_name, u.handover_kept, u.unit_from, u.unit_to,
       CASE WHEN v.plan_state = 'closed' THEN 'handed over'
            WHEN l.action IS NULL OR l.action = 'reopen' THEN 'open'
            WHEN l.action = 'publish' THEN 'published'
            ELSE 'handed over' END AS state,
       l.action AS last_action, l.entered_at AS last_at, l.entered_by AS last_by, l.reason AS last_reason
FROM versions v CROSS JOIN unit u
LEFT JOIN last l ON l.version_id = v.version_id AND l.ord = u.unit_to
