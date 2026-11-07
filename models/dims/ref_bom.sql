/* The abbreviated bill of materials: finished material → key components, quantity per case, by plant and version.
   Single-level rows; depth is a question for the explosion, not a column. */
MODEL (name dims.ref_bom, kind FULL, grain (bom_version, plant_code, parent_material, component_material), audits (bom_component_known));
SELECT b.bom_version::TEXT AS bom_version, b.plant_code::TEXT AS plant_code, b.parent_material::TEXT AS parent_material,
       b.component_material::TEXT AS component_material, b.quantity_per_case::DOUBLE AS quantity_per_case, b.uom::TEXT AS uom,
       b.valid_from::DATE AS valid_from, NULLIF(b.valid_to::TEXT, '')::DATE AS valid_to,
       i.material_code IS NOT NULL AS component_known
FROM bronze.ref_bom b
LEFT JOIN bronze.dim_input_material i ON i.material_code = b.component_material
