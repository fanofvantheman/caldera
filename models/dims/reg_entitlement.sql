/* The entitlements, each a row under a kind with the clause it came from, quoted: by layer (the entity's agreement; the
   statutory floor for a jurisdiction; an award where an entity has no agreement), instrument, classification (blank:
   every classification) and the period it runs from. The latest row per entitlement stands. The plan reads these rows,
   never a document. An agreement taken in at the door adds a row only when a person has taken it — accepted as proposed,
   placed under another kind, or an unplaced clause approximated under a kind: the proposal's row under the kind the
   decision names, entered by whoever decided it, its clause quoted as the tool found it in the document. */
MODEL (name dims.reg_entitlement, kind FULL, grain (entitlement_id), audits (entitlement_kind_known));
SELECT e.entitlement_id::TEXT AS entitlement_id, e.layer::TEXT AS layer, e.instrument::TEXT AS instrument, e.instrument_name::TEXT AS instrument_name,
       NULLIF(e.entity_code::TEXT, '') AS entity_code, NULLIF(e.jurisdiction::TEXT, '') AS jurisdiction, e.kind::TEXT AS kind,
       NULLIF(e.classification::TEXT, '') AS classification, NULLIF(e.classification_name::TEXT, '') AS classification_name,
       NULLIF(e.applies_to::TEXT, '') AS applies_to, e.value::DOUBLE AS value, e.valid_from_period::TEXT AS valid_from_period,
       e.clause_ref::TEXT AS clause_ref, e.clause::TEXT AS clause, e.specimen::TEXT = 'Y' AS specimen,
       e.entered_by::TEXT AS entered_by, e.entered_on::TEXT AS entered_on,
       k.kind IS NOT NULL AS kind_known, COALESCE(k.priced, FALSE) AS priced
FROM (SELECT * FROM bronze.reg_entitlement
      QUALIFY ROW_NUMBER() OVER (PARTITION BY entitlement_id ORDER BY CASE WHEN source_file LIKE '20%' THEN source_file ELSE '0' END DESC, file_row_number DESC) = 1
      UNION ALL BY NAME
      SELECT p.proposal_id AS entitlement_id, 'agreement' AS layer, p.instrument, p.instrument_name, p.entity_code, NULL AS jurisdiction,
             d.target_code AS kind, p.classification, p.classification_name, p.applies_to, p.value, p.valid_from_period,
             p.clause_ref, p.clause, 'N' AS specimen, d.acted_by AS entered_by, d.acted_at AS entered_on
      FROM (SELECT * FROM bronze.reg_entitlement_proposal WHERE placed IN ('row', 'unplaced')
            QUALIFY ROW_NUMBER() OVER (PARTITION BY proposal_id ORDER BY source_file DESC, file_row_number DESC) = 1) p
      JOIN (SELECT * FROM bronze.reg_door_act WHERE door = 'EBA'
            QUALIFY ROW_NUMBER() OVER (PARTITION BY kind, item_code ORDER BY acted_at DESC, source_file DESC, file_row_number DESC) = 1) d
        ON d.item_code = p.proposal_id AND d.state = 'decided' AND d.resolution IN ('accept', 'alter', 'approximate')) e
LEFT JOIN dims.ref_entitlement_kind k ON k.kind = e.kind
