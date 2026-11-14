AUDIT (name role_action_vocabulary);
/* blocking: an action the plan does not have grants nothing and looks like it granted something */
SELECT role_code, action FROM @this_model
WHERE NOT (action SIMILAR TO 'layer\.[1-9]\.(enter|withdraw|submit|reopen)'
        OR action SIMILAR TO 'demand\.(unit|plan)\.(submit|reopen)'
        OR action SIMILAR TO 'delta\.(supply|allocation|timing)\.enter'
        OR action = 'shaping.enter'
        OR action = 'overlay.finance.enter'
        OR action SIMILAR TO 'register\.[a-z_.]+\.maintain'
        OR action SIMILAR TO 'structure\.(material|customer|location|position)\.maintain'
        OR action = 'bom.version.release'
        OR action SIMILAR TO 'mapping\.(propose|accept|alter)'
        OR action SIMILAR TO 'version\.(name|freeze|declare_reference)'
        OR action SIMILAR TO 'scenario\.(create|promote)'
        OR action SIMILAR TO 'standard\.(derive|declare)'
        OR action SIMILAR TO 'cycle\.(open|close)'
        OR action SIMILAR TO 'review\.(portfolio|demand|supply|reconciliation|mbr)\.close'
        OR action SIMILAR TO 'decision\.(record|accept)'
        OR action IN ('capex.project.enter', 'capex.approve', 'policy.production.accept', 'tier.step.accept', 'headcount.enter', 'schedule.line.enter', 'run.plan')
        OR action SIMILAR TO 'read\.(plan|reading|drill|health|proof|pay)');

AUDIT (name role_scope_is_a_node);
/* blocking: an assignment at a scope that is not a node of its dimension grants nothing */
SELECT principal, role_code, scope_dimension, scope_node FROM @this_model WHERE NOT scope_is_node;

AUDIT (name role_assignment_role_exists);
SELECT principal, role_code FROM @this_model WHERE NOT role_exists;

AUDIT (name signal_segregation, blocking false);
/* warn: one principal both enters a demand layer and enters the supply constraint — the constraint has a back door
   into the demand signal */
SELECT principal FROM @this_model
GROUP BY principal
HAVING BOOL_OR(action SIMILAR TO 'layer\.[1-9]\.enter') AND BOOL_OR(action = 'delta.supply.enter');

AUDIT (name role_action_registered);
/* blocking: a role, shipped or composed, grants only a right the plan has — every audit is written on these, so a role
   holding one the register lacks would hold something no audit knows */
SELECT role_code, action FROM @this_model WHERE action NOT IN (SELECT verb::TEXT FROM bronze.ref_verb);

AUDIT (name verb_class_vocabulary);
/* blocking: a right is one of five classes */
SELECT verb, right_class FROM @this_model WHERE right_class NOT IN ('enter', 'maintain', 'decide', 'read', 'run');
