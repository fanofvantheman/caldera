/* The drivers a schedule line may declare: a plan quantity, none (a flat amount per period) or last year (the same
   period's actual a year earlier, × an index). Amount = driver × rate. */
MODEL (name dims.ref_cost_driver, kind FULL, grain (driver));
SELECT driver::TEXT AS driver, driver_label::TEXT AS driver_label, unit::TEXT AS unit, says::TEXT AS says, ord::INT AS ord
FROM bronze.ref_cost_driver
