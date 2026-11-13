/* What the labour model produces for every reader: labour cost by entity × the plan's cost centre × account × period ×
   version — wages on 6100, on-costs on 6150 — the same whichever model a line came from, so the schedule does not know.
   Only the cost centre's declared model is taken (dims.dim_cost_centre.labour_model). */
MODEL (name plan.labour_cost, kind FULL, grain (version_id, entity_code, cost_centre_code, account_code, period), audits (labour_model_declared));
SELECT version_id, entity_code, cost_centre_code, '6100' AS account_code, period, fiscal_year, model, SUM(wages) AS amount, SUM(fte) AS fte
FROM plan.labour_line WHERE model_declared GROUP BY ALL
UNION ALL
SELECT version_id, entity_code, cost_centre_code, '6150', period, fiscal_year, model, SUM(on_costs), NULL
FROM plan.labour_line WHERE model_declared GROUP BY ALL
