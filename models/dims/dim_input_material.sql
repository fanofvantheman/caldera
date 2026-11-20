/* Non-finished materials: ingredients, packaging, utilities — with the campaign window, commodity link and origin
   that decide how their price behaves, and the key material indicator: a purchase is prepared for a key material every
   month, so its stock is planned and valued (dims.ref_key_material); every other input is valued at its price in force. */
MODEL (name dims.dim_input_material, kind FULL, grain (material_code));
SELECT material_code::TEXT AS material_code, material_name::TEXT AS material_name, material_type::TEXT AS material_type,
       base_uom::TEXT AS base_uom, NULLIF(campaign_window::TEXT, '') AS campaign_window, NULLIF(commodity_link::TEXT, '') AS commodity_link,
       origin::TEXT AS origin, origin = 'IMPORT' AS is_imported, COALESCE(key_material::TEXT, '') = 'Y' AS is_key_material
FROM bronze.dim_input_material
