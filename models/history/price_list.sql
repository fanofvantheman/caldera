/* Price lists: list price per case by material, effective-dated, with the increase event that produced each row. */
MODEL (name history.price_list, kind FULL, grain (price_list, material_code, valid_from));
SELECT price_list::TEXT AS price_list, material_code::TEXT AS material_code, currency::TEXT AS currency, price_per_case::DOUBLE AS price_per_case,
       valid_from::DATE AS valid_from, NULLIF(valid_to::TEXT, '')::DATE AS valid_to, NULLIF(event::TEXT, '') AS price_event
FROM bronze.price_list
