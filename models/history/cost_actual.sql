/* The ledgers' actuals as they arrive: entity × the ledger's own cost centre × account × period. Read at the plan's cost
   centre through the mapping by plan.cost_actual. */
MODEL (name history.cost_actual, kind FULL, grain (entity_code, ledger_cost_centre, account_code, period));
SELECT entity_code::TEXT AS entity_code, ledger_cost_centre::TEXT AS ledger_cost_centre, account_code::TEXT AS account_code,
       period::TEXT AS period, SUM(amount)::DOUBLE AS amount
FROM bronze.cost_actual GROUP BY ALL
