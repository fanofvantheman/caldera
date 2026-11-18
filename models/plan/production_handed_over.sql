/* What the materials stage reads (DEC-20261118-04 point 2): cases to make by material × plant × period as last handed
   over by production — the snapshot its handover (or a later reopen) took (reg_stage_snap_production) — not production's
   latest figures. Where that handover is compressed away or took no snapshot, production as it stands. */
MODEL (name plan.production_handed_over, kind FULL, grain (version_id, material_code, plant_code, period));
WITH unit AS (SELECT version_id, unit_to, handover_kept FROM plan.stage_state WHERE stage = 'production'),
acts AS (
  SELECT a.act_id::TEXT AS act_id, a.version_id::TEXT AS version_id, a.entered_at::TEXT AS entered_at,
         COALESCE(a.snapshot::TEXT, '') <> '' AS has_snapshot, r.ord
  FROM bronze.reg_stage_act a JOIN dims.ref_stage r ON r.stage = a.stage::TEXT
),
latest AS (
  SELECT a.* FROM acts a JOIN unit u ON u.version_id = a.version_id AND a.ord = u.unit_to
  WHERE u.handover_kept
  QUALIFY ROW_NUMBER() OVER (PARTITION BY a.version_id ORDER BY a.entered_at DESC, a.act_id DESC) = 1
),
snap AS (
  SELECT s.version_id::TEXT AS version_id, s.material_code::TEXT AS material_code, s.plant_code::TEXT AS plant_code, s.period::TEXT AS period,
         TRY_CAST(s.quantity::TEXT AS DOUBLE) AS quantity, s.act_id::TEXT AS act_id
  FROM bronze.reg_stage_snap_production s JOIN latest l ON l.act_id = s.act_id::TEXT AND l.has_snapshot
)
SELECT version_id, material_code, plant_code, period, quantity, 'handed over' AS read_as, act_id FROM snap
UNION ALL
SELECT version_id, material_code, plant_code, period, quantity, 'as it stands', NULL FROM plan.production_requirement
WHERE version_id NOT IN (SELECT version_id FROM snap)
