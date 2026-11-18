/* What the inventory stage reads (DEC-20261118-04 point 2): the demand plan's cases by stocking node × material × week as
   last handed over by the stage before it — the figures the handover (or a later reopen) took, from the stage acts'
   snapshots (reg_stage_snap_demand) — not the demand plan's latest release. Where that handover is compressed away
   (the deployment runs the stages as one) or took no snapshot (the onboarding handover), the demand plan as it stands. */
MODEL (name plan.demand_handed_over, kind FULL, grain (version_id, node_code, material_code, week_id));
WITH unit AS (SELECT version_id, unit_to, handover_kept FROM plan.stage_state WHERE stage = 'valuation'),
acts AS (
  SELECT a.act_id::TEXT AS act_id, a.version_id::TEXT AS version_id, a.stage::TEXT AS stage, a.entered_at::TEXT AS entered_at,
         COALESCE(a.snapshot::TEXT, '') <> '' AS has_snapshot, r.ord
  FROM bronze.reg_stage_act a JOIN dims.ref_stage r ON r.stage = a.stage::TEXT
),
latest AS (                                            -- the latest act of the unit's handing stage, and whether it took the figures
  SELECT a.* FROM acts a JOIN unit u ON u.version_id = a.version_id AND a.ord = u.unit_to
  WHERE u.handover_kept
  QUALIFY ROW_NUMBER() OVER (PARTITION BY a.version_id ORDER BY a.entered_at DESC, a.act_id DESC) = 1
),
snap AS (
  SELECT s.version_id::TEXT AS version_id, s.node_code::TEXT AS node_code, s.material_code::TEXT AS material_code, s.week_id::TEXT AS week_id,
         TRY_CAST(s.cases::TEXT AS DOUBLE) AS cases, s.act_id::TEXT AS act_id
  FROM bronze.reg_stage_snap_demand s JOIN latest l ON l.act_id = s.act_id::TEXT AND l.has_snapshot
),
live AS (
  SELECT d.version_id, n.node_code, d.material_code, d.week_id, SUM(d.cases) AS cases
  FROM plan.unconstrained_demand d JOIN dims.ref_serving_node n USING (ship_to_code)
  WHERE d.version_id NOT IN (SELECT version_id FROM snap) GROUP BY ALL
)
SELECT version_id, node_code, material_code, week_id, cases, 'handed over' AS read_as, act_id FROM snap
UNION ALL SELECT version_id, node_code, material_code, week_id, cases, 'as it stands', NULL FROM live
