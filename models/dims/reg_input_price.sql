/* Each input's price per its base unit from a period, and the index it moves with (the assumptions register): the price
   in a period is this × the index then ÷ 100. Imported inputs are priced landed. */
MODEL (name dims.reg_input_price, kind FULL, grain (material_code, price_from));
SELECT material_code::TEXT AS material_code, price::DOUBLE AS price, price_from::TEXT AS price_from, NULLIF(index_code::TEXT, '') AS index_code,
       NULLIF(note::TEXT, '') AS note
FROM bronze.reg_input_price
