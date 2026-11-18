/* The service level by class (DEC-20261117-02 points 2, 8): the fill rate each class of material is stocked for at
   every node — A at the top, C allowed to stock out. The one declared assumption the safety stock is solved from; a
   material's class is read from its share of the plan's cases (plan.service_class). Specimen values, a row to change. */
MODEL (name dims.ref_service_level, kind FULL, grain service_class);
SELECT * FROM (VALUES
  ('A', 0.99, 0.80, 'the materials that make the first 80% of the plan''s cases'),
  ('B', 0.97, 0.95, 'the next 15%'),
  ('C', 0.95, 1.00, 'the tail')
) AS t (service_class, fill_rate, cumulative_to, says)
