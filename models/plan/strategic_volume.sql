/* The strategic plan's volume and net revenue: category × channel × fiscal year over the plan's horizon. A year the latest
   view covers whole (its closed periods as shipped, the rest the latest view) is the latest view rolled up — the strategic
   plan does not re-enter it; a year beyond is the last such year grown by the plan's rate for the category, year on year,
   with the channel mix and the net price per case held (DEC-20261113-01; strategic_plan.md §Grain and horizon). */
MODEL (name plan.strategic_volume, kind FULL, grain (plan_id, category_code, channel, fiscal_year));
WITH sp AS (SELECT plan_id, latest_view, first_year, last_year FROM plan.strategic_plan),
mat AS (SELECT material_code, category_code, category_name FROM dims.dim_material),
acc AS (SELECT account_code, channel FROM dims.dim_account),
closed AS (SELECT period, fiscal_year FROM dims.dim_period WHERE period_state = 'CLOSED'),
lv AS (
  SELECT d.fiscal_year, d.period, m.category_code, a.channel, SUM(d.cases) AS cases, SUM(d.net_sales) AS net_sales
  FROM plan.demand_financialised d JOIN sp ON d.version_id = sp.latest_view
  JOIN mat m ON m.material_code = d.material_code JOIN acc a ON a.account_code = d.account_code GROUP BY ALL
),
shipped AS (
  SELECT s.fiscal_year, s.period, m.category_code, a.channel, SUM(s.cases) AS cases, SUM(s.net_sales) AS net_sales
  FROM history.shipments s JOIN closed c ON c.period = s.period JOIN mat m ON m.material_code = s.material_code JOIN acc a ON a.account_code = s.account_code
  WHERE s.fiscal_year >= (SELECT first_year FROM sp) GROUP BY ALL
),
covered AS (                          -- a year is inside when its closed periods and the latest view's together make all of it
  SELECT p.fiscal_year, COUNT(*) AS periods,
         COUNT(*) FILTER (WHERE p.period_state = 'CLOSED' OR p.period IN (SELECT DISTINCT period FROM lv)) AS read
  FROM dims.dim_period p GROUP BY 1
),
inside AS (
  SELECT x.fiscal_year, x.category_code, x.channel, SUM(x.cases) AS cases, SUM(x.net_sales) AS net_sales,
         BOOL_OR(x.shipped) AS with_actuals
  FROM (SELECT *, TRUE AS shipped FROM shipped UNION ALL SELECT *, FALSE FROM lv) x
  JOIN covered c ON c.fiscal_year = x.fiscal_year AND c.read = c.periods
  WHERE x.fiscal_year BETWEEN (SELECT first_year FROM sp) AND (SELECT last_year FROM sp) GROUP BY ALL
),
last_inside AS (SELECT MAX(fiscal_year) AS fy FROM inside),
growth AS (
  SELECT g.category_code, g.fiscal_year, g.growth_pct FROM plan.strategic_growth g JOIN sp ON g.plan_id = sp.plan_id
),
years AS (SELECT range AS fiscal_year FROM range((SELECT fy FROM last_inside) + 1, (SELECT last_year FROM sp) + 1)),
factor AS (                           -- the growth compounded from the last inside year to each year beyond
  SELECT c.category_code, y.fiscal_year,
         EXP(SUM(LN(1 + COALESCE(g.growth_pct, 0))) OVER (PARTITION BY c.category_code ORDER BY y.fiscal_year)) AS factor,
         g.growth_pct
  FROM (SELECT DISTINCT category_code FROM inside) c CROSS JOIN years y
  LEFT JOIN growth g ON g.category_code = c.category_code AND g.fiscal_year = y.fiscal_year
)
SELECT sp.plan_id, i.category_code, i.channel, i.fiscal_year, i.cases, i.net_sales,
       CASE WHEN i.with_actuals THEN 'shipped and the latest view' ELSE 'the latest view' END AS source, NULL::DOUBLE AS growth_pct
FROM inside i CROSS JOIN sp
UNION ALL
SELECT sp.plan_id, b.category_code, b.channel, f.fiscal_year, b.cases * f.factor, b.net_sales * f.factor,
       'grown from FY' || (SELECT fy FROM last_inside) AS source, f.growth_pct
FROM inside b JOIN factor f ON f.category_code = b.category_code CROSS JOIN sp
WHERE b.fiscal_year = (SELECT fy FROM last_inside)
