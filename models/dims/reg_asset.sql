/* The fixed-asset register as loaded from the ledgers: each asset's class, entity, the plan's cost centre it is charged to,
   the plant whose cases a units-of-production asset is worn by, cost and accumulated depreciation at the register's date.
   The plan does not re-key it; it walks it forward (calc/capex.py). */
MODEL (name dims.reg_asset, kind FULL, grain (asset_id));
SELECT asset_id::TEXT AS asset_id, asset_name::TEXT AS asset_name, asset_class::TEXT AS asset_class, entity_code::TEXT AS entity_code,
       cost_centre_code::TEXT AS cost_centre_code, NULLIF(plant_code::TEXT, '') AS plant_code, cost::DOUBLE AS cost, accumulated::DOUBLE AS accumulated,
       in_service_period::TEXT AS in_service_period, lifetime_units::DOUBLE AS lifetime_units, life_years::DOUBLE AS life_years,
       as_at_period::TEXT AS as_at_period
FROM bronze.reg_asset
