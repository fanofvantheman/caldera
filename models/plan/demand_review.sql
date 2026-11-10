/* The plan as a review reads it: by fiscal year, the closed periods of the current year as actuals and the open ones as
   plan, so a year's total is year-to-date actual plus the plan for the rest. One row per version × standard material ×
   account × period, with the source of the number; the plan rows are unconstrained demand at review grain, the actual
   rows are shipments at the same grain for every closed period of a fiscal year the version's horizon touches. Money
   beside the cases on both: the actual rows carry what was invoiced, the plan rows the gross-to-net at the list and
   terms in force — history is revenue and units, the plan is units and a price, and this is where they meet. */
MODEL (name plan.demand_review, kind FULL, grain (version_id, standard_material, account_code, period));
WITH years AS (
  SELECT v.version_id, p.fiscal_year
  FROM dims.ctl_version v JOIN dims.dim_period p ON p.period BETWEEN v.horizon_start AND v.horizon_end
  WHERE v.version_kind <> 'actual' GROUP BY ALL
),
money AS (
  SELECT version_id, standard_material, account_code, period, SUM(gross_at_list) AS gross_sales, SUM(net_sales) AS net_sales
  FROM plan.demand_financialised GROUP BY ALL
)
SELECT u.version_id, u.standard_material, u.account_code, u.period, u.fiscal_year, 'plan' AS source, u.cases, u.tonnes,
       m.gross_sales, m.net_sales
FROM plan.unconstrained_demand_period u
LEFT JOIN money m ON m.version_id = u.version_id AND m.standard_material = u.standard_material AND m.account_code = u.account_code AND m.period = u.period
UNION ALL
SELECT y.version_id, s.standard_material, s.account_code, s.period, s.fiscal_year, 'actual' AS source, SUM(s.cases), SUM(s.tonnes),
       SUM(s.gross_sales), SUM(s.net_sales)
FROM years y
JOIN dims.ctl_version v ON v.version_id = y.version_id
JOIN history.shipments_period s ON s.fiscal_year = y.fiscal_year AND s.period < v.horizon_start
JOIN dims.dim_period p ON p.period = s.period AND p.period_state = 'CLOSED'
GROUP BY ALL
