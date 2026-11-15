/* What the capital plan charges the opex schedule: depreciation on 6750 and lease charges on 6700, by version × entity ×
   the plan's cost centre × period. The schedule's lines here are filled by the capital plan, never typed. A charge at a
   factory cost centre is fixed factory overhead — the standard's (DEC-20261115-01 point 2); elsewhere a period cost. */
MODEL (name plan.capex_charge, kind FULL, grain (version_id, entity_code, cost_centre_code, account_code, period));
SELECT version_id, entity_code, cost_centre_code, '6750' AS account_code, period, SUM(depreciation) AS amount
FROM plan.capex_line WHERE kind <> 'lease' GROUP BY ALL
UNION ALL
SELECT version_id, entity_code, cost_centre_code, '6700', period, SUM(lease_charge)
FROM plan.capex_line WHERE kind = 'lease' GROUP BY ALL
