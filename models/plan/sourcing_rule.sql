/* The second sourcing rule (DEC-20261117-02 point 3): stocking node × material → the plant that supplies it, with a share.
   The default is the material's primary route — where the plant is the stocking point the step is nil. A declared rule
   (reg_sourcing: the latest act per node × material × plant; a share of 0 takes a plant out) replaces the default for its
   node × material whole; its shares are scaled to sum to one. */
MODEL (name plan.sourcing_rule, kind FULL, grain (node_code, material_code, plant_code));
WITH acts AS (
  SELECT act_id::TEXT AS act_id, node_code::TEXT AS node_code, material_code::TEXT AS material_code, plant_code::TEXT AS plant_code,
         TRY_CAST(share::TEXT AS DOUBLE) AS share, reason::TEXT AS reason, entered_by::TEXT AS entered_by, entered_at::TEXT AS entered_at, source_file, file_row_number
  FROM bronze.reg_sourcing
),
declared AS (
  SELECT * FROM acts
  QUALIFY ROW_NUMBER() OVER (PARTITION BY node_code, material_code, plant_code ORDER BY entered_at DESC, source_file DESC, file_row_number DESC) = 1
),
dc AS (SELECT node_code FROM dims.dim_node WHERE node_kind <> 'plant'),
routed AS (SELECT material_code, plant_code FROM dims.ref_route WHERE is_primary),
defaults AS (
  SELECT d.node_code, r.material_code, r.plant_code, 1.0 AS share, 'primary route' AS basis, NULL::TEXT AS act_id, NULL::TEXT AS reason
  FROM dc d CROSS JOIN routed r
  WHERE NOT EXISTS (SELECT 1 FROM declared x WHERE x.node_code = d.node_code AND x.material_code = r.material_code)
),
rules AS (
  SELECT node_code, material_code, plant_code, share / SUM(share) OVER (PARTITION BY node_code, material_code) AS share, 'declared' AS basis, act_id, reason
  FROM declared WHERE share > 0
)
SELECT * FROM defaults UNION ALL SELECT * FROM rules
