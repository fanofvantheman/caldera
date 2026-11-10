/* The same history read at period grain — the plan's grain — with the standard material (variants rolled to parent). */
MODEL (name history.shipments_period, kind FULL, grain (standard_material, ship_to_code, period));
SELECT m.standard_material, s.ship_to_code, s.account_code, s.period, s.fiscal_year,
       SUM(s.cases) AS cases, SUM(s.tonnes) AS tonnes, SUM(s.gross_sales) AS gross_sales, SUM(s.net_sales) AS net_sales,
       SUM(CASE WHEN s.is_promo_week THEN s.cases END) AS promo_cases
FROM history.shipments s
JOIN dims.dim_material m ON m.material_code = s.material_code
GROUP BY ALL
