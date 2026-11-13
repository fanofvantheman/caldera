/* Cost centres and the organisation above them — the plan's own cost centres, a normalised set over each entity's ledger
   (dims.reg_cost_centre_map). The labour model is declared per cost centre: by role where the entitlement accrues to the
   role (the factory cost centres), by name where it does not (the overhead ones). */
MODEL (name dims.dim_cost_centre, kind FULL, grain (cost_centre_code));
SELECT cost_centre_code::TEXT AS cost_centre_code, cost_centre_name::TEXT AS cost_centre_name, NULLIF(parent_code::TEXT, '') AS parent_code,
       kind::TEXT AS kind, kind = 'factory' AS is_factory, NULLIF(labour_model::TEXT, '') AS labour_model
FROM bronze.dim_cost_centre
