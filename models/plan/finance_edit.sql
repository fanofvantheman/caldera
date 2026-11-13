/* Finance's figures as typed: one row per figure — a node of the customer structure at account or above × a node of the
   material structure × a period, volume or price, the value, and the demand plan at that node when it was typed. A save
   is the figures typed together under one reason; a later row naming a save releases it, and its figures return to the
   source. A figure stands when it is typed by a holder of Finance's verb on a known version, for a known reason, at nodes
   both structures have. Never in the demand stack: plan.finance_plan applies these over the demand plan valued. */
MODEL (name plan.finance_edit, kind FULL, grain (edit_id));
WITH rows_ AS (SELECT * FROM bronze.reg_finance_overlay),
entered AS (SELECT * FROM rows_ WHERE action = 'enter'),
released AS (SELECT withdraws AS save_id, ANY_VALUE(entered_by) AS released_by, ANY_VALUE(entered_on) AS released_on FROM rows_ WHERE action = 'release' GROUP BY 1),
holders AS (SELECT DISTINCT principal FROM dims.effective_entitlements WHERE action = 'overlay.finance.enter'),
cust AS (SELECT descendant_code AS code, ANY_VALUE(descendant_level) AS lvl FROM dims.dim_customer_hierarchy GROUP BY 1),
mat AS (SELECT descendant_code AS code, ANY_VALUE(descendant_level) AS lvl FROM dims.dim_material_hierarchy GROUP BY 1)
SELECT e.edit_id::TEXT AS edit_id, e.save_id::TEXT AS save_id, e.version_id::TEXT AS version_id,
       e.scope_customer::TEXT AS scope_customer, c.lvl AS customer_level, e.scope_material::TEXT AS scope_material, m.lvl AS material_level,
       e.period::TEXT AS period, p.fiscal_year, e.measure::TEXT AS measure, e.value::DOUBLE AS value, e.source_at_entry::DOUBLE AS source_at_entry,
       e.reason_code::TEXT AS reason_code, r.description AS reason, e.entered_by::TEXT AS entered_by, e.entered_on::TEXT AS entered_on,
       NULLIF(e.note::TEXT, '') AS note, c.lvl = 'account' AND m.lvl = 'material' AS at_grain, w.released_by, w.released_on,
       CASE WHEN w.save_id IS NOT NULL THEN 'released'
            WHEN h.principal IS NULL THEN 'refused: not typed by a holder of Finance''s verb'
            WHEN v.version_id IS NULL THEN 'refused: no such version'
            WHEN r.reason_code IS NULL THEN 'refused: a reason the vocabulary does not have'
            WHEN c.lvl IS NULL OR c.lvl = 'ship_to' THEN 'refused: the customer is not a node at account or above'
            WHEN m.lvl IS NULL THEN 'refused: the material is not a node of the material structure'
            WHEN p.period IS NULL THEN 'refused: no such period'
            WHEN e.measure NOT IN ('volume', 'price') THEN 'refused: a figure is a volume or a price'
            WHEN e.value IS NULL OR e.value::DOUBLE < 0 OR (e.measure = 'price' AND e.value::DOUBLE = 0) THEN 'refused: a volume of zero or more, a price above zero'
            ELSE 'in_force' END AS state
FROM entered e
LEFT JOIN released w ON w.save_id = e.save_id
LEFT JOIN holders h ON h.principal = e.entered_by
LEFT JOIN dims.ctl_version v ON v.version_id = e.version_id
LEFT JOIN plan.ref_overlay_reason r ON r.reason_code = e.reason_code
LEFT JOIN cust c ON c.code = e.scope_customer
LEFT JOIN mat m ON m.code = e.scope_material
LEFT JOIN dims.dim_period p ON p.period = e.period
