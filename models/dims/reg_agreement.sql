/* Each entity's agreement as a rate-side instrument: classification × hourly rate, effective from a period; the
   agreement's increase is a later row. Penalties, allowances and leave are not loaded (stage 3). */
MODEL (name dims.reg_agreement, kind FULL, grain (agreement, classification, valid_from_period));
SELECT agreement::TEXT AS agreement, agreement_name::TEXT AS agreement_name, entity_code::TEXT AS entity_code, classification::TEXT AS classification,
       classification_name::TEXT AS classification_name, hourly_rate::DOUBLE AS hourly_rate, valid_from_period::TEXT AS valid_from_period
FROM bronze.reg_agreement
