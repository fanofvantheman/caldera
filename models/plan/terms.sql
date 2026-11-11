/* The terms register: each account's instruments with the attributes that decide the formula and where it lands —
   flow position, driver basis, conditionality, settlement timing — as independent columns. The band is presentation.
   Effective-dated: Finance amends an instrument by placing a new row from a date, never by editing the row in force;
   the latest act per instrument × date is the row, and a row runs until the day before the next one starts (or its own
   end, if earlier). The co-op envelope is an instrument too — an annual amount, spent by the events that draw on it. */
MODEL (name plan.terms, kind FULL, grain (instrument_code, valid_from), audits (terms_vocabulary));
WITH acts AS (
  SELECT t.*, ROW_NUMBER() OVER (PARTITION BY t.instrument_code, t.valid_from::DATE
                                 ORDER BY CASE WHEN t.source_file LIKE '20%' THEN t.source_file ELSE '0' END DESC, t.file_row_number DESC) AS recency,
         CASE WHEN t.source_file LIKE '20%' THEN t.source_file END AS amended_by_file
  FROM bronze.reg_terms t
),
dated AS (
  SELECT a.*, a.valid_from::DATE AS vf, NULLIF(a.valid_to::TEXT, '')::DATE AS vt,
         LEAD(a.valid_from::DATE) OVER (PARTITION BY a.instrument_code ORDER BY a.valid_from::DATE) AS next_from
  FROM acts a WHERE a.recency = 1
)
SELECT d.instrument_code::TEXT AS instrument_code, d.account_code::TEXT AS account_code, d.instrument_kind::TEXT AS instrument_kind,
       d.driver_basis::TEXT AS driver_basis, d.rate::DOUBLE AS rate, d.flow_position::TEXT AS flow_position, d.conditionality::TEXT AS conditionality,
       d.settlement_timing::TEXT AS settlement_timing, d.scope_material::TEXT AS scope_material, d.vf AS valid_from,
       CASE WHEN d.next_from IS NULL THEN d.vt WHEN d.vt IS NULL THEN (d.next_from - INTERVAL 1 DAY)::DATE ELSE LEAST(d.vt, (d.next_from - INTERVAL 1 DAY)::DATE) END AS valid_to,
       NULLIF(d.note::TEXT, '') AS note, d.amended_by_file, a.account_code IS NOT NULL AS account_known,
       d.vt IS NULL OR d.vt >= d.vf AS window_ordered
FROM dated d LEFT JOIN dims.dim_account a ON a.account_code = d.account_code
