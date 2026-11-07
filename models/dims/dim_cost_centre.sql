/* Cost centres and the organisation above them. */
MODEL (name dims.dim_cost_centre, kind FULL, grain (cost_centre_code));
SELECT cost_centre_code::TEXT AS cost_centre_code, cost_centre_name::TEXT AS cost_centre_name, NULLIF(parent_code::TEXT, '') AS parent_code,
       kind::TEXT AS kind, kind = 'factory' AS is_factory
FROM bronze.dim_cost_centre
