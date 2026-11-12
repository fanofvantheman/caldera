/* What a person may decide at each door, per kind of disagreement: reference data, one row per door × kind × resolution.
   A kind says what disagrees and what the plan does meanwhile; a resolution says what the choice is, what it names of
   ours (if anything), whether it takes the proposal, whether it needs a reason, and the verb that lets a person make it.
   The promotions system's codes (door TPM) are one kind per subject: accept the proposal, or alter it to one of ours.
   The forecasting system's run (door FCS): a code in the run the plan has not got, and a series the plan has that the run
   has not. A third door is a query that finds its disagreements and rows here. */
MODEL (name plan.ref_door_resolution, kind FULL, grain (door, kind, resolution));
SELECT * FROM (VALUES
  ('TPM', 'customer',     'Their planning account, not yet ours', 'every event that uses it is held', 'accept', 'Accept', 'accepted as', NULL, TRUE, FALSE, 'mapping.accept', 1),
  ('TPM', 'customer',     'Their planning account, not yet ours', 'every event that uses it is held', 'alter', 'Map to', 'mapped to', 'account', FALSE, TRUE, 'mapping.alter', 2),
  ('TPM', 'material',     'Their product group, not yet ours', 'every event that uses it is held', 'accept', 'Accept', 'accepted as', NULL, TRUE, FALSE, 'mapping.accept', 3),
  ('TPM', 'material',     'Their product group, not yet ours', 'every event that uses it is held', 'alter', 'Map to', 'mapped to', 'promo group', FALSE, TRUE, 'mapping.alter', 4),
  ('TPM', 'mechanic',     'Their tactic, not yet ours', 'every event that uses it is held', 'accept', 'Accept', 'accepted as', NULL, TRUE, FALSE, 'mapping.accept', 5),
  ('TPM', 'mechanic',     'Their tactic, not yet ours', 'every event that uses it is held', 'alter', 'Map to', 'mapped to', 'mechanic', FALSE, TRUE, 'mapping.alter', 6),
  ('TPM', 'funding_type', 'Their fund type, not yet ours', 'every event that uses it is held', 'accept', 'Accept', 'accepted as', NULL, TRUE, FALSE, 'mapping.accept', 7),
  ('TPM', 'funding_type', 'Their fund type, not yet ours', 'every event that uses it is held', 'alter', 'Map to', 'mapped to', 'funding type', FALSE, TRUE, 'mapping.alter', 8),
  ('TPM', 'status',       'Their status word, not yet ours', 'every event that uses it is held', 'accept', 'Accept', 'accepted as', NULL, TRUE, FALSE, 'mapping.accept', 9),
  ('TPM', 'status',       'Their status word, not yet ours', 'every event that uses it is held', 'alter', 'Map to', 'mapped to', 'status', FALSE, TRUE, 'mapping.alter', 10),
  ('FCS', 'theirs_not_ours', 'In the run, not in the plan', 'held out of the plan', 'same_as', 'The same as one of ours', 'the same as', 'material', FALSE, TRUE, 'layer.1.enter', 11),
  ('FCS', 'theirs_not_ours', 'In the run, not in the plan', 'held out of the plan', 'place_under', 'Place under a product', 'placed under', 'product', FALSE, TRUE, 'layer.1.enter', 12),
  ('FCS', 'theirs_not_ours', 'In the run, not in the plan', 'held out of the plan', 'leave_out', 'Leave out', 'left out', NULL, FALSE, TRUE, 'layer.1.enter', 13),
  ('FCS', 'ours_not_theirs', 'In the plan, not in the run', 'on our calculation', 'keep_ours', 'Keep our calculation', 'our calculation kept', NULL, FALSE, TRUE, 'layer.1.enter', 14),
  ('FCS', 'ours_not_theirs', 'In the plan, not in the run', 'on our calculation', 'zero', 'Zero on purpose', 'zero on purpose', NULL, FALSE, TRUE, 'layer.1.enter', 15)
) AS t(door, kind, kind_says, meanwhile, resolution, label, says, names, takes_proposal, reason_required, verb, ord)
