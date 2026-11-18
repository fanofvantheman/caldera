/* Each material's class on each plan (DEC-20261117-02 point 2): ranked by its cases over the plan's periods, A while the
   running share is within 80%, B within 95%, C after — and the class's declared fill rate (dims.ref_service_level). An
   ABC on volume only: the XYZ half (variability) is not taken, and the page says so. */
MODEL (name plan.service_class, kind FULL, grain (version_id, material_code));
WITH v AS (SELECT version_id, from_period, plan_through FROM dims.ctl_version WHERE version_kind <> 'actual' AND from_period IS NOT NULL),
c AS (
  SELECT d.version_id, d.material_code, SUM(d.cases) AS cases FROM plan.unconstrained_demand d
  JOIN v ON v.version_id = d.version_id AND d.period > v.from_period AND d.period <= v.plan_through GROUP BY ALL
),
r AS (
  SELECT *, SUM(cases) OVER (PARTITION BY version_id ORDER BY cases DESC, material_code ROWS UNBOUNDED PRECEDING) / NULLIF(SUM(cases) OVER (PARTITION BY version_id), 0) AS running
  FROM c
)
SELECT r.version_id, r.material_code, r.cases, r.running,
       (SELECT s.service_class FROM dims.ref_service_level s WHERE r.running <= s.cumulative_to + 1e-12 ORDER BY s.cumulative_to LIMIT 1) AS service_class,
       (SELECT s.fill_rate FROM dims.ref_service_level s WHERE r.running <= s.cumulative_to + 1e-12 ORDER BY s.cumulative_to LIMIT 1) AS fill_rate
FROM r
