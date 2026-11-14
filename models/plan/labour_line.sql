/* The labour model, line by line, on each open version for every period it calculates after its last actual one.
   By role: a position's FTE × paid hours a week × the period's weeks × its classification's rate in force (× 1 + the
   agreement's casual loading for the casual pool, an entitlement of the agreement) — a change of person moves nothing. By name: a person's salary × (1 + incentive at
   target) ÷ 52 × the weeks of the period they are employed in. On-costs on both at the entity's rates. The output every
   reader takes is plan.labour_cost; this table carries individual pay. */
MODEL (name plan.labour_line, kind FULL, grain (version_id, model, line_id, period));
WITH v AS (SELECT version_id, horizon_start, horizon_end, from_period FROM dims.ctl_version WHERE status = 'open'),
per AS (SELECT v.version_id, p.period, p.fiscal_year, p.period_start, p.period_end, p.weeks_in_period
        FROM v JOIN dims.dim_period p ON p.period BETWEEN v.horizon_start AND v.horizon_end WHERE p.period > v.from_period),
oc AS (SELECT entity_code, SUM(rate) AS on_cost FROM dims.ref_on_cost GROUP BY ALL),
cl AS (SELECT instrument AS agreement, MAX(value) AS loading FROM dims.reg_entitlement
       WHERE layer = 'agreement' AND kind = 'loading' AND applies_to = 'casual' GROUP BY 1),
role AS (
  SELECT per.version_id, 'role' AS model, r.position_id AS line_id, per.period, per.fiscal_year, r.entity_code, r.cost_centre_code,
         a.classification_name AS what, r.employment_type, r.shown_name AS shown, r.fte,
         r.fte * r.hours_per_week * per.weeks_in_period * a.hourly_rate * (1 + CASE WHEN r.employment_type = 'casual' THEN COALESCE(cl.loading, 0) ELSE 0 END) AS wages,
         a.hourly_rate AS rate
  FROM dims.reg_position r JOIN per ON per.period >= r.from_period AND (r.to_period IS NULL OR per.period <= r.to_period)
  JOIN dims.reg_agreement a ON a.agreement = r.agreement AND a.classification = r.classification
   AND a.valid_from_period = (SELECT MAX(x.valid_from_period) FROM dims.reg_agreement x WHERE x.agreement = r.agreement AND x.classification = r.classification AND x.valid_from_period <= per.period)
  LEFT JOIN cl ON cl.agreement = r.agreement
),
named AS (
  SELECT per.version_id, 'name' AS model, p.person_id AS line_id, per.period, per.fiscal_year, p.entity_code, p.cost_centre_code,
         p.title AS what, CASE WHEN p.vacancy THEN 'vacancy' ELSE 'person' END AS employment_type, p.person_name AS shown,
         GREATEST(0, DATE_DIFF('day', GREATEST(per.period_start, p.start_date), LEAST(per.period_end, COALESCE(p.end_date, per.period_end))) + 1) / (per.weeks_in_period * 7.0) AS fte,
         p.annual_salary * (1 + p.incentive_pct) / 52.0
           * GREATEST(0, DATE_DIFF('day', GREATEST(per.period_start, p.start_date), LEAST(per.period_end, COALESCE(p.end_date, per.period_end))) + 1) / 7.0 AS wages,
         p.annual_salary AS rate
  FROM dims.reg_person p JOIN per ON p.start_date <= per.period_end AND (p.end_date IS NULL OR p.end_date >= per.period_start)
)
SELECT x.*, x.wages * oc.on_cost AS on_costs, c.labour_model = x.model AS model_declared
FROM (SELECT * FROM role UNION ALL SELECT * FROM named) x
LEFT JOIN oc ON oc.entity_code = x.entity_code
LEFT JOIN dims.dim_cost_centre c ON c.cost_centre_code = x.cost_centre_code
