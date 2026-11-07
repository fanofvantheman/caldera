/* The planning assumptions register: one shared set of rates and indices valuing every plan on a version. */
MODEL (name dims.reg_assumption, kind FULL, grain (assumption_code, version_id, period));
SELECT assumption_code::TEXT AS assumption_code, assumption_name::TEXT AS assumption_name, kind::TEXT AS kind, version_id::TEXT AS version_id,
       COALESCE(NULLIF(period::TEXT, ''), 'ALL') AS period, value::DOUBLE AS value, owner::TEXT AS owner, note::TEXT AS note
FROM bronze.reg_assumption
