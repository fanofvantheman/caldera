/* The planning assumptions register: one shared set of rates and indices valuing every plan on a version — the value
   each version was named with. A version named from a base takes its base's values as its own at naming: they are
   written onto it as rows from ALL in the amendment register, carrying the value they were copied from, and read here,
   not as amendments. */
MODEL (name dims.reg_assumption, kind FULL, grain (assumption_code, version_id, period));
SELECT assumption_code::TEXT AS assumption_code, assumption_name::TEXT AS assumption_name, kind::TEXT AS kind, version_id::TEXT AS version_id,
       COALESCE(NULLIF(period::TEXT, ''), 'ALL') AS period, value::DOUBLE AS value, owner::TEXT AS owner, note::TEXT AS note
FROM bronze.reg_assumption
UNION ALL
SELECT * FROM (SELECT a.assumption_code::TEXT, n.assumption_name, n.kind, a.version_id::TEXT, 'ALL', a.value::DOUBLE, a.entered_by::TEXT, NULLIF(a.note::TEXT, '')
FROM bronze.reg_assumption_amend a
JOIN (SELECT assumption_code, ANY_VALUE(assumption_name) AS assumption_name, ANY_VALUE(kind) AS kind FROM bronze.reg_assumption GROUP BY 1) n
  ON n.assumption_code = a.assumption_code
WHERE a.valid_from = 'ALL'
QUALIFY ROW_NUMBER() OVER (PARTITION BY a.version_id, a.assumption_code ORDER BY a.source_file DESC, a.file_row_number DESC) = 1)
