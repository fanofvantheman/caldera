/* A step that plans a shorter window than the version declares it here — never a longer one: the step plans the lesser
   of its own window and the version's horizon, from the period after the version's last actual one. */
MODEL (name dims.ref_step_horizon, kind FULL, grain (step));
SELECT step::TEXT AS step, step_label::TEXT AS step_label, horizon_periods::INT AS horizon_periods, says::TEXT AS says, ord::INT AS ord
FROM bronze.ref_step_horizon
