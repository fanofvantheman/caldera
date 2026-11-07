/* Every stack line valued: cases × the list in force on the account's price list (export converted at the version's FX
   assumption), then the gross-to-net — standing discount and the event's price reduction on invoice; retro and volume
   rebates (at the accrual rate), warehouse allowance, scan funding and settlement discount off invoice; returns and claims
   as history rates. Each layer sells at the same list and terms, so the bridge by layer is a bridge by cause; the event's
   reduction and funding fall on every case in the window and are read under promotion. Lump sums are not here: they
   have no quantity and sit in the long form. */
MODEL (name plan.demand_financialised, kind FULL, grain (version_id, layer_no, line_source, effect_type, material_code, ship_to_code, week_id),
       audits (every_cell_priced, gross_to_net_identity));
WITH fx AS (
  SELECT version_id, MAX(CASE WHEN assumption_code = 'FX_AUDUSD' THEN value END) AS aud_usd,
         MAX(CASE WHEN assumption_code = 'RETURNS_RATE' THEN value END) AS returns_rate,
         MAX(CASE WHEN assumption_code = 'CLAIMS_RATE' THEN value END) AS claims_rate
  FROM dims.reg_assumption WHERE period = 'ALL' GROUP BY version_id
),
terms AS (
  SELECT t.account_code, w.week_id,
         SUM(CASE WHEN instrument_kind = 'standing_discount' THEN rate ELSE 0 END) AS standing_discount_rate,
         SUM(CASE WHEN instrument_kind = 'retro_rebate' THEN rate ELSE 0 END) AS retro_rebate_rate,
         SUM(CASE WHEN instrument_kind = 'volume_rebate' THEN rate ELSE 0 END) AS volume_rebate_accrual_rate,
         SUM(CASE WHEN instrument_kind = 'warehouse_allowance' THEN rate ELSE 0 END) AS warehouse_allowance_rate,
         SUM(CASE WHEN instrument_kind = 'settlement_discount' THEN rate ELSE 0 END) AS settlement_discount_rate
  FROM plan.terms t JOIN dims.dim_week w ON t.valid_from <= w.week_start AND (t.valid_to IS NULL OR t.valid_to >= w.week_start)
  WHERE t.account_known GROUP BY ALL
),
promo AS (
  SELECT version_id, material_code, account_code, week_id, SUM(tpr_per_case * in_window) AS tpr_per_case, SUM(scan_funding_per_case * in_window) AS scan_per_case,
         STRING_AGG(event_id, ',' ORDER BY event_id) AS event_ids
  FROM plan.promo_rate_in_window GROUP BY ALL
),
valued AS (
  SELECT s.*, a.price_list, p.currency, p.price_event,
         CASE p.currency WHEN 'USD' THEN p.price_per_case / NULLIF(f.aud_usd, 0) ELSE p.price_per_case END AS list_price,
         COALESCE(t.standing_discount_rate, 0) AS standing_discount_rate, COALESCE(t.retro_rebate_rate, 0) AS retro_rebate_rate,
         COALESCE(t.volume_rebate_accrual_rate, 0) AS volume_rebate_accrual_rate, COALESCE(t.warehouse_allowance_rate, 0) AS warehouse_allowance_rate,
         COALESCE(t.settlement_discount_rate, 0) AS settlement_discount_rate,
         COALESCE(pr.tpr_per_case, 0) AS tpr_per_case, COALESCE(pr.scan_per_case, 0) * a.supplies_scan_data::INT AS scan_per_case, pr.event_ids,
         COALESCE(f.returns_rate, 0) AS returns_rate, COALESCE(f.claims_rate, 0) AS claims_rate
  FROM plan.demand_stack s
  JOIN dims.dim_account a ON a.account_code = s.account_code
  LEFT JOIN fx f ON f.version_id = s.version_id
  LEFT JOIN plan.price_in_force p ON p.price_list = a.price_list AND p.material_code = s.material_code AND p.week_id = s.week_id
  LEFT JOIN terms t ON t.account_code = s.account_code AND t.week_id = s.week_id
  LEFT JOIN promo pr ON pr.version_id = s.version_id AND pr.material_code = s.material_code AND pr.account_code = s.account_code AND pr.week_id = s.week_id
),
money AS (
  SELECT *, list_price IS NOT NULL AS priced,
         cases * list_price AS gross_at_list,
         cases * list_price * standing_discount_rate AS standing_discount,
         cases * tpr_per_case AS temporary_price_reduction
  FROM valued
),
invoice AS (
  SELECT *, gross_at_list - standing_discount - temporary_price_reduction AS gross_invoice FROM money
)
SELECT version_id, layer_no, layer_name, owner_role, line_source, effect_type, reason_code, material_code, standard_material, ship_to_code, account_code,
       week_id, period, fiscal_year, cases, tonnes, price_list, currency, list_price, price_event, event_ids, priced,
       gross_at_list, standing_discount, temporary_price_reduction, gross_invoice,
       gross_invoice * retro_rebate_rate AS retro_rebate,
       gross_invoice * volume_rebate_accrual_rate AS volume_rebate_accrual,
       gross_invoice * warehouse_allowance_rate AS warehouse_allowance,
       cases * scan_per_case AS scan_funding,
       gross_invoice * settlement_discount_rate AS settlement_discount,
       gross_invoice * returns_rate AS returns_and_ullage,
       gross_invoice * claims_rate AS claims,
       gross_invoice * (1 - retro_rebate_rate - volume_rebate_accrual_rate - warehouse_allowance_rate - settlement_discount_rate - returns_rate - claims_rate)
         - cases * scan_per_case AS net_sales
FROM invoice
