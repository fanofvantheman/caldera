/* The role-based headcount: positions by the plan's cost centre × classification × employment type, FTE at the paid
   hours a week, from a period to a period (a casual pool is a position for the campaign periods). A name may be shown
   beside a position and carries nothing: the cost is the classification's. */
MODEL (name dims.reg_position, kind FULL, grain (position_id));
SELECT position_id::TEXT AS position_id, entity_code::TEXT AS entity_code, cost_centre_code::TEXT AS cost_centre_code, agreement::TEXT AS agreement,
       classification::TEXT AS classification, employment_type::TEXT AS employment_type, fte::DOUBLE AS fte, hours_per_week::DOUBLE AS hours_per_week,
       from_period::TEXT AS from_period, NULLIF(to_period::TEXT, '') AS to_period, NULLIF(shown_name::TEXT, '') AS shown_name
FROM bronze.reg_position
