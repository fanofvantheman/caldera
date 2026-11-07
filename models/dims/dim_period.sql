/* Periods with their state and RELATIVE position, so a reader filters on "latest closed" or an offset, never on a
   literal period. Current = the open period; latest closed = the default reading period. No OPEN row → nothing is
   current and every offset is NULL: a null is honest where a zero would lie. */
MODEL (name dims.dim_period, kind FULL, grain (period), audits (period_single_open));
WITH p AS (
  SELECT period::TEXT AS period, fiscal_year::INT AS fiscal_year, fiscal_period::INT AS fiscal_period, quarter::INT AS quarter,
         period_start::DATE AS period_start, period_end::DATE AS period_end, weeks::INT AS weeks_in_period, state::TEXT AS period_state,
         period = MAX(CASE WHEN state = 'OPEN' THEN period END) OVER () AS is_current_period,
         period = MAX(CASE WHEN state = 'CLOSED' THEN period END) OVER () AS is_latest_closed,
         ROW_NUMBER() OVER (ORDER BY period) AS period_sequence,
         LAG(period) OVER (ORDER BY period) AS prior_period,
         LAG(period, 12) OVER (ORDER BY period) AS prior_year_period
  FROM bronze.ctl_period
)
SELECT *, period_sequence - MAX(CASE WHEN is_current_period THEN period_sequence END) OVER () AS periods_from_current
FROM p
