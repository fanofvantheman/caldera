/* The actions each role grants. Vocabulary: layer.<n>.enter|withdraw, delta.<supply|allocation|timing>.enter, shaping.enter,
   register.<kind>.maintain, structure.<dim>.maintain, bom.version.release, mapping.<propose|accept|alter>, version.<name|freeze|declare_reference>,
   scenario.<create|promote>, standard.<derive|declare>, cycle.<open|close>, review.<step>.close, decision.<record|accept>, capex.<project.enter|approve>,
   policy.production.accept, tier.step.accept, headcount.enter, schedule.line.enter, run.plan, read.<plan|reading|drill|health|proof>. */
MODEL (name dims.ctl_role_action, kind FULL, grain (role_code, action), audits (role_action_vocabulary));
SELECT role_code::TEXT AS role_code, action::TEXT AS action FROM bronze.ctl_role_action
