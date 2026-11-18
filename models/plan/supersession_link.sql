/* Supersession (DEC-20261118-01, DEC-20261117-04): one link between materials on a Plan, kept on Launches — a share for
   each from → to pair, an optional uplift with a reason (in the innovation layer), an optional end (the baseline goes back
   to the item it stood in for), the switch (on a week, or when the predecessor's stock runs out), and optionally the
   accounts it applies to (none named: all). The kind is what the person chose — Replace, Replace with a gain, Merge,
   Split, Temporary — a preset over the same settings, kept on the link. What a link carries is demand only. Each link is an
   act: the latest act of a link stands whole; a withdrawal names the link and the history goes back where it was. */
MODEL (name plan.supersession_link, kind FULL, grain (version_id, link_id, from_material, to_material));
WITH acts AS (
  SELECT act_id::TEXT AS act_id, link_id::TEXT AS link_id, action::TEXT AS action, version_id::TEXT AS version_id, kind::TEXT AS kind,
         from_material::TEXT AS from_material, to_material::TEXT AS to_material, TRY_CAST(share::TEXT AS DOUBLE) AS share,
         TRY_CAST(NULLIF(uplift_pct::TEXT, '') AS DOUBLE) AS uplift_pct, NULLIF(uplift_reason::TEXT, '') AS uplift_reason,
         switch::TEXT AS switch, NULLIF(switch_week::TEXT, '') AS switch_week, NULLIF(end_week::TEXT, '') AS end_week,
         NULLIF(accounts::TEXT, '') AS accounts, reason::TEXT AS reason, entered_by::TEXT AS entered_by, entered_at::TEXT AS entered_at,
         source_file, file_row_number
  FROM bronze.reg_supersession
),
latest AS (                                            -- the latest act of each link, whole
  SELECT version_id, link_id, act_id, action FROM acts
  QUALIFY ROW_NUMBER() OVER (PARTITION BY version_id, link_id ORDER BY entered_at DESC, source_file DESC, file_row_number DESC) = 1
)
SELECT a.version_id, a.link_id, a.act_id, a.kind, a.from_material, a.to_material, a.share, a.uplift_pct, a.uplift_reason, a.switch, a.switch_week,
       a.end_week, a.accounts, a.reason, a.entered_by, a.entered_at
FROM acts a JOIN latest l ON l.version_id = a.version_id AND l.link_id = a.link_id AND l.act_id = a.act_id
WHERE l.action = 'set'
