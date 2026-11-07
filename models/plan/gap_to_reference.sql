/* The gap: each version read against the reference version it names, at standard material × account × period — cases and
   net sales, plan less reference, only where both have a period. The business plan does not move; this is how it is read. */
MODEL (name plan.gap_to_reference, kind FULL, grain (version_id, standard_material, account_code, period));
WITH f AS (
  SELECT version_id, standard_material, account_code, period, SUM(cases) AS cases, SUM(net_sales) AS net_sales
  FROM plan.demand_financialised GROUP BY ALL
)
SELECT v.version_id, v.reference_version, COALESCE(p.standard_material, r.standard_material) AS standard_material,
       COALESCE(p.account_code, r.account_code) AS account_code, COALESCE(p.period, r.period) AS period,
       COALESCE(p.cases, 0) AS plan_cases, COALESCE(r.cases, 0) AS reference_cases, COALESCE(p.cases, 0) - COALESCE(r.cases, 0) AS cases_gap,
       COALESCE(p.net_sales, 0) AS plan_net_sales, COALESCE(r.net_sales, 0) AS reference_net_sales, COALESCE(p.net_sales, 0) - COALESCE(r.net_sales, 0) AS net_sales_gap
FROM dims.ctl_version v
JOIN f p ON p.version_id = v.version_id
FULL OUTER JOIN f r ON r.version_id = v.reference_version AND r.standard_material = p.standard_material AND r.account_code = p.account_code AND r.period = p.period
WHERE v.reference_version IS NOT NULL
  AND COALESCE(p.period, r.period) BETWEEN v.horizon_start AND v.horizon_end
  AND COALESCE(p.period, r.period) BETWEEN (SELECT horizon_start FROM dims.ctl_version WHERE version_id = v.reference_version)
                                       AND (SELECT horizon_end FROM dims.ctl_version WHERE version_id = v.reference_version)
