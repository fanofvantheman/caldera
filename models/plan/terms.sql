/* The terms register: each account's instruments with the attributes that decide the formula and where it lands —
   flow position, driver basis, conditionality, settlement timing — as independent columns. The band is presentation. */
MODEL (name plan.terms, kind FULL, grain (instrument_code), audits (terms_vocabulary));
SELECT t.instrument_code::TEXT AS instrument_code, t.account_code::TEXT AS account_code, t.instrument_kind::TEXT AS instrument_kind,
       t.driver_basis::TEXT AS driver_basis, t.rate::DOUBLE AS rate, t.flow_position::TEXT AS flow_position, t.conditionality::TEXT AS conditionality,
       t.settlement_timing::TEXT AS settlement_timing, t.scope_material::TEXT AS scope_material, t.valid_from::DATE AS valid_from,
       NULLIF(t.valid_to::TEXT, '')::DATE AS valid_to, NULLIF(t.note::TEXT, '') AS note, a.account_code IS NOT NULL AS account_known
FROM bronze.reg_terms t LEFT JOIN dims.dim_account a ON a.account_code = t.account_code
