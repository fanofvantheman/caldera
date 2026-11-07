/* Finished materials with the attributes the plan uses: the nesting levels (category → product → format → material)
   as columns, the flags and links beside them. A variant rolls to its parent material for every reading. */
MODEL (name dims.dim_material, kind FULL, grain (material_code), audits (material_product_exists));
SELECT m.material_code::TEXT AS material_code, m.material_name::TEXT AS material_name, m.product_code::TEXT AS product_code,
       p.product_name::TEXT AS product_name, m.format_code::TEXT AS format_code, f.format_name::TEXT AS format_name,
       m.category_code::TEXT AS category_code, c.category_name::TEXT AS category_name, m.segment::TEXT AS segment,
       m.brand::TEXT AS brand, NULLIF(m.sub_brand::TEXT, '') AS sub_brand, m.price_tier::TEXT AS price_tier, m.branded::TEXT AS branded,
       m.seasonal_flag::TEXT AS seasonal_flag, m.lifecycle_status::TEXT AS lifecycle_status,
       NULLIF(m.parent_material::TEXT, '') AS parent_material, COALESCE(NULLIF(m.parent_material::TEXT, ''), m.material_code::TEXT) AS standard_material,
       m.units_per_case::INT AS units_per_case, m.case_net_kg::DOUBLE AS case_net_kg, NULLIF(m.campaign_input::TEXT, '') AS campaign_input,
       p.product_code IS NOT NULL AS product_exists
FROM bronze.dim_material m
LEFT JOIN bronze.dim_product p ON p.product_code = m.product_code
LEFT JOIN bronze.dim_format f ON f.format_code = m.format_code
LEFT JOIN bronze.dim_category c ON c.category_code = m.category_code
