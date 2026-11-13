/* The chart of accounts the cost lines are planned on — one for both entities (Riverbend moved onto Caldera's accounts at
   acquisition and kept its cost centres) — each account in a cost family for reading. */
MODEL (name dims.dim_gl_account, kind FULL, grain (account_code));
SELECT account_code::TEXT AS account_code, account_name::TEXT AS account_name, cost_family::TEXT AS cost_family, is_labour = 'Y' AS is_labour
FROM bronze.dim_gl_account
