/* The crew each line runs with: the direct labour of a case is the crew over the route's cases an hour. */
MODEL (name dims.ref_line_crew, kind FULL, grain (line_code));
SELECT line_code::TEXT AS line_code, crew::DOUBLE AS crew FROM bronze.ref_line_crew
