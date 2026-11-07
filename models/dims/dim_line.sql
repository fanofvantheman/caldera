/* Production lines inside the plant hierarchy plant → area → line; machine capacity attaches here. */
MODEL (name dims.dim_line, kind FULL, grain (line_code), audits (line_area_exists));
SELECT l.line_code::TEXT AS line_code, l.plant_code::TEXT AS plant_code, l.area_code::TEXT AS area_code, a.area_name::TEXT AS area_name,
       l.line_name::TEXT AS line_name, l.rate_uom::TEXT AS rate_uom, a.area_code IS NOT NULL AS area_exists
FROM bronze.dim_line l
LEFT JOIN bronze.dim_plant_area a ON a.plant_code = l.plant_code AND a.area_code = l.area_code
