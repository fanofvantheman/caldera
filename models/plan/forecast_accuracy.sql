/* The plan judged as a forecast: what the cycle `lag` periods before said against what shipped, for every closed period
   a snapshot covers, at standard material × account × period, with the material and customer structures beside so a
   reading at any node sums its leaves. Accuracy is read from this, never stored: 1 − Σ|error| / Σactual (weighted
   absolute error) and bias Σerror / Σactual, at whatever grain the page asks. A material shipped but never forecast
   counts as a miss; a material forecast that never shipped counts as a miss too. */
MODEL (name plan.forecast_accuracy, kind FULL, grain (lag, standard_material, account_code, period));
WITH actual AS (
  SELECT s.standard_material, s.account_code, s.period, s.fiscal_year, SUM(s.cases) AS cases
  FROM history.shipments_period s JOIN dims.dim_period p ON p.period = s.period AND p.period_state = 'CLOSED'
  WHERE s.period IN (SELECT DISTINCT period FROM history.forecast_snapshot)
  GROUP BY ALL
),
lags AS (SELECT DISTINCT lag FROM history.forecast_snapshot)
SELECT l.lag, COALESCE(f.standard_material, a.standard_material) AS standard_material, COALESCE(f.account_code, a.account_code) AS account_code,
       COALESCE(f.period, a.period) AS period, COALESCE(f.fiscal_year, a.fiscal_year) AS fiscal_year,
       f.forecast_version, COALESCE(f.cases, 0) AS forecast_cases, COALESCE(a.cases, 0) AS actual_cases,
       COALESCE(f.cases, 0) - COALESCE(a.cases, 0) AS error, ABS(COALESCE(f.cases, 0) - COALESCE(a.cases, 0)) AS abs_error,
       m.category_code, m.category_name, m.product_code, m.product_name, m.material_name,
       ac.planning_unit, ac.planning_unit_name
FROM lags l
JOIN history.forecast_snapshot f ON f.lag = l.lag
FULL OUTER JOIN actual a ON a.standard_material = f.standard_material AND a.account_code = f.account_code AND a.period = f.period
LEFT JOIN dims.dim_material m ON m.material_code = COALESCE(f.standard_material, a.standard_material)
LEFT JOIN dims.dim_account ac ON ac.account_code = COALESCE(f.account_code, a.account_code)
