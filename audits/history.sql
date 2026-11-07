AUDIT (name shipment_material_known);
SELECT DISTINCT material_code FROM @this_model WHERE NOT material_known;

AUDIT (name shipment_ship_to_known);
SELECT DISTINCT ship_to_code FROM @this_model WHERE NOT ship_to_known;

AUDIT (name shipment_week_known);
SELECT DISTINCT week_id FROM @this_model WHERE NOT week_known;
