/* The reports people made: each a saved question over the measure register — measures, what is on the rows (an axis
   and a level), what is across, the versions, a comparison, filters — owned by whoever made it. Never figures: the face
   draws each from the plan's own models as whoever opens it. The latest save of a report stands. */
MODEL (name plan.report, kind FULL, grain (report_id));
SELECT report_id::TEXT AS report_id, owner::TEXT AS owner, report_name::TEXT AS report_name, measures::TEXT AS measures,
       rows_axis::TEXT AS rows_axis, NULLIF(rows_level::TEXT, '') AS rows_level, columns_axis::TEXT AS columns_axis,
       NULLIF(versions::TEXT, '') AS versions, compare::TEXT = 'Y' AS compare, NULLIF(filter_material::TEXT, '') AS filter_material,
       NULLIF(filter_customer::TEXT, '') AS filter_customer, saved_on::TEXT AS saved_on
FROM bronze.reg_report
QUALIFY ROW_NUMBER() OVER (PARTITION BY report_id ORDER BY CASE WHEN source_file LIKE '20%' THEN source_file ELSE '0' END DESC, file_row_number DESC) = 1
