/* The gap: each version read against the reference version it names, at standard material × account × period — cases and
   net sales, plan less reference, only where both have a period. The business plan does not move; this is how it is read. */
MODEL (name plan.gap_to_reference, kind FULL, grain (version_id, standard_material, account_code, period));
WITH f AS (
  SELECT version_id, standard_material, account_code, period, SUM(cases) AS cases, SUM(net_sales) AS net_sales
  FROM plan.demand_financialised GROUP BY ALL
), vr AS (
  SELECT version_id, reference_version, horizon_start, horizon_end FROM dims.ctl_version WHERE reference_version IS NOT NULL
), k AS (
  SELECT vr.version_id, vr.reference_version, vr.horizon_start, vr.horizon_end, f.standard_material, f.account_code, f.period
  FROM vr JOIN f ON f.version_id = vr.version_id
  UNION
  SELECT vr.version_id, vr.reference_version, vr.horizon_start, vr.horizon_end, f.standard_material, f.account_code, f.period
  FROM vr JOIN f ON f.version_id = vr.reference_version
)
SELECT k.version_id, k.reference_version, k.standard_material, k.account_code, k.period,
       COALESCE(p.cases, 0) AS plan_cases, COALESCE(r.cases, 0) AS reference_cases, COALESCE(p.cases, 0) - COALESCE(r.cases, 0) AS cases_gap,
       COALESCE(p.net_sales, 0) AS plan_net_sales, COALESCE(r.net_sales, 0) AS reference_net_sales, COALESCE(p.net_sales, 0) - COALESCE(r.net_sales, 0) AS net_sales_gap
FROM k
LEFT JOIN f p ON p.version_id = k.version_id AND p.standard_material = k.standard_material AND p.account_code = k.account_code AND p.period = k.period
LEFT JOIN f r ON r.version_id = k.reference_version AND r.standard_material = k.standard_material AND r.account_code = k.account_code AND r.period = k.period
WHERE k.period BETWEEN k.horizon_start AND k.horizon_end
  AND k.period BETWEEN (SELECT horizon_start FROM dims.ctl_version WHERE version_id = k.reference_version)
                   AND (SELECT horizon_end FROM dims.ctl_version WHERE version_id = k.reference_version)
