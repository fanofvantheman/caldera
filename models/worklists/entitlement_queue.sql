/* What the agreement door waits on: every row the first pass proposed from a document, and every clause it placed under
   no kind, that nobody has decided — one row per proposal, in the doors' queue contract (door EBA). A proposed row is
   not read by the labour model until a person accepts it, or places it under another kind; an unplaced clause is what the
   plan does not price until a person closes it as not material or approximates it under a kind. A row whose quotation is
   not in the document was refused at the door and is never here. Routed to the holders of the register's verb. */
MODEL (name plan.worklist_entitlement_queue, kind FULL, grain (kind, item_code, scope_code));
WITH p AS (
  SELECT * FROM bronze.reg_entitlement_proposal WHERE placed IN ('row', 'unplaced')
  QUALIFY ROW_NUMBER() OVER (PARTITION BY proposal_id ORDER BY source_file DESC, file_row_number DESC) = 1
),
decided AS (SELECT item_code FROM plan.door_act WHERE door = 'EBA' AND in_force),
holders AS (SELECT STRING_AGG(DISTINCT principal, ', ' ORDER BY principal) AS whose FROM dims.effective_entitlements WHERE action = 'register.agreement.maintain')
SELECT 'EBA' AS door, CASE p.placed WHEN 'row' THEN 'clause' ELSE 'unplaced' END AS kind, p.proposal_id::TEXT AS item_code, 'ALL' AS scope_code,
       '' AS reaches, p.clause_ref || ' — “' || p.clause || '”' AS description,
       CONCAT_WS(' · ', p.instrument, NULLIF(p.classification_name, ''), NULLIF(p.applies_to, ''),
                 CASE WHEN p.value::DOUBLE <> 0 THEN p.value::TEXT END, CASE WHEN NULLIF(p.valid_from_period, '') IS NOT NULL THEN 'from ' || p.valid_from_period END) AS as_sent,
       NULL::TEXT AS would_bring,
       CASE p.placed WHEN 'row' THEN 'not read by the labour model' ELSE 'the plan does not price it' END AS meanwhile,
       CASE p.placed WHEN 'row' THEN p.kind END AS proposed_target,
       NULLIF(CONCAT_WS(' · ', NULLIF(p.confidence, ''), NULLIF(p.rationale, '')), '') AS proposal,
       h.whose, p.instrument || ' ' || p.clause_ref || ': ' || CASE p.placed WHEN 'row' THEN 'proposed as ' || p.kind ELSE 'fits no kind' END AS item,
       p.instrument, p.document, p.taken_in_at
FROM p CROSS JOIN holders h
WHERE p.proposal_id NOT IN (SELECT item_code FROM decided)
