/* The plan read by cause at the cycle's grain: cases, gross and net by version × layer × period. Net here is after the
   per-case and percentage deductions; event fixed fees are read from the long form. Finance's overlay is a line of its own
   (no layer, no cases): the plan valued is the sum of the layers, the plan with the overlay is that plus the overlay line.
   Reading, never stored by hand. */
MODEL (name plan.revenue_bridge, kind FULL, grain (version_id, line_kind, layer_no, period));
SELECT version_id, 'plan' AS line_kind, layer_no, layer_name, period, fiscal_year, SUM(cases) AS cases, SUM(tonnes) AS tonnes, SUM(gross_at_list) AS gross_at_list,
       SUM(standing_discount + temporary_price_reduction) AS on_invoice_deductions, SUM(gross_invoice) AS gross_invoice,
       SUM(retro_rebate + volume_rebate_accrual + warehouse_allowance + scan_funding + settlement_discount + returns_and_ullage + claims) AS off_invoice_deductions,
       SUM(net_sales) AS net_sales
FROM plan.demand_financialised
GROUP BY ALL
UNION ALL
SELECT version_id, 'overlay', NULL, 'Finance overlay', period, ANY_VALUE(fiscal_year), NULL, NULL, NULL, NULL, NULL, NULL, SUM(overlay)
FROM plan.finance_overlay
GROUP BY version_id, period
