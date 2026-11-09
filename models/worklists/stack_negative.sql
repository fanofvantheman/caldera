/* Cells whose layers sum below zero: an exit or a dip larger than what was there. In the plan as they stand; the demand
   planner owns the stack and decides. */
MODEL (name plan.worklist_stack_negative, kind FULL, grain (version_id, material_code, ship_to_code, week_id));
WITH owners AS (SELECT STRING_AGG(DISTINCT principal, ', ') AS whose FROM dims.effective_entitlements WHERE action = 'layer.1.enter'),
cells AS (
  SELECT s.version_id, s.material_code, s.ship_to_code, s.week_id, SUM(s.cases) AS cases
  FROM plan.demand_stack s GROUP BY ALL HAVING SUM(s.cases) < -0.5
)
SELECT c.version_id, c.material_code, c.ship_to_code, c.week_id, c.cases,
       c.material_code || ' at ' || c.ship_to_code || ' in ' || c.week_id || ' sums to ' || ROUND(c.cases) || ' cases' AS item, o.whose
FROM cells c CROSS JOIN owners o
