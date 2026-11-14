/* The entitlements, each a row under a kind with the clause it came from, quoted: by layer (the entity's agreement; the
   statutory floor for a jurisdiction; an award where an entity has no agreement), instrument, classification (blank:
   every classification) and the period it runs from. The latest row per entitlement stands. The plan reads these rows,
   never a document. */
MODEL (name dims.reg_entitlement, kind FULL, grain (entitlement_id), audits (entitlement_kind_known));
SELECT e.entitlement_id::TEXT AS entitlement_id, e.layer::TEXT AS layer, e.instrument::TEXT AS instrument, e.instrument_name::TEXT AS instrument_name,
       NULLIF(e.entity_code::TEXT, '') AS entity_code, NULLIF(e.jurisdiction::TEXT, '') AS jurisdiction, e.kind::TEXT AS kind,
       NULLIF(e.classification::TEXT, '') AS classification, NULLIF(e.classification_name::TEXT, '') AS classification_name,
       NULLIF(e.applies_to::TEXT, '') AS applies_to, e.value::DOUBLE AS value, e.valid_from_period::TEXT AS valid_from_period,
       e.clause_ref::TEXT AS clause_ref, e.clause::TEXT AS clause, e.specimen::TEXT = 'Y' AS specimen,
       e.entered_by::TEXT AS entered_by, e.entered_on::TEXT AS entered_on,
       k.kind IS NOT NULL AS kind_known, COALESCE(k.priced, FALSE) AS priced
FROM bronze.reg_entitlement e
LEFT JOIN dims.ref_entitlement_kind k ON k.kind = e.kind
QUALIFY ROW_NUMBER() OVER (PARTITION BY e.entitlement_id ORDER BY CASE WHEN e.source_file LIKE '20%' THEN e.source_file ELSE '0' END DESC, e.file_row_number DESC) = 1
