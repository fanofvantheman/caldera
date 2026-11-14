/* A version is open or closed — the two states a person sees (DEC-20261113-05). Read from the acts: the latest close or
   reopen decides; a version with no act is as it was named (open, or closed when named frozen, closed or retired — the
   data's frozen and closed are one state). Closed means no entry and no change of any register on it; it stays readable,
   and every calculation keeps reading it. The actuals are closed by the period, not by an act. Whether the version is the
   declared reference of another is carried here, because such a version is not reopened.
   Which version is the latest view in force is carried here too: it moves only by promotion (a `promote` act — the
   version comes back whole, nothing merged); naming a version from a base never moves it. */
MODEL (name plan.version_state, kind FULL, grain (version_id));
WITH latest AS (
  SELECT a.*, ROW_NUMBER() OVER (PARTITION BY a.version_id ORDER BY a.entered_on DESC, COALESCE(a.placed_by_file, '0') DESC, a.file_row_number DESC) AS r
  FROM plan.version_act a WHERE a."act" IN ('close', 'reopen')
),
counts AS (SELECT version_id, COUNT(*) AS acts FROM plan.version_act GROUP BY 1),
promoted AS (                -- the latest view in force: the version of the latest promotion; with none, the latest one
  SELECT version_id, entered_by, entered_on, reason FROM plan.version_act WHERE "act" = 'promote'    -- of its kind not named from a base
  ORDER BY entered_on DESC, COALESCE(placed_by_file, '0') DESC, file_row_number DESC LIMIT 1
),
latest_view AS (
  SELECT COALESCE((SELECT version_id FROM promoted),
                  (SELECT version_id FROM dims.ctl_version WHERE version_kind = 'latest_view' AND base_version IS NULL
                   ORDER BY named_on DESC, version_id DESC LIMIT 1)) AS version_id
),
refs AS (SELECT reference_version AS version_id, STRING_AGG(version_id, ', ' ORDER BY version_id) AS reference_of FROM dims.ctl_version
         WHERE reference_version IS NOT NULL GROUP BY 1)
SELECT v.version_id, v.status AS named_status,
       CASE WHEN v.version_kind = 'actual' THEN 'closed' WHEN l."act" = 'close' THEN 'closed' WHEN l."act" = 'reopen' THEN 'open'
            WHEN v.status = 'open' THEN 'open' ELSE 'closed' END AS state,
       l."act" AS last_act, l.entered_by AS last_act_by, l.entered_on AS last_act_on, l.reason AS last_act_reason,
       COALESCE(c.acts, 0) AS acts, r.reference_of, r.reference_of IS NOT NULL AS is_reference,
       v.version_id = (SELECT version_id FROM latest_view) AS is_latest_view,
       CASE WHEN v.version_id = (SELECT version_id FROM promoted) THEN (SELECT entered_by FROM promoted) END AS promoted_by,
       CASE WHEN v.version_id = (SELECT version_id FROM promoted) THEN (SELECT entered_on FROM promoted) END AS promoted_on,
       CASE WHEN v.version_id = (SELECT version_id FROM promoted) THEN (SELECT reason FROM promoted) END AS promoted_reason,
       v.base_version, v.named_by_act
FROM dims.ctl_version v
LEFT JOIN latest l ON l.version_id = v.version_id AND l.r = 1
LEFT JOIN counts c ON c.version_id = v.version_id
LEFT JOIN refs r ON r.version_id = v.version_id
