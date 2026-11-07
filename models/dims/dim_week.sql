/* The trading calendar at week grain: every week in exactly one period, Monday to Sunday. The calendar is
   always operating; readings choose the grain. */
MODEL (name dims.dim_week, kind FULL, grain (week_id), audits (week_in_one_period));
SELECT week_id::TEXT AS week_id, fiscal_year::INT AS fiscal_year, fiscal_week::INT AS fiscal_week, period::TEXT AS period,
       fiscal_period::INT AS fiscal_period, quarter::INT AS quarter, week_start::DATE AS week_start, week_end::DATE AS week_end,
       calendar_year::INT AS calendar_year, calendar_month::INT AS calendar_month, is_53rd::TEXT = 'True' AS is_53rd_week,
       ROW_NUMBER() OVER (ORDER BY week_start) AS week_sequence
FROM bronze.dim_week
