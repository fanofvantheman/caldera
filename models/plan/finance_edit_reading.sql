/* Each of Finance's figures read against the plan after the last run: what stands at its node now, what the demand plan
   is there now and what it was when the figure was typed. A figure holds unless a later figure of the same measure has
   overwritten it where their scopes meet; a figure whose source has moved since it was typed is marked — the value
   does not change. The price at a node is always revenue ÷ volume. */
MODEL (name plan.finance_edit_reading, kind FULL, grain (edit_id), audits (finance_figure_holds, finance_revenue_is_volume_times_price));
WITH e AS (SELECT * FROM plan.finance_edit),
node AS (
  SELECT e.edit_id, COUNT(*) AS n_cells, COUNT(f.source_cases) AS n_fed,
         SUM(f.cases) AS cases, SUM(f.net_sales) AS net_sales, SUM(f.source_cases) AS source_cases, SUM(f.source_net_sales) AS source_net_sales
  FROM e
  JOIN dims.dim_customer_hierarchy c ON c.ancestor_code = e.scope_customer AND c.descendant_level = 'account'
  JOIN dims.dim_material_hierarchy m ON m.ancestor_code = e.scope_material AND m.descendant_level = 'material'
  JOIN plan.finance_plan f ON f.version_id = e.version_id AND f.period = e.period AND f.account_code = c.descendant_code AND f.material_code = m.descendant_code
  WHERE e.state = 'in_force'
  GROUP BY 1
),
overwritten AS (
  SELECT a.edit_id, ARG_MIN(b.edit_id, b.entered_on || b.edit_id) AS overwritten_by
  FROM e a JOIN e b ON b.version_id = a.version_id AND b.period = a.period AND b.measure = a.measure AND a.state = 'in_force' AND b.state = 'in_force'
       AND (b.entered_on > a.entered_on OR (b.entered_on = a.entered_on AND b.edit_id > a.edit_id))
       AND EXISTS (SELECT 1 FROM dims.dim_customer_hierarchy h WHERE (h.ancestor_code = a.scope_customer AND h.descendant_code = b.scope_customer)
                                                               OR (h.ancestor_code = b.scope_customer AND h.descendant_code = a.scope_customer))
       AND EXISTS (SELECT 1 FROM dims.dim_material_hierarchy h WHERE (h.ancestor_code = a.scope_material AND h.descendant_code = b.scope_material)
                                                               OR (h.ancestor_code = b.scope_material AND h.descendant_code = a.scope_material))
  GROUP BY 1
),
r AS (
  SELECT e.*, n.n_cells, n.n_fed, n.cases, n.net_sales, n.source_cases, n.source_net_sales, o.overwritten_by,
         CASE e.measure WHEN 'volume' THEN n.cases ELSE n.net_sales / NULLIF(n.cases, 0) END AS now_at_node,
         CASE WHEN COALESCE(n.n_fed, 0) = 0 THEN NULL
              WHEN e.measure = 'volume' THEN n.source_cases ELSE n.source_net_sales / NULLIF(n.source_cases, 0) END AS source_now
  FROM e LEFT JOIN node n ON n.edit_id = e.edit_id LEFT JOIN overwritten o ON o.edit_id = e.edit_id
)
SELECT *,
       CASE WHEN state <> 'in_force' THEN state
            WHEN COALESCE(n_cells, 0) = 0 THEN 'unplaced: nothing at this node in this period'
            WHEN overwritten_by IS NOT NULL THEN 'overwritten'
            ELSE 'held' END AS standing,
       state = 'in_force' AND source_at_entry IS NOT NULL
         AND ABS(COALESCE(source_now, 0) - source_at_entry) > CASE measure WHEN 'volume' THEN 0.5 ELSE 0.005 END AS source_moved
FROM r
