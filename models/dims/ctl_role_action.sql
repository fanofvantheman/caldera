/* The actions each role grants. Vocabulary: layer.<n>.enter|withdraw, delta.<supply|allocation|timing>.enter, shaping.enter,
   register.<kind>.maintain, structure.<dim>.maintain, bom.version.release, mapping.<propose|accept|alter>, version.<name|freeze|declare_reference>,
   scenario.<create|promote>, standard.<derive|declare>, cycle.<open|close>, review.<step>.close, decision.<record|accept>, capex.<project.enter|approve>,
   policy.production.accept, tier.step.accept, headcount.enter, schedule.line.enter, run.plan, read.<plan|reading|drill|health|proof>. */
MODEL (name dims.ctl_role_action, kind FULL, grain (role_code, action), audits (role_action_vocabulary, role_action_registered));
SELECT role_code::TEXT AS role_code, action::TEXT AS action FROM bronze.ctl_role_action
UNION ALL                                  -- the client's own roles: the rights of each role's latest composition
SELECT DISTINCT r.role_code::TEXT, r.action::TEXT FROM bronze.reg_role r
WHERE (CASE WHEN r.source_file LIKE '20%' THEN r.source_file ELSE '0' END) = (SELECT MAX(CASE WHEN x.source_file LIKE '20%' THEN x.source_file ELSE '0' END) FROM bronze.reg_role x WHERE x.role_code = r.role_code)
  AND r.role_code::TEXT NOT IN (SELECT role_code::TEXT FROM bronze.ctl_role_definition)
