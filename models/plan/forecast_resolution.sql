/* What people have decided about the disagreements between the forecasting system's structures and the plan's: read
   from the doors' act register (door FCS); the latest act per item is in force and stands for every later run until
   someone acts again. Two kinds of item. Theirs, not ours — a material code the plan does not have (keyed by the code,
   whatever accounts it was sent for): the same as one of ours, placed under a product, or left out. Ours, not theirs — a
   material × account the plan calculates and the run does not carry: keep our calculation, or zero on purpose. */
MODEL (name plan.forecast_resolution, kind FULL, grain (sender, kind, item_code, account_code), audits (forecast_resolution_target_known));
SELECT a.act_id AS resolution_id, a.door AS sender, a.kind, a.item_code, a.scope_code AS account_code, a.resolution, a.target_code,
       COALESCE(m.material_name, p.product_name) AS target_name, a.reason, a.acted_by, a.acted_at, a.acts,
       CASE a.resolution WHEN 'same_as' THEN m.material_code IS NOT NULL WHEN 'place_under' THEN p.product_code IS NOT NULL ELSE TRUE END AS target_known
FROM plan.door_act a
LEFT JOIN dims.dim_material m ON a.resolution = 'same_as' AND m.material_code = a.target_code
LEFT JOIN (SELECT DISTINCT product_code, product_name FROM dims.dim_material) p ON a.resolution = 'place_under' AND p.product_code = a.target_code
WHERE a.door = 'FCS' AND a.in_force
