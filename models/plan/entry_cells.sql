/* Every entry resolved to the storage grid: the leaf materials under its material scope (a node of the hierarchy or a
   promo group), the ship-tos under its customer scope, the weeks inside its window — with the two weights a spread can
   use that do not depend on the version's own baseline: the history shape of the cell-week, and the catchment (stores
   served by the ship-to, flat across weeks). */
MODEL (name plan.entry_cells, kind FULL, grain (entry_id, material_code, ship_to_code, week_id));
WITH mats AS (
  SELECT ancestor_code AS scope_material, descendant_code AS material_code FROM dims.dim_material_hierarchy WHERE descendant_is_leaf
  UNION SELECT promo_group_code, material_code FROM dims.ref_promo_group
),
custs AS (SELECT ancestor_code AS scope_customer, descendant_code AS ship_to_code FROM dims.dim_customer_hierarchy WHERE descendant_is_leaf)
SELECT e.entry_id, e.version_id, e.layer_no, e.value_kind, e.value, e.spread_rule, e.effect_type, e.reason_code,
       m.material_code, c.ship_to_code, st.account_code, w.week_id, w.period, w.fiscal_week,
       COALESCE(hs.shape_cases, 0) AS w_history_shape,
       GREATEST(st.stores_served, 1)::DOUBLE AS w_catchment
FROM plan.layer_entry e
JOIN mats m ON m.scope_material = e.scope_material
JOIN custs c ON c.scope_customer = e.scope_customer
JOIN dims.dim_ship_to st ON st.ship_to_code = c.ship_to_code
JOIN dims.dim_week w ON w.period BETWEEN e.period_from AND e.period_to
LEFT JOIN plan.history_shape hs ON hs.material_code = m.material_code AND hs.ship_to_code = c.ship_to_code AND hs.fiscal_week = LEAST(w.fiscal_week, 52)
WHERE e.version_known AND e.material_scope_resolves AND e.customer_scope_resolves AND e.entered_by_owner AND e.window_ordered
  AND NOT (e.withdrawn AND e.withdrawn_by_owner)        -- a withdrawal by someone without the verb does not take the entry out
