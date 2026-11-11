/* Price lists: list price per case by material, effective-dated, with the increase event that produced each row. Finance
   changes a price by placing a new row from a date — never by editing the row in force; the latest act per list ×
   material × date is the row, and a row runs until the day before the next one starts (or its own end, if earlier). */
MODEL (name history.price_list, kind FULL, grain (price_list, material_code, valid_from));
WITH acts AS (
  SELECT p.*, ROW_NUMBER() OVER (PARTITION BY p.price_list, p.material_code, p.valid_from::DATE
                                 ORDER BY CASE WHEN p.source_file LIKE '20%' THEN p.source_file ELSE '0' END DESC, p.file_row_number DESC) AS recency
  FROM bronze.price_list p
),
dated AS (
  SELECT a.*, a.valid_from::DATE AS vf, NULLIF(a.valid_to::TEXT, '')::DATE AS vt,
         LEAD(a.valid_from::DATE) OVER (PARTITION BY a.price_list, a.material_code ORDER BY a.valid_from::DATE) AS next_from
  FROM acts a WHERE a.recency = 1
)
SELECT price_list::TEXT AS price_list, material_code::TEXT AS material_code, currency::TEXT AS currency, price_per_case::DOUBLE AS price_per_case,
       vf AS valid_from,
       CASE WHEN next_from IS NULL THEN vt WHEN vt IS NULL THEN (next_from - INTERVAL 1 DAY)::DATE ELSE LEAST(vt, (next_from - INTERVAL 1 DAY)::DATE) END AS valid_to,
       NULLIF(event::TEXT, '') AS price_event, source_file LIKE '20%' AS placed_by_finance
FROM dated
