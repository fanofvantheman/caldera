/* The material of a case input by input: version × material × period × input at the material's primary plant — the bill's
   quantity per case and the input's price in the period, its pool read from its type. The planned unit cost's material
   pools are the sum of these; the material price and usage variances read them against the standard (DEC-20261116-02
   point 5). The quantity is the bill × the plant's usage assumption (% of the bill; 100 until someone moves it). The price
   is a key raw material's consumption cost in the period — its opening cost basis — read as given from the material
   balance (plan.material_stock, DEC-20261116-04 point 5, DEC-20261120-02 point 7), and any other input's price in force (price × index ÷ 100); the utility
   in the bill is the schedule's energy, an overhead pool, and is not priced here. */
MODEL (name plan.planned_material_input, kind FULL, grain (version_id, material_code, period, input_code));
WITH mats AS (SELECT version_id, material_code, period, plant_code FROM plan.planned_labour),
avg AS (                                              -- a key raw material: what its consumption is valued at in the period (DEC-20261120-02 point 7)
  SELECT version_id, input_code, plant_code, period, COALESCE(consumption_value / NULLIF(consumption_quantity, 0), average_cost) AS avg_cost
  FROM plan.material_stock
)
SELECT m.version_id, m.material_code, m.period, m.plant_code, b.component_material AS input_code, pl.pool_code,
       SUM(b.quantity_per_case) * ANY_VALUE(COALESCE(u.value, 100)) / 100 AS quantity,
       ANY_VALUE(COALESCE(a.avg_cost, pr.price)) AS price, ANY_VALUE(a.avg_cost IS NOT NULL) AS from_stock, ANY_VALUE(pr.price) AS price_in_force,
       SUM(b.quantity_per_case) * ANY_VALUE(COALESCE(u.value, 100)) / 100 * ANY_VALUE(COALESCE(a.avg_cost, pr.price)) AS per_case
FROM mats m
JOIN dims.ref_bom b ON b.parent_material = m.material_code AND b.plant_code = m.plant_code
JOIN dims.dim_input_material im ON im.material_code = b.component_material AND im.material_type <> 'utility'
JOIN dims.ref_cost_pool pl ON pl.input_type = im.material_type
JOIN plan.input_price_in_force pr ON pr.version_id = m.version_id AND pr.period = m.period AND pr.input_code = b.component_material
LEFT JOIN avg a ON a.version_id = m.version_id AND a.input_code = b.component_material AND a.plant_code = m.plant_code AND a.period = m.period
LEFT JOIN plan.assumption_in_force u ON u.version_id = m.version_id AND u.period = m.period AND u.assumption_code = 'USAGE_' || m.plant_code
GROUP BY ALL
