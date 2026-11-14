/* The rights the plan has — closed: every verb a role may grant, the shipped roles' and the client's own alike. Each carries
   its group (where in the plan it acts: layers, registers, versions, the budget …) and its class of right — enter, maintain
   (keep a register or a structure), decide (accept, approve, declare, close, record), read, run. The node a verb is held
   at, and the kind of plan, are where it is held (the assignment), never part of the verb. */
MODEL (name dims.ref_verb, kind FULL, grain (verb), audits (verb_class_vocabulary));
SELECT verb::TEXT AS verb, verb_group::TEXT AS verb_group, right_class::TEXT AS right_class, ord::INT AS ord FROM bronze.ref_verb
