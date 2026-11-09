/* One row per worklist: what it is, where its rows are, how serious, how many, what to do, and who sees the whole.
   VERDICT: the run excluded the rows and someone must act; WARN: in the plan, someone should look. */
MODEL (name plan.run_health, kind FULL, grain (name));
WITH readers AS (SELECT STRING_AGG(DISTINCT principal, ', ') AS whose FROM dims.effective_entitlements WHERE action = 'read.health')
SELECT w.name, w.surface, w.severity, w.items, w.what_to_do, r.whose
FROM (
  SELECT 'entries refused' AS name, 'plan.worklist_entry_refused' AS surface, 'VERDICT' AS severity, COUNT(*) AS items,
         'the author does not own the layer: the owner enters it, or the author withdraws it' AS what_to_do FROM plan.worklist_entry_refused
  UNION ALL SELECT 'withdrawals refused', 'plan.worklist_withdrawal_refused', 'VERDICT', COUNT(*),
         'only the layer owner withdraws: ask them, or leave the entry standing' FROM plan.worklist_withdrawal_refused
  UNION ALL SELECT 'entries unresolved', 'plan.worklist_entry_unresolved', 'VERDICT', COUNT(*),
         'withdraw and re-enter with a scope that reaches members and a window inside the horizon' FROM plan.worklist_entry_unresolved
  UNION ALL SELECT 'reasons unknown', 'plan.worklist_reason_unknown', 'WARN', COUNT(*),
         'give a reason the vocabulary has, or add the reason to the register' FROM plan.worklist_reason_unknown
  UNION ALL SELECT 'cells below zero', 'plan.worklist_stack_negative', 'WARN', COUNT(*),
         'an exit or dip larger than the baseline: trim the entry or accept the zero' FROM plan.worklist_stack_negative
) w CROSS JOIN readers r
