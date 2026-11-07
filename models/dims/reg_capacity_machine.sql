/* The machine capacity register: available hours per line per period at the tier in force, planned downtime and the
   efficiency assumption the plant manager stands behind. Campaign windows lift the tier. */
MODEL (name dims.reg_capacity_machine, kind FULL, grain (line_code, period), audits (capacity_line_exists));
SELECT c.line_code::TEXT AS line_code, c.period::TEXT AS period, c.tier::TEXT AS tier, c.shifts::INT AS shifts, c.working_days::INT AS working_days,
       c.available_hours::DOUBLE AS available_hours, c.planned_downtime_hours::DOUBLE AS planned_downtime_hours,
       c.efficiency_assumption::DOUBLE AS efficiency_assumption,
       (c.available_hours - c.planned_downtime_hours) * c.efficiency_assumption AS effective_hours,
       c.campaign_window::TEXT = 'Y' AS is_campaign_window, l.line_code IS NOT NULL AS line_exists
FROM bronze.reg_capacity_machine c
LEFT JOIN bronze.dim_line l ON l.line_code = c.line_code
