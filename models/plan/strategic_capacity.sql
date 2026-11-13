/* The strategic plan's capacities, by kind × plant or network × fiscal year: what is available at each tier and the load
   the volume path puts on it (DEC-20261113-01; capacities.md). Only what Caldera can compute is here:
     production   line hours by plant. Available: the machine register's effective hours (shifts × days × hours, less
                  planned downtime, × efficiency) at the tier registered (tier 0) and with one more shift on every line
                  that has fewer than three (tier 1, derived from the register — no step cost or lead time is declared);
                  a year past the register holds its last year. Load: inside the latest view, cases ÷ the primary route's
                  rate, material by material (closed periods as shipped — no production history, so shipments stand in);
                  beyond, the category's cases × its hours per case at the plant in the last inside year — a factor, not a route.
     working capital  receivables at the accounts' payment terms — net sales × days ÷ 365 — as load only: no limit is
                  declared, and inventory and payables are not planned, so there is no availability to read it against.
   Storage, material and logistics have no data behind a capacity and are declared, not computed (plan.ref_strategic_capacity). */
MODEL (name plan.strategic_capacity, kind FULL, grain (plan_id, kind, node, fiscal_year));
WITH sp AS (SELECT plan_id, latest_view, first_year, last_year FROM plan.strategic_plan),
years AS (SELECT range AS fiscal_year FROM range((SELECT first_year FROM sp), (SELECT last_year FROM sp) + 1)),
reg AS (
  SELECT l.plant_code, p.fiscal_year, SUM(c.effective_hours) AS tier0, SUM(c.effective_hours * LEAST(c.shifts + 1, 3) / c.shifts) AS tier1,
         STRING_AGG(DISTINCT c.tier, ', ' ORDER BY c.tier) AS tiers
  FROM dims.reg_capacity_machine c JOIN dims.dim_line l ON l.line_code = c.line_code JOIN dims.dim_period p ON p.period = c.period
  WHERE c.line_exists GROUP BY ALL
),
avail AS (                            -- each year of the plan; past the register, its last year held
  SELECT pl.plant_code, y.fiscal_year,
         (SELECT r.tier0 FROM reg r WHERE r.plant_code = pl.plant_code AND r.fiscal_year <= y.fiscal_year ORDER BY r.fiscal_year DESC LIMIT 1) AS tier0,
         (SELECT r.tier1 FROM reg r WHERE r.plant_code = pl.plant_code AND r.fiscal_year <= y.fiscal_year ORDER BY r.fiscal_year DESC LIMIT 1) AS tier1,
         (SELECT r.tiers FROM reg r WHERE r.plant_code = pl.plant_code AND r.fiscal_year <= y.fiscal_year ORDER BY r.fiscal_year DESC LIMIT 1) AS tiers,
         y.fiscal_year > (SELECT MAX(fiscal_year) FROM reg) AS held
  FROM (SELECT DISTINCT plant_code FROM reg) pl CROSS JOIN years y
),
route AS (SELECT material_code, plant_code, rate_cases_per_hour FROM dims.ref_route WHERE is_primary AND rate_cases_per_hour > 0),
mat AS (SELECT material_code, category_code FROM dims.dim_material),
inside_years AS (SELECT DISTINCT fiscal_year FROM plan.strategic_volume WHERE source NOT LIKE 'grown%'),
cases AS (                            -- material × year: closed periods as shipped, the rest the latest view
  SELECT s.material_code, s.fiscal_year, SUM(s.cases) AS cases FROM history.shipments s
  JOIN dims.dim_period p ON p.period = s.period AND p.period_state = 'CLOSED' WHERE s.fiscal_year IN (SELECT fiscal_year FROM inside_years) GROUP BY ALL
  UNION ALL
  SELECT d.material_code, d.fiscal_year, SUM(d.cases) FROM plan.demand_financialised d JOIN sp ON d.version_id = sp.latest_view
  WHERE d.fiscal_year IN (SELECT fiscal_year FROM inside_years) GROUP BY ALL
),
hours_inside AS (
  SELECT r.plant_code, c.fiscal_year, m.category_code, SUM(c.cases / r.rate_cases_per_hour) AS hours, SUM(c.cases) AS cases
  FROM cases c JOIN route r ON r.material_code = c.material_code JOIN mat m ON m.material_code = c.material_code GROUP BY ALL
),
last_inside AS (SELECT MAX(fiscal_year) AS fy FROM inside_years),
cat_cases AS (SELECT category_code, fiscal_year, SUM(cases) AS cases FROM plan.strategic_volume GROUP BY ALL),
per_case AS (                         -- hours per case of the category at the plant, in the last inside year
  SELECT h.plant_code, h.category_code, h.hours / NULLIF(cc.cases, 0) AS hours_per_case
  FROM hours_inside h JOIN cat_cases cc ON cc.category_code = h.category_code AND cc.fiscal_year = h.fiscal_year
  WHERE h.fiscal_year = (SELECT fy FROM last_inside)
),
load AS (
  SELECT plant_code, fiscal_year, SUM(hours) AS load, 'cases ÷ the route''s rate' AS load_from FROM hours_inside GROUP BY 1, 2
  UNION ALL
  SELECT pc.plant_code, cc.fiscal_year, SUM(cc.cases * pc.hours_per_case), 'cases × hours per case in FY' || (SELECT fy FROM last_inside)
  FROM cat_cases cc JOIN per_case pc ON pc.category_code = cc.category_code
  WHERE cc.fiscal_year > (SELECT fy FROM last_inside) GROUP BY 1, 2
),
terms AS (                            -- receivables at terms: net sales × days ÷ 365, account by account inside; the ratio held beyond
  SELECT x.fiscal_year, SUM(x.net_sales * a.payment_terms_days / 365.0) AS receivables, SUM(x.net_sales) AS net_sales
  FROM (SELECT s.account_code, s.fiscal_year, s.net_sales FROM history.shipments s JOIN dims.dim_period p ON p.period = s.period AND p.period_state = 'CLOSED'
        WHERE s.fiscal_year IN (SELECT fiscal_year FROM inside_years)
        UNION ALL SELECT d.account_code, d.fiscal_year, d.net_sales FROM plan.demand_financialised d JOIN sp ON d.version_id = sp.latest_view
        WHERE d.fiscal_year IN (SELECT fiscal_year FROM inside_years)) x
  JOIN dims.dim_account a ON a.account_code = x.account_code GROUP BY 1
)
SELECT sp.plan_id, 'production' AS kind, a.plant_code AS node, a.fiscal_year, 'line hours' AS unit,
       a.tier0 AS available_tier0, a.tier1 AS available_tier1, a.tiers AS tier0_is, a.held AS availability_held,
       l.load, l.load_from
FROM avail a CROSS JOIN sp LEFT JOIN load l ON l.plant_code = a.plant_code AND l.fiscal_year = a.fiscal_year
UNION ALL
SELECT sp.plan_id, 'working_capital', 'Caldera', y.fiscal_year, 'dollars of receivables', NULL, NULL, NULL, NULL,
       COALESCE(t.receivables, (SELECT t2.receivables / t2.net_sales FROM terms t2 WHERE t2.fiscal_year = (SELECT fy FROM last_inside))
                               * (SELECT SUM(v.net_sales) FROM plan.strategic_volume v WHERE v.fiscal_year = y.fiscal_year)),
       CASE WHEN t.receivables IS NOT NULL THEN 'net sales × each account''s terms' ELSE 'net sales × the FY' || (SELECT fy FROM last_inside) || ' ratio' END
FROM years y CROSS JOIN sp LEFT JOIN terms t ON t.fiscal_year = y.fiscal_year
