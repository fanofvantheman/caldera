/* Where Finance's volume and price come from, declared per account × material: fed — the demand plan valued is the
   source and Finance types over it — or built — there is no source and Finance keeps the figures itself. The account's
   row (material ALL) is its default; a material row is an exception. What is not declared is fed. */
MODEL (name plan.finance_source, kind FULL, grain (account_code, material_code));
SELECT s.account_code::TEXT AS account_code, s.material_code::TEXT AS material_code, s.source::TEXT AS source, a.account_name,
       CASE WHEN s.material_code = 'ALL' THEN 'All materials' ELSE m.material_name END AS material_name,
       s.declared_by::TEXT AS declared_by, s.declared_on::TEXT AS declared_on, NULLIF(s.note::TEXT, '') AS note,
       a.account_code IS NOT NULL AND (s.material_code = 'ALL' OR m.material_code IS NOT NULL) AND s.source IN ('fed', 'built') AS valid
FROM bronze.reg_finance_source s
LEFT JOIN dims.dim_account a ON a.account_code = s.account_code
LEFT JOIN dims.dim_material m ON m.material_code = s.material_code
