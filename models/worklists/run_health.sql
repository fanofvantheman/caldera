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
  UNION ALL SELECT 'submissions open', 'plan.worklist_open_submissions', 'ACTION', COUNT(*),
         'submit what is yours when it is complete; a unit submits when its layers are in; the plan when its units are' FROM plan.worklist_open_submissions
  UNION ALL SELECT 'entries after submission', 'plan.worklist_entry_after_submission', 'VERDICT', COUNT(*),
         'the layer is closed at that scope: the holder reopens it, or the entry waits for the next cycle' FROM plan.worklist_entry_after_submission
  UNION ALL SELECT 'promotions held', 'plan.worklist_promo_held', 'VERDICT', COUNT(*),
         'review the codes it waits for: the event enters on the first run after its mappings are accepted or altered' FROM plan.worklist_promo_held
  UNION ALL SELECT 'promotions refused', 'plan.worklist_promo_refused', 'VERDICT', COUNT(*),
         'the event came through the wrong door: the sender withdraws it, or it is entered where the account''s promotions are kept' FROM plan.worklist_promo_refused
  UNION ALL SELECT 'mappings to review', 'plan.worklist_promo_mapping_review', 'ACTION', COUNT(*),
         'accept the proposal, or alter it to another of ours with a reason' FROM plan.worklist_promo_mapping_review
  UNION ALL SELECT 'forecast disagreements', 'plan.worklist_forecast_queue', 'ACTION', COUNT(*),
         'decide each on the statistical forecast page: the same as one of ours, placed, left out; keep our calculation, or zero' FROM plan.worklist_forecast_queue
  UNION ALL SELECT 'ledger cost centres unmapped', 'plan.worklist_cost_centre_unmapped', 'ACTION', COUNT(*),
         'decide each on the cost centres page: map it to one of ours, open a planning cost centre for it, or leave it out with a reason' FROM plan.worklist_cost_centre_unmapped
  UNION ALL SELECT 'agreement clauses to decide', 'plan.worklist_entitlement_queue', 'ACTION', COUNT(*),
         'decide each on the entitlements page: accept it, place it under another kind or leave it out; a clause under no kind: not material, or approximate it under a kind' FROM plan.worklist_entitlement_queue
) w CROSS JOIN readers r
