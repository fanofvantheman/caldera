/* What each earlier cycle's latest view said, kept: the plan at material × account × period as it stood `lag` periods
   before the period, read at the plan's grain (variants rolled to the standard material). This is the forecast the plan
   is later judged as; the judgement is plan.forecast_accuracy. */
MODEL (name history.forecast_snapshot, kind FULL, grain (forecast_version, lag, standard_material, account_code, period));
SELECT f.forecast_version::TEXT AS forecast_version, f.cycle_period::TEXT AS cycle_period, f.lag::INT AS lag, f.period::TEXT AS period,
       p.fiscal_year, m.standard_material, f.account_code::TEXT AS account_code, SUM(f.cases::DOUBLE) AS cases
FROM bronze.forecast_snapshot f
JOIN dims.dim_material m ON m.material_code = f.material_code
LEFT JOIN dims.dim_period p ON p.period = f.period
GROUP BY ALL
