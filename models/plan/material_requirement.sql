/* What production draws of each key raw material (DEC-20261116-04 point 2): by version × input × plant × period, the
   plan's cases made at the plant × the high-level bill × expected usage (the plant's usage assumption, % of the bill;
   100 until someone moves it). Cases made are the inventory plan's production requirement at each plant — a typed
   production quantity where one stands (DEC-20261117-02 point 6), in place of the demand plan's cases sold. */
MODEL (name plan.material_requirement, kind FULL, grain (version_id, input_code, plant_code, period));
WITH cases AS (SELECT version_id, material_code, plant_code, period, quantity AS cases FROM plan.production_handed_over)   -- as production last handed it over (DEC-20261118-04)
SELECT c.version_id, b.component_material AS input_code, c.plant_code, c.period,
       SUM(c.cases * b.quantity_per_case * COALESCE(u.value, 100) / 100) AS quantity, ANY_VALUE(COALESCE(u.value, 100)) AS usage_pct
FROM cases c
JOIN dims.ref_bom b ON b.parent_material = c.material_code AND b.plant_code = c.plant_code
JOIN dims.ref_key_material k ON k.input_code = b.component_material AND k.plant_code = c.plant_code
LEFT JOIN plan.assumption_in_force u ON u.version_id = c.version_id AND u.period = c.period AND u.assumption_code = 'USAGE_' || c.plant_code
GROUP BY c.version_id, b.component_material, c.plant_code, c.period
