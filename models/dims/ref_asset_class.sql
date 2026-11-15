/* The asset classes of the capital plan: each one's depreciation method — straight-line, or units of production (the
   cases made at the asset's plant over its lifetime cases) — its useful life in years and its residual share. Declared per
   class; the plan does not invent a method (DEC-20261115-01 point 4). */
MODEL (name dims.ref_asset_class, kind FULL, grain (asset_class));
SELECT asset_class::TEXT AS asset_class, class_name::TEXT AS class_name, method::TEXT AS method, life_years::DOUBLE AS life_years,
       residual_pct::DOUBLE AS residual_pct, ord::INT AS ord
FROM bronze.ref_asset_class
