/* Finance's overlay at its grain — account × material × period — each entry in force spread over its scope by the plan's
   own net sales there. The plan valued and the plan valued with the overlay are always read together. */
MODEL (name plan.finance_overlay, kind FULL, grain (version_id, overlay_id, account_code, material_code, period), audits (finance_overlay_spread_ties));
WITH e AS (SELECT * FROM plan.finance_overlay_entry WHERE state = 'in_force'),
cells AS (
  SELECT e.version_id, e.overlay_id, e.kind, e.reason_code, f.account_code, f.material_code, f.period, ANY_VALUE(f.fiscal_year) AS fiscal_year,
         SUM(f.net_sales) AS net_sales, ANY_VALUE(e.amount) AS amount, ANY_VALUE(e.scope_net_sales) AS scope_net_sales
  FROM e
  JOIN dims.dim_customer_hierarchy c ON c.ancestor_code = e.scope_customer
  JOIN dims.dim_material_hierarchy m ON m.ancestor_code = e.scope_material
  JOIN plan.demand_financialised f ON f.version_id = e.version_id AND f.account_code = c.descendant_code AND f.material_code = m.descendant_code
       AND f.period BETWEEN e.period_from AND e.period_to
  GROUP BY e.version_id, e.overlay_id, e.kind, e.reason_code, f.account_code, f.material_code, f.period
)
SELECT version_id, overlay_id, kind, reason_code, account_code, material_code, period, fiscal_year, net_sales AS plan_net_sales,
       amount * net_sales / scope_net_sales AS overlay
FROM cells WHERE net_sales <> 0
