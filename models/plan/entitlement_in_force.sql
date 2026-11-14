/* The entitlement in force for each entity, by kind, classification and the pattern it applies to: the entity's agreement
   where it speaks, the statutory floor for the entity's jurisdiction where it does not — the Commonwealth's (AU) and its
   state's (dim_entity.state). An award would sit between them only where an entity has no agreement; both of Caldera's
   have one. A floor row with no value awaits its source and is never read as zero. Beside each on-cost, the rate the
   labour model uses today (dims.ref_on_cost), so the gap between the register and the floor is visible. */
MODEL (name plan.entitlement_in_force, kind FULL, grain (entity_code, kind, classification, applies_to));
WITH ent AS (SELECT entity_code, state FROM dims.dim_entity),
ag AS (SELECT r.* FROM dims.reg_entitlement r WHERE r.layer = 'agreement' AND r.kind_known
       QUALIFY ROW_NUMBER() OVER (PARTITION BY r.entity_code, r.kind, COALESCE(r.classification, ''), COALESCE(r.applies_to, '') ORDER BY r.valid_from_period DESC) = 1),
fl AS (SELECT e.entity_code, r.* EXCLUDE (entity_code) FROM dims.reg_entitlement r JOIN ent e ON r.jurisdiction IN ('AU', e.state)
       WHERE r.layer = 'statute' AND r.kind_known
       QUALIFY ROW_NUMBER() OVER (PARTITION BY e.entity_code, r.kind, COALESCE(r.classification, ''), COALESCE(r.applies_to, '') ORDER BY r.valid_from_period DESC) = 1),
k AS (SELECT entity_code, kind, COALESCE(classification, '') AS classification, COALESCE(applies_to, '') AS applies_to FROM ag
      UNION SELECT entity_code, kind, COALESCE(classification, ''), COALESCE(applies_to, '') FROM fl)
SELECT k.entity_code, k.kind, k.classification, k.applies_to, COALESCE(a.classification_name, f.classification_name) AS classification_name,
       CASE WHEN a.entitlement_id IS NOT NULL THEN 'agreement' ELSE 'statute' END AS layer,
       COALESCE(a.entitlement_id, f.entitlement_id) AS entitlement_id, COALESCE(a.instrument_name, f.instrument_name) AS instrument_name,
       CASE WHEN a.entitlement_id IS NOT NULL THEN a.value ELSE f.value END AS value,
       a.entitlement_id IS NULL AND f.value IS NULL AS awaiting_source,
       COALESCE(a.specimen, f.specimen) AS specimen, f.value AS floor_value, f.entitlement_id IS NOT NULL AS floor_speaks, f.specimen AS floor_specimen,
       oc.rate AS used_today
FROM k
LEFT JOIN ag a ON a.entity_code = k.entity_code AND a.kind = k.kind AND COALESCE(a.classification, '') = k.classification AND COALESCE(a.applies_to, '') = k.applies_to
LEFT JOIN fl f ON f.entity_code = k.entity_code AND f.kind = k.kind AND COALESCE(f.classification, '') = k.classification AND COALESCE(f.applies_to, '') = k.applies_to
LEFT JOIN dims.ref_on_cost oc ON k.kind = 'on_cost' AND oc.entity_code = k.entity_code AND oc.component = k.applies_to
