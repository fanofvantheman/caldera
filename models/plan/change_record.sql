/* The record of acts read as one register: every act anyone has taken on the plan, one row each — who, when, why, what it
   did, and whether it stands, was withdrawn, was overwritten by a later act, or was refused by the plan's checks. Nothing
   here is new: each row is read from the register the act already lives in (layer entries, Finance's figures, the opex
   schedule, the assumptions, promotions typed here, submissions, version acts, the doors' decisions). A withdrawal is an
   act of its own and names the act it takes out of force. `version_id` is null for an act every version reads (a door's
   decision stands for every later arrival). `grid` and `withdraw_id` say where a standing act can be withdrawn and what
   names it — one figure, or a whole save. */
MODEL (name plan.change_record, kind FULL, grain (record, act_id));
WITH sched_standing AS (
  SELECT DISTINCT version_id, month_edit_id AS edit_id FROM plan.opex_schedule WHERE month_edit_id IS NOT NULL
  UNION SELECT DISTINCT version_id, rate_edit_id FROM plan.opex_schedule WHERE rate_edit_id IS NOT NULL
),
sched_driver AS (                         -- the latest driver act in force on each line is the one that stands
  SELECT edit_id FROM plan.schedule_edit
  WHERE action = 'driver' AND withdrawn_by_act IS NULL
  QUALIFY ROW_NUMBER() OVER (PARTITION BY version_id, entity_code, cost_centre_code, account_code ORDER BY entered_on DESC, edit_id DESC) = 1
),
fin_release AS (SELECT * FROM bronze.reg_finance_overlay WHERE action = 'release')
-- the demand plan: a contribution to a layer, and its withdrawal
SELECT 'demand plan' AS record, e.entry_id AS act_id, e.version_id, 'entry' AS act, e.entered_on::TIMESTAMP AS acted_at, e.entered_by AS by_whom,
       e.reason_code || COALESCE(' · ' || e.note, '') AS why,
       'layer ' || e.layer_no || ' · ' || e.scope_customer || ' × ' || e.scope_material || ' · ' || e.period_from ||
         CASE WHEN e.period_to <> e.period_from THEN '–' || e.period_to ELSE '' END || ' · ' || ROUND(e.value, 4) || ' ' || e.value_kind AS what,
       CASE WHEN e.withdrawn AND e.withdrawn_by_owner THEN 'withdrawn'
            WHEN NOT (e.version_known AND e.material_scope_resolves AND e.customer_scope_resolves AND e.entered_by_owner AND e.window_ordered) THEN 'refused'
            ELSE 'stands' END AS standing,
       NULL AS names, 'demand' AS grid, e.entry_id AS withdraw_id, e.entry_id AS save_id
FROM plan.layer_entry e
UNION ALL
SELECT 'demand plan', 'W:' || e.entry_id, e.version_id, 'withdrawal', e.withdrawn_on::TIMESTAMP, e.withdrawn_by, e.withdrawal_note,
       'withdraws ' || e.entry_id || ' (layer ' || e.layer_no || ')', 'stands', e.entry_id, NULL, NULL, NULL
FROM plan.layer_entry e WHERE e.withdrawn
UNION ALL
-- Finance's figures, each in its save, and a release (a whole save) or a withdrawal (one figure)
SELECT 'Finance''s plan', f.edit_id, f.version_id, 'figure', f.entered_on::TIMESTAMP, f.entered_by, COALESCE(f.reason, f.reason_code) || COALESCE(' · ' || f.note, ''),
       f.measure || ' ' || ROUND(f.value, 2) || ' at ' || f.scope_customer || ' × ' || f.scope_material || ' in ' || f.period,
       CASE WHEN f.state IN ('released', 'withdrawn') THEN 'withdrawn' WHEN f.state LIKE 'refused%' THEN 'refused'
            WHEN f.standing = 'overwritten' THEN 'overwritten' ELSE 'stands' END,
       NULL, 'finance', f.edit_id, f.save_id
FROM plan.finance_edit_reading f
UNION ALL
SELECT 'Finance''s plan', r.edit_id::TEXT, r.version_id::TEXT, CASE WHEN r.withdraws LIKE 'FS-%' THEN 'release' ELSE 'withdrawal' END,
       r.entered_on::TIMESTAMP, r.entered_by::TEXT, NULLIF(r.note::TEXT, ''),
       CASE WHEN r.withdraws LIKE 'FS-%' THEN 'releases the save ' ELSE 'withdraws the figure ' END || r.withdraws, 'stands', r.withdraws::TEXT, NULL, NULL, NULL
FROM fin_release r
UNION ALL
-- the opex schedule: a driver, a rate, a month, a reset — and a withdrawal of an act or a save
SELECT 'opex schedule', s.edit_id, s.version_id, s.action, s.entered_on, s.entered_by, s.reason_code || COALESCE(' · ' || s.note, ''),
       CASE s.action WHEN 'withdraw' THEN 'withdraws ' || s.withdraws
                     ELSE s.account_code || ' at ' || s.cost_centre_code || ' (' || s.entity_code || ')' ||
                          CASE s.action WHEN 'month' THEN ' · ' || s.period || ' ' || ROUND(s.value, 0)
                                        WHEN 'rate' THEN ' · rate ' || COALESCE(ROUND(s.value, 4)::TEXT, 'back to calculated')
                                        WHEN 'driver' THEN ' · driver ' || s.driver
                                        ELSE ' · ' || COALESCE(s.period, 'every typed month') || ' back to calculated' END END,
       CASE WHEN s.action = 'withdraw' OR s.action = 'reset' THEN CASE WHEN s.withdrawn_by_act IS NOT NULL THEN 'withdrawn' ELSE 'stands' END
            WHEN s.withdrawn_by_act IS NOT NULL THEN 'withdrawn'
            WHEN s.action IN ('month', 'rate') AND ss.edit_id IS NULL THEN 'overwritten'
            WHEN s.action = 'driver' AND sd.edit_id IS NULL THEN 'overwritten'
            ELSE 'stands' END,
       s.withdraws, CASE WHEN s.action <> 'withdraw' THEN 'schedule' END, CASE WHEN s.action <> 'withdraw' THEN s.edit_id END, s.save_id
FROM plan.schedule_edit s
LEFT JOIN sched_standing ss ON ss.version_id = s.version_id AND ss.edit_id = s.edit_id
LEFT JOIN sched_driver sd ON sd.edit_id = s.edit_id
UNION ALL
-- the assumptions: a value from a period; a later act on the same assumption and period takes its place
SELECT 'assumptions', a.amend_id::TEXT, a.version_id::TEXT, 'amendment', a.entered_on::TIMESTAMP, a.entered_by::TEXT, NULLIF(a.note::TEXT, ''),
       a.assumption_code || ' ' || a.value || ' from ' || a.valid_from,
       CASE WHEN ROW_NUMBER() OVER (PARTITION BY a.version_id, a.assumption_code, a.valid_from ORDER BY a.entered_on DESC, a.amend_id DESC) = 1 THEN 'stands' ELSE 'overwritten' END,
       NULL, NULL, NULL, NULL
FROM bronze.reg_assumption_amend a
UNION ALL
-- promotions typed here
SELECT 'promotions', p.event_id::TEXT, p.version_id::TEXT, 'event', p.entered_on::TIMESTAMP, p.owner::TEXT, NULLIF(p.note::TEXT, ''),
       p.account_code || ' × ' || p.promo_group_code || ' · ' || p.window_start || ' to ' || p.window_end || ' · ' || p.mechanic || ' · ' || p.status,
       CASE WHEN ROW_NUMBER() OVER (PARTITION BY p.event_id ORDER BY p.source_file DESC, p.file_row_number DESC) = 1 THEN 'stands' ELSE 'overwritten' END,
       NULL, NULL, NULL, NULL
FROM bronze.reg_promo_event p
UNION ALL
-- submissions: submit or reopen on a subject at a node; the latest stands
SELECT 'submissions', s.submission_id::TEXT, s.version_id::TEXT, s.action::TEXT, s.submitted_on::TIMESTAMP, s.submitted_by::TEXT, NULLIF(s.note::TEXT, ''),
       s.subject || ' at ' || s.scope_node,
       CASE WHEN ROW_NUMBER() OVER (PARTITION BY s.version_id, s.subject, s.scope_node ORDER BY s.submitted_on DESC, s.source_file DESC, s.file_row_number DESC) = 1 THEN 'stands' ELSE 'overwritten' END,
       NULL, NULL, NULL, NULL
FROM bronze.reg_submission s
UNION ALL
-- the version's own acts: closed, reopened
SELECT 'versions', a.act_id, a.version_id, a.act, a.entered_on::TIMESTAMP, a.entered_by, a.reason, a.version_id || ' ' || a.act,
       CASE WHEN ROW_NUMBER() OVER (PARTITION BY a.version_id ORDER BY a.entered_on DESC, a.act_id DESC) = 1 THEN 'stands' ELSE 'overwritten' END,
       NULL, NULL, NULL, NULL
FROM plan.version_act a
UNION ALL
-- the doors' decisions: read by every version
SELECT 'doors', d.act_id, NULL, d.resolution, d.acted_at::TIMESTAMP, d.acted_by, COALESCE(d.reason, d.rationale),
       d.door || ' · ' || d.kind || ' · ' || d.item_code || COALESCE(' → ' || d.target_code, ''),
       CASE WHEN d.in_force THEN 'stands' ELSE 'overwritten' END, NULL, NULL, NULL, NULL
FROM plan.door_act d
