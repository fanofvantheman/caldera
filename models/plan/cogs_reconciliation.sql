/* Planned reported cost of goods, by version × plant × period: at standard, each variance, as reported
   (DEC-20261116-02 point 8, DEC-20261117-01) — one form for an actual period and a planned one.
     plan period    cases made are cases sold (no production plan is valued yet), so every variance is recognised in the
                    period it arises and none is retained in stock; material price variance is already carried through the
                    stock's weighted average and recognised as it is consumed. At standard = Σ cases × the standard; the
                    lines per case × cases (a typed component whole); fixed overhead's spending and volume from the plant;
                    cases of a material with no standard at their planned unit cost; a year with no standard: the planned
                    cost and the fixed overhead not absorbed, unsplit.
                    As reported = cases × the planned unit cost + the fixed overhead not absorbed.
     actual period  the ledger read through the pools (plan.actual_cost_pool): the standard absorbed, the variance whole
                    by component, fixed split into spending and volume. As reported = the ledger's cost.
   The cases are the plan's (the demand plan's at each material's primary plant) or the actual's (shipped); Finance's typed
   volume does not move the cases made. */
MODEL (name plan.cogs_reconciliation, kind FULL, grain (version_id, plant_code, period));
WITH versions AS (SELECT version_id, from_period FROM dims.ctl_version WHERE version_kind <> 'actual' AND from_period IS NOT NULL),
cases_m AS (SELECT version_id, material_code, period, SUM(cases) AS cases FROM plan.demand_financialised GROUP BY ALL),
pm AS (
  SELECT u.version_id, u.plant_code, u.period, SUM(c.cases) AS cases, SUM(c.cases * u.unit_cost) AS at_planned,
         SUM(CASE WHEN v.std_cost IS NOT NULL THEN c.cases * v.std_cost END) AS at_standard,
         SUM(CASE WHEN v.std_cost IS NULL THEN c.cases * u.unit_cost END) AS no_standard,
         SUM(c.cases * v.mat_price) AS mat_price, SUM(c.cases * v.mat_usage) AS mat_usage,
         SUM(CASE WHEN v.typed_material THEN c.cases * v.var_material END) AS material_whole,
         SUM(c.cases * v.lab_rate) AS lab_rate, SUM(c.cases * v.lab_eff) AS lab_eff,
         SUM(CASE WHEN v.typed_labour THEN c.cases * v.var_labour END) AS labour_whole,
         SUM(c.cases * v.var_oh) AS var_oh, SUM(c.cases * v.fixed_oh) AS fixed_case,
         ANY_VALUE(v.set_on) AS set_on
  FROM plan.planned_unit_cost u
  JOIN versions x ON x.version_id = u.version_id AND u.period > x.from_period
  JOIN cases_m c ON c.version_id = u.version_id AND c.material_code = u.material_code AND c.period = u.period
  LEFT JOIN plan.cost_variance v ON v.version_id = u.version_id AND v.material_code = u.material_code AND v.period = u.period
  WHERE u.complete GROUP BY ALL
),
fv AS (SELECT version_id, plant_code, period, SUM(spending) AS spending, SUM(volume) AS volume FROM plan.fixed_variance GROUP BY ALL),
plan_rows AS (
  SELECT m.version_id, m.plant_code, m.period, 'plan' AS basis, m.set_on, m.cases, m.at_standard, m.mat_price, m.mat_usage, m.material_whole,
         m.lab_rate, m.lab_eff, m.labour_whole, m.var_oh, m.fixed_case,
         CASE WHEN a.fixed_held THEN f.spending END AS fixed_spending, CASE WHEN a.fixed_held THEN f.volume END AS fixed_volume,
         CASE WHEN NOT COALESCE(a.fixed_held, FALSE) THEN a.under_absorbed END AS not_absorbed,
         m.no_standard, m.at_planned + COALESCE(a.under_absorbed, 0) AS as_reported
  FROM pm m
  LEFT JOIN plan.standard_absorption a ON a.version_id = m.version_id AND a.plant_code = m.plant_code AND a.period = m.period
  LEFT JOIN fv f ON f.version_id = m.version_id AND f.plant_code = m.plant_code AND f.period = m.period
),
act AS (
  SELECT plant_code, period, ANY_VALUE(set_on) AS set_on, ANY_VALUE(cases) AS cases, BOOL_OR(has_standard) AS has_standard,
         SUM(absorbed) AS at_standard,
         SUM(CASE WHEN component = 'material' THEN variance END) AS material_whole,
         SUM(CASE WHEN component = 'labour' THEN variance END) AS labour_whole,
         SUM(CASE WHEN component = 'variable_overhead' THEN variance END) AS var_oh,
         SUM(spending) AS fixed_spending, SUM(volume) AS fixed_volume,
         SUM(CASE WHEN NOT has_standard THEN actual END) AS no_standard, SUM(actual) AS as_reported
  FROM plan.actual_cost_pool GROUP BY ALL
),
act_rows AS (
  SELECT x.version_id, a.plant_code, a.period, 'actual' AS basis, a.set_on, a.cases, a.at_standard, NULL::DOUBLE AS mat_price, NULL::DOUBLE AS mat_usage,
         a.material_whole, NULL::DOUBLE AS lab_rate, NULL::DOUBLE AS lab_eff, a.labour_whole, a.var_oh, NULL::DOUBLE AS fixed_case,
         a.fixed_spending, a.fixed_volume, NULL::DOUBLE AS not_absorbed, a.no_standard, a.as_reported
  FROM act a JOIN versions x ON a.period <= x.from_period
)
SELECT r.*, p.fiscal_year::INT AS fiscal_year,
       COALESCE(at_standard, 0) + COALESCE(mat_price, 0) + COALESCE(mat_usage, 0) + COALESCE(material_whole, 0) + COALESCE(lab_rate, 0)
         + COALESCE(lab_eff, 0) + COALESCE(labour_whole, 0) + COALESCE(var_oh, 0) + COALESCE(fixed_case, 0) + COALESCE(fixed_spending, 0)
         + COALESCE(fixed_volume, 0) + COALESCE(not_absorbed, 0) + COALESCE(no_standard, 0) AS lines_sum
FROM (SELECT * FROM plan_rows UNION ALL SELECT * FROM act_rows) r JOIN dims.dim_period p ON p.period = r.period
