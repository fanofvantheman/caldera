/* The assumptions in force: per version, assumption and period of the version's horizon, the value every plan on that
   version is valued with. The version's own value (dims.reg_assumption, period 'ALL') holds until Finance amends it;
   an amendment is a value from a period, placed as a new row and never an edit of the one in force — the latest act per
   version × assumption × period stands, and runs until the next one starts. Read by every calculation that uses an
   assumption, by period (plan.ref_assumption_reader says which). */
MODEL (name plan.assumption_in_force, kind FULL, grain (version_id, assumption_code, period), audits (one_value_per_period));
WITH acts AS (
  SELECT a.version_id::TEXT AS version_id, a.assumption_code::TEXT AS assumption_code, a.valid_from::TEXT AS valid_from, a.value::DOUBLE AS value,
         NULLIF(a.note::TEXT, '') AS note, a.entered_by::TEXT AS entered_by, a.entered_on::TEXT AS entered_on, a.amend_id::TEXT AS amend_id,
         CASE WHEN a.source_file LIKE '20%' THEN a.source_file END AS amended_by_file,
         ROW_NUMBER() OVER (PARTITION BY a.version_id, a.assumption_code, a.valid_from
                            ORDER BY CASE WHEN a.source_file LIKE '20%' THEN a.source_file ELSE '0' END DESC, a.file_row_number DESC) AS recency
  FROM bronze.reg_assumption_amend a
  WHERE a.valid_from <> 'ALL'                -- a version's own value, copied at naming, is read in dims.reg_assumption
),
base AS (SELECT * FROM dims.reg_assumption WHERE period = 'ALL'),
horizon AS (
  SELECT v.version_id, p.period, p.fiscal_year FROM dims.ctl_version v JOIN dims.dim_period p ON p.period BETWEEN v.horizon_start AND v.horizon_end
)
SELECT b.version_id, b.assumption_code, b.assumption_name, b.kind, h.period, h.fiscal_year,
       COALESCE(a.value, b.value) AS value, b.value AS version_value,
       CASE WHEN a.valid_from IS NULL THEN 'version' ELSE 'amended' END AS source,
       a.valid_from AS amended_from, a.amend_id, a.note AS amend_note, a.entered_by AS amended_by, a.entered_on AS amended_on, a.amended_by_file
FROM base b
JOIN horizon h ON h.version_id = b.version_id
LEFT JOIN acts a ON a.recency = 1 AND a.version_id = b.version_id AND a.assumption_code = b.assumption_code AND a.valid_from <= h.period
QUALIFY ROW_NUMBER() OVER (PARTITION BY b.version_id, b.assumption_code, h.period ORDER BY a.valid_from DESC NULLS LAST) = 1
