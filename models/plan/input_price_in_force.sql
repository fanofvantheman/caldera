/* Each input's price in force by version × period: the register's price × its index in the assumptions ÷ 100 (an input
   with no index at its price). What a spot or campaign purchase pays, and what an input with no stock is valued at. */
MODEL (name plan.input_price_in_force, kind FULL, grain (version_id, period, input_code));
WITH vp AS (
  SELECT v.version_id, p.period FROM dims.ctl_version v JOIN dims.dim_period p ON p.period > v.from_period AND p.period <= v.plan_through
  WHERE v.version_kind <> 'actual' AND v.from_period IS NOT NULL
)
SELECT m.version_id, m.period, p.material_code AS input_code, p.price * COALESCE(i.value, 100) / 100 AS price, p.index_code
FROM vp m CROSS JOIN dims.reg_input_price p
LEFT JOIN plan.assumption_in_force i ON i.version_id = m.version_id AND i.period = m.period AND i.assumption_code = p.index_code
WHERE p.price_from <= m.period
QUALIFY ROW_NUMBER() OVER (PARTITION BY m.version_id, m.period, p.material_code ORDER BY p.price_from DESC) = 1
