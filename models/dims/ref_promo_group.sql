/* Promo groups: reusable sets of materials promoted together — a scope object events point at, not a material attribute. */
MODEL (name dims.ref_promo_group, kind FULL, grain (promo_group_code, material_code));
SELECT promo_group_code::TEXT AS promo_group_code, promo_group_name::TEXT AS promo_group_name, material_code::TEXT AS material_code
FROM bronze.ref_promo_group
