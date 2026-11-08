/* The plan as a review reads it: by fiscal year, the closed periods of the current year as actuals and the open ones as
   plan, so a year's total is year-to-date actual plus the plan for the rest. One row per version × standard material ×
   account × period, with the source of the number; the plan rows are unconstrained demand at review grain, the actual
   rows are shipments at the same grain for every closed period of a fiscal year the version's horizon touches. */
MODEL (name plan.demand_review, kind FULL, grain (version_id, standard_material, account_code, period));
WITH years AS (
  SELECT v.version_id, p.fiscal_year
  FROM dims.ctl_version v JOIN dims.dim_period p ON p.period BETWEEN v.horizon_start AND v.horizon_end
  WHERE v.version_kind <> 'actual' GROUP BY ALL
)
SELECT u.version_id, u.standard_material, u.account_code, u.period, u.fiscal_year, 'plan' AS source, u.cases, u.tonnes
FROM plan.unconstrained_demand_period u
UNION ALL
SELECT y.version_id, s.standard_material, s.account_code, s.period, s.fiscal_year, 'actual' AS source, SUM(s.cases), SUM(s.tonnes)
FROM years y
JOIN dims.ctl_version v ON v.version_id = y.version_id
JOIN history.shipments_period s ON s.fiscal_year = y.fiscal_year AND s.period < v.horizon_start
JOIN dims.dim_period p ON p.period = s.period AND p.period_state = 'CLOSED'
GROUP BY ALL
