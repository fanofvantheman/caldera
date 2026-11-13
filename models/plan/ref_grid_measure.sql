/* The measures of each grid a person types into, and the rules behind each — one row per grid × measure. Read by the one
   calculation the grid and the run share (calc/finance.py for the finance grid, calc/schedule.py for the opex schedule —
   each called from its model and from the face), and shown on
   the page "How each figure is calculated".

   Settings the calculation obeys — change the row and the grid behaves differently:
     rollup     how the figure reads at a total: 'sum' (of the figures beneath) or 'ratio' (rollup_num ÷ rollup_den, never stored);
                on the schedule also 'months' (the sum of one line's months) and 'line' (the line's own figure) — never across lines
     breakback  how a figure typed at a total spreads beneath it: 'source_shape' (by the source's figures beneath; the
                figure's own where nothing feeds it; evenly where all are zero), 'proportional' (every figure beneath moves
                by one factor so the total reads what was typed), or null — not typed
     verb       who may type it; null where it is not typed (on the schedule a figure is typed only at a line × month, or for a
                line — never spread from a total — so its spread is null and the verb alone says it is typed)
   Words only — written in the calculation, and checked against these words by tests/measure_register.py:
     set_says, formula_says (and every *_says column).
   field / source_field name the figure's column in plan.finance_plan; unit is the line's label on the grid; shown_as how its figures are written (count · rate · money). */
MODEL (name plan.ref_grid_measure, kind FULL, grain (grid, measure));
SELECT * FROM (VALUES
  ('finance', 'Revenue', 'plan.revenue', 1, 'volume', 'Volume', 'cases', 'count', 'cases', 'source_cases',
   'typed over a source', 'Typed by Finance, or the demand plan''s cases where the account × material is fed by it',
   NULL,
   'sum', NULL, NULL, 'the sum of the figures beneath it',
   'source_shape', 'split by the demand plan''s volumes beneath it (Finance''s own where built); evenly where they are all zero',
   'overlay.finance.enter', TRUE, NULL),
  ('finance', 'Revenue', 'plan.revenue', 2, 'price', 'Price', 'net / case', 'rate', 'price', 'source_price',
   'typed over a source', 'Typed by Finance, or the demand plan''s net sales ÷ its cases where it feeds',
   NULL,
   'ratio', 'revenue', 'volume', 'calculated: revenue ÷ volume — never stored above a single account × material',
   'proportional', 'every price beneath moves by the same proportion, so the total reads what was typed; a figure with no price takes the one typed',
   'overlay.finance.enter', TRUE, NULL),
  ('finance', 'Revenue', 'plan.revenue', 3, 'revenue', 'Revenue', 'net sales', 'money', 'net_sales', 'source_net_sales',
   'calculated', 'Calculated, never typed — the demand plan''s own net sales where nothing has been typed',
   'volume × price',
   'sum', NULL, NULL, 'the sum of the figures beneath it',
   NULL, 'not typed — type a volume or a price',
   NULL, TRUE, NULL),
  ('finance', 'Revenue', 'plan.revenue', 4, 'std_cost', 'Standard cost', 'cost / case', 'rate', 'std_cost', NULL,
   'from a source', 'From the cost of goods step''s declared source — read here, changed where the standard is kept, never typed on this grid',
   NULL,
   'ratio', 'cogs', 'volume', 'calculated: cost of goods ÷ volume',
   NULL, 'not typed here',
   NULL, FALSE, 'The standard cost per case is not built in Caldera yet — Where each number comes from shows the cost of goods step not yet filled.'),
  ('finance', 'Revenue', 'plan.revenue', 5, 'cogs', 'Cost of goods', 'cost of goods', 'money', 'cogs', NULL,
   'calculated', 'Calculated, never typed',
   'volume × standard cost',
   'sum', NULL, NULL, 'the sum of the figures beneath it',
   NULL, 'not typed',
   NULL, FALSE, 'Waits for the standard cost per case.'),
  ('finance', 'Revenue', 'plan.revenue', 6, 'margin', 'Margin', 'margin', 'money', 'margin', NULL,
   'calculated', 'Calculated, never typed',
   'revenue − cost of goods',
   'sum', NULL, NULL, 'the sum of the figures beneath it',
   NULL, 'not typed',
   NULL, FALSE, 'Waits for cost of goods.'),
  -- the opex schedule: entity × the plan's cost centre × account × period; a line is a driver and a rate (calc/schedule.py)
  ('schedule', 'Opex schedule', 'plan.schedule', 1, 'driver', 'Driver', 'driver quantity', 'count', 'driver_qty', NULL,
   'from a source', 'The plan quantity the line declares — cases made at a plant, cases shipped, net sales — or the same period''s actual a year earlier for last year, or one for a flat amount',
   NULL,
   'months', NULL, NULL, 'the sum of the line''s months; never added across lines',
   NULL, 'not typed — a driver is chosen for the line from the list',
   NULL, TRUE, NULL),
  ('schedule', 'Opex schedule', 'plan.schedule', 2, 'rate_calc', 'Calculated rate', 'per unit of driver', 'rate', 'rate_calc', NULL,
   'calculated', 'From the line''s own history; shown beneath the rate in use',
   'the line''s actuals ÷ the driver''s actuals over the last twelve closed periods',
   'line', NULL, NULL, 'the line''s own figure; never added across lines',
   NULL, 'not typed',
   NULL, TRUE, NULL),
  ('schedule', 'Opex schedule', 'plan.schedule', 3, 'rate', 'Rate', 'per unit of driver', 'rate', 'rate', 'rate_calc',
   'typed over a source', 'The calculated rate unless typed over, for the whole line; emptied, it is the calculated rate again; a changed driver returns it to calculated',
   NULL,
   'line', NULL, NULL, 'the line''s own figure; never added across lines',
   NULL, 'typed for a line, never at a total',
   'register.cost_input.maintain', TRUE, NULL),
  ('schedule', 'Opex schedule', 'plan.schedule', 4, 'amount_calc', 'Calculated amount', '$', 'money', 'amount_calc', NULL,
   'calculated', 'Every month, typed or not — shown beneath a typed month with the difference',
   'driver × rate',
   'sum', NULL, NULL, 'the sum of the figures beneath it',
   NULL, 'not typed',
   NULL, TRUE, NULL),
  ('schedule', 'Opex schedule', 'plan.schedule', 5, 'amount', 'Amount', '$', 'money', 'amount', 'amount_calc',
   'typed over a source', 'The calculated amount until a month is typed; a typed month holds through every recalculation until it is reset',
   'the calculated amount, or the month as typed',
   'sum', NULL, NULL, 'the sum of the figures beneath it',
   NULL, 'typed in a month of a line, never at a total',
   'schedule.line.enter', TRUE, NULL)
) AS t(grid, grid_label, grid_page, ord, measure, label, unit, shown_as, field, source_field,
       set_by, set_says, formula_says, rollup, rollup_num, rollup_den, rollup_says, breakback, breakback_says, verb, built, not_built_says)
