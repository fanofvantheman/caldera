/* The variability each stocking point plans its safety stock against (DEC-20261117-02 point 2): the standard deviation
   of the cases it shipped a week over the last 52 closed weeks — at a DC, the ship-tos it serves; at a plant, everything
   its materials shipped. This is the note's fallback (location_and_drp.md: demand variability, an upper bound — it
   counts movement the plan would have explained): Caldera keeps no weekly residual of the plan against what shipped.
   A material with fewer than 13 weeks shipped has none, and holds no safety stock. */
MODEL (name plan.demand_variability, kind FULL, grain (node_code, material_code));
WITH last AS (SELECT week_id FROM dims.dim_week WHERE period <= (SELECT MAX(period) FROM dims.dim_period WHERE period_state = 'CLOSED') ORDER BY week_id DESC LIMIT 52),
weekly AS (
  SELECT n.node_code, s.material_code, s.week_id, SUM(s.cases) AS cases
  FROM history.shipments s JOIN last USING (week_id) JOIN dims.ref_serving_node n USING (ship_to_code) GROUP BY ALL
  UNION ALL
  SELECT r.plant_code, s.material_code, s.week_id, SUM(s.cases)
  FROM history.shipments s JOIN last USING (week_id) JOIN dims.ref_route r ON r.material_code = s.material_code AND r.is_primary GROUP BY ALL
),
filled AS (                                            -- a week with nothing shipped is a zero, not a gap
  SELECT k.node_code, k.material_code, l.week_id, COALESCE(w.cases, 0) AS cases
  FROM (SELECT DISTINCT node_code, material_code FROM weekly) k CROSS JOIN last l
  LEFT JOIN weekly w ON w.node_code = k.node_code AND w.material_code = k.material_code AND w.week_id = l.week_id
)
SELECT node_code, material_code, COUNT(*) FILTER (WHERE cases > 0) AS weeks_shipped, AVG(cases) AS mean_weekly,
       CASE WHEN COUNT(*) FILTER (WHERE cases > 0) >= 13 THEN STDDEV_SAMP(cases) END AS sigma,
       'demand variability over the last 52 closed weeks (fallback, an upper bound)' AS source
FROM filled GROUP BY ALL
