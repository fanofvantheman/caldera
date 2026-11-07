/* Routes: which line a material runs on at the plant, the rate at the rate-limiting step, changeover; primary and
   costed alternatives. Only the rate-limiting step is modelled. */
MODEL (name dims.ref_route, kind FULL, grain (route_code), audits (route_line_exists, route_material_exists));
SELECT r.route_code::TEXT AS route_code, r.plant_code::TEXT AS plant_code, r.material_code::TEXT AS material_code, r.line_code::TEXT AS line_code,
       r.is_rate_limiting::TEXT = 'Y' AS is_rate_limiting, r.rate_cases_per_hour::DOUBLE AS rate_cases_per_hour,
       r.changeover_hours::DOUBLE AS changeover_hours, r.is_primary::TEXT = 'Y' AS is_primary,
       r.valid_from::DATE AS valid_from, NULLIF(r.valid_to::TEXT, '')::DATE AS valid_to,
       l.line_code IS NOT NULL AS line_exists, m.material_code IS NOT NULL AS material_exists
FROM bronze.ref_route r
LEFT JOIN bronze.dim_line l ON l.line_code = r.line_code
LEFT JOIN bronze.dim_material m ON m.material_code = r.material_code
