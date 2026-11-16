/* What production draws of each key raw material (DEC-20261116-04 point 2): by version × input × plant × period, the
   plan's cases made at the plant × the high-level bill × expected usage (the plant's usage assumption, % of the bill;
   100 until someone moves it). Until production is planned, cases made are the demand plan's cases at each material's
   primary plant. */
MODEL (name plan.material_requirement, kind FULL, grain (version_id, input_code, plant_code, period));
WITH cases AS (SELECT version_id, material_code, period, SUM(cases) AS cases FROM plan.demand_financialised GROUP BY ALL)
SELECT c.version_id, b.component_material AS input_code, r.plant_code, c.period,
       SUM(c.cases * b.quantity_per_case * COALESCE(u.value, 100) / 100) AS quantity, ANY_VALUE(COALESCE(u.value, 100)) AS usage_pct
FROM cases c
JOIN dims.ref_route r ON r.material_code = c.material_code AND r.is_primary
JOIN dims.ref_bom b ON b.parent_material = c.material_code AND b.plant_code = r.plant_code
JOIN dims.ref_key_material k ON k.input_code = b.component_material AND k.plant_code = r.plant_code
LEFT JOIN plan.assumption_in_force u ON u.version_id = c.version_id AND u.period = c.period AND u.assumption_code = 'USAGE_' || r.plant_code
GROUP BY c.version_id, b.component_material, r.plant_code, c.period
