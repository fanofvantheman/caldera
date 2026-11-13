/* What an employer pays on top of wages, by entity: superannuation, payroll tax at the entity's state's rate, workers'
   compensation. */
MODEL (name dims.ref_on_cost, kind FULL, grain (entity_code, component));
SELECT entity_code::TEXT AS entity_code, component::TEXT AS component, rate::DOUBLE AS rate FROM bronze.ref_on_cost
