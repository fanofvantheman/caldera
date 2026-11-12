/* Finance's overlay as entered: one row per entry, with its state. An entry is Finance's own risk or opportunity on a
   version, in net-sales dollars, at a node of the customer structure × a node of the material structure × a span of
   periods. It stands when it is entered by a holder of the overlay verb, on a known version, for a reason the vocabulary
   has, and the plan has net sales in its scope to spread it by; a later row naming it withdraws it. Never cases, never
   in the demand stack: the overlay is money on the plan valued, read beside it. */
MODEL (name plan.finance_overlay_entry, kind FULL, grain (overlay_id));
WITH rows_ AS (SELECT * FROM bronze.reg_finance_overlay),
entered AS (SELECT * FROM rows_ WHERE action = 'enter'),
withdrawn AS (SELECT withdraws AS overlay_id, ANY_VALUE(entered_by) AS withdrawn_by, ANY_VALUE(entered_on) AS withdrawn_on FROM rows_ WHERE action = 'withdraw' GROUP BY 1),
holders AS (SELECT DISTINCT principal FROM dims.effective_entitlements WHERE action = 'overlay.finance.enter'),
base AS (
  SELECT e.overlay_id, SUM(f.net_sales) AS scope_net_sales
  FROM entered e
  JOIN dims.dim_customer_hierarchy c ON c.ancestor_code = e.scope_customer
  JOIN dims.dim_material_hierarchy m ON m.ancestor_code = e.scope_material
  JOIN plan.demand_financialised f ON f.version_id = e.version_id AND f.account_code = c.descendant_code AND f.material_code = m.descendant_code
       AND f.period BETWEEN e.period_from AND e.period_to
  GROUP BY 1
)
SELECT e.overlay_id::TEXT AS overlay_id, e.version_id::TEXT AS version_id, e.kind::TEXT AS kind, e.reason_code::TEXT AS reason_code, r.description AS reason,
       e.scope_customer::TEXT AS scope_customer, e.scope_material::TEXT AS scope_material, e.period_from::TEXT AS period_from, e.period_to::TEXT AS period_to,
       e.amount::DOUBLE AS amount, e.entered_by::TEXT AS entered_by, e.entered_on::TEXT AS entered_on, NULLIF(e.note::TEXT, '') AS note,
       b.scope_net_sales, w.withdrawn_by, w.withdrawn_on,
       CASE WHEN w.overlay_id IS NOT NULL THEN 'withdrawn'
            WHEN h.principal IS NULL THEN 'refused: not entered by a holder of the overlay'
            WHEN v.version_id IS NULL THEN 'refused: no such version'
            WHEN r.reason_code IS NULL THEN 'refused: a reason the vocabulary does not have'
            WHEN e.kind NOT IN ('risk', 'opportunity') OR (e.kind = 'risk') <> (e.amount::DOUBLE < 0) THEN 'refused: a risk is negative, an opportunity positive'
            WHEN COALESCE(b.scope_net_sales, 0) = 0 THEN 'unplaced: the plan has no net sales in its scope'
            ELSE 'in_force' END AS state
FROM entered e
LEFT JOIN withdrawn w ON w.overlay_id = e.overlay_id
LEFT JOIN holders h ON h.principal = e.entered_by
LEFT JOIN dims.ctl_version v ON v.version_id = e.version_id
LEFT JOIN plan.ref_overlay_reason r ON r.reason_code = e.reason_code
LEFT JOIN base b ON b.overlay_id = e.overlay_id
