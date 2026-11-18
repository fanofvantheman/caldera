/* A planned unit cost component typed where its drivers are missing (DEC-20261116-02 point 7): a figure per case at a
   material × plant × period on a plan, for one of the four components, by whoever holds Finance's entry right — an act on
   the record like any other figure. The latest act per cell stands; a withdrawal names an act and takes it out, and the
   one before it stands again. A typed component replaces its driver-based figure in plan.planned_unit_cost. */
MODEL (name plan.unit_cost_act, kind FULL, grain (version_id, material_code, plant_code, period, component));
WITH acts AS (
  SELECT act_id::TEXT AS act_id, action::TEXT AS action, NULLIF(withdraws::TEXT, '') AS withdraws, version_id::TEXT AS version_id,
         material_code::TEXT AS material_code, plant_code::TEXT AS plant_code, period::TEXT AS period, component::TEXT AS component,
         TRY_CAST(NULLIF(per_case::TEXT, '') AS DOUBLE) AS per_case, reason::TEXT AS reason, entered_by::TEXT AS entered_by,
         entered_at::TEXT AS entered_at, source_file, file_row_number
  FROM bronze.reg_unit_cost_act
)
SELECT a.act_id, a.version_id, a.material_code, a.plant_code, a.period, a.component, a.per_case, a.reason, a.entered_by, a.entered_at
FROM acts a
WHERE a.action = 'set' AND a.per_case IS NOT NULL
  AND a.component IN ('material', 'labour', 'variable_overhead', 'fixed_overhead')
  AND a.act_id NOT IN (SELECT withdraws FROM acts WHERE action = 'withdraw' AND withdraws IS NOT NULL)
QUALIFY ROW_NUMBER() OVER (PARTITION BY a.version_id, a.material_code, a.plant_code, a.period, a.component
                           ORDER BY a.entered_at DESC, a.source_file DESC, a.file_row_number DESC) = 1
