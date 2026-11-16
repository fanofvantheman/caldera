/* The material of a case input by input: version × material × period × input at the material's primary plant — the bill's
   quantity per case and the input's price in the period, its pool read from its type. The planned unit cost's material
   pools are the sum of these; the material price and usage variances read them against the standard (DEC-20261116-02
   point 5). The price is the price in force (price × index ÷ 100); the utility in the bill is the schedule's energy, an
   overhead pool, and is not priced here. */
MODEL (name plan.planned_material_input, kind FULL, grain (version_id, material_code, period, input_code));
WITH mats AS (SELECT version_id, material_code, period, plant_code FROM plan.planned_labour),
idx AS (SELECT version_id, period, assumption_code, value FROM plan.assumption_in_force),
price AS (
  SELECT m.version_id, m.period, p.material_code AS input, p.price * COALESCE(i.value, 100) / 100 AS price
  FROM (SELECT DISTINCT version_id, period FROM mats) m CROSS JOIN dims.reg_input_price p
  LEFT JOIN idx i ON i.version_id = m.version_id AND i.period = m.period AND i.assumption_code = p.index_code
  WHERE p.price_from <= m.period
  QUALIFY ROW_NUMBER() OVER (PARTITION BY m.version_id, m.period, p.material_code ORDER BY p.price_from DESC) = 1
)
SELECT m.version_id, m.material_code, m.period, m.plant_code, b.component_material AS input_code, pl.pool_code,
       SUM(b.quantity_per_case) AS quantity, ANY_VALUE(pr.price) AS price, SUM(b.quantity_per_case) * ANY_VALUE(pr.price) AS per_case
FROM mats m
JOIN dims.ref_bom b ON b.parent_material = m.material_code AND b.plant_code = m.plant_code
JOIN dims.dim_input_material im ON im.material_code = b.component_material AND im.material_type <> 'utility'
JOIN dims.ref_cost_pool pl ON pl.input_type = im.material_type
JOIN price pr ON pr.version_id = m.version_id AND pr.period = m.period AND pr.input = b.component_material
GROUP BY ALL
