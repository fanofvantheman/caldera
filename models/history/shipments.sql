/* Shipments by material × ship-to × week: the history the baseline is fitted from, with what each row invoiced — gross at
   list and net sales — because history is revenue and units and price is the derived figure. Period and the account come
   from the calendar and the customer structure, never from the file. */
MODEL (name history.shipments, kind FULL, grain (material_code, ship_to_code, week_id),
       audits (shipment_material_known, shipment_ship_to_known, shipment_week_known));
SELECT s.week_id::TEXT AS week_id, w.period AS period, w.fiscal_year, w.fiscal_week, s.material_code::TEXT AS material_code,
       s.ship_to_code::TEXT AS ship_to_code, st.account_code, s.cases::DOUBLE AS cases, s.tonnes::DOUBLE AS tonnes,
       s.gross_sales::DOUBLE AS gross_sales, s.net_sales::DOUBLE AS net_sales,
       s.is_promo_week::TEXT = 'Y' AS is_promo_week,
       m.material_code IS NOT NULL AS material_known, st.ship_to_code IS NOT NULL AS ship_to_known, w.week_id IS NOT NULL AS week_known
FROM bronze.shipments s
LEFT JOIN dims.dim_week w ON w.week_id = s.week_id
LEFT JOIN dims.dim_material m ON m.material_code = s.material_code
LEFT JOIN dims.dim_ship_to st ON st.ship_to_code = s.ship_to_code
