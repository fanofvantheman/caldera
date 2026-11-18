/* Storage read against capacity (DEC-20261117-03): by version × node × class × period, the pallet positions taken at the
   period's end and at its peak — finished goods from the inventory plan (plan.inventory_flow), key raw materials from the
   material stock (plan.material_stock; the opening and the period's purchases are its peak) — against the node's own
   positions, the working limit below them, and the overflow tier at its rate. Utilisation is the peak over the own tier:
   a campaign business peaks after intake, and a period end never shows it. The cost of running out of room is the
   overflow tier's rate, a step; nothing here moves a unit cost (point 6). */
MODEL (name plan.storage_load, kind FULL, grain (version_id, node_code, storage_class, period));
WITH fg AS (
  SELECT f.version_id, f.node_code, a.storage_class, f.period, SUM(f.closing / a.units_per_pallet) AS end_pallets, SUM(f.peak / a.units_per_pallet) AS peak_pallets
  FROM plan.inventory_flow f JOIN dims.ref_storage_attribute a ON a.item_kind = 'finished' AND a.item_code = f.material_code GROUP BY ALL
),
rm AS (
  SELECT s.version_id, s.plant_code AS node_code, a.storage_class, s.period, SUM(s.closing_quantity / a.units_per_pallet) AS end_pallets,
         SUM((s.opening_quantity + s.purchase_quantity) / a.units_per_pallet) AS peak_pallets
  FROM plan.material_stock s JOIN dims.ref_storage_attribute a ON a.item_kind = 'input' AND a.item_code = s.input_code GROUP BY ALL
),
load AS (
  SELECT version_id, node_code, storage_class, period, SUM(end_pallets) AS end_pallets, SUM(peak_pallets) AS peak_pallets,
         SUM(CASE WHEN src = 'finished' THEN peak_pallets END) AS finished_pallets, SUM(CASE WHEN src = 'input' THEN peak_pallets END) AS input_pallets
  FROM (SELECT *, 'finished' AS src FROM fg UNION ALL SELECT *, 'input' FROM rm) GROUP BY ALL
),
cap AS (
  SELECT node_code, storage_class, SUM(CASE WHEN tier = 'own' THEN pallets END) AS own_pallets, SUM(CASE WHEN tier = 'overflow' THEN pallets END) AS overflow_pallets,
         MAX(CASE WHEN tier = 'overflow' THEN rate_per_pallet_week END) AS overflow_rate, MAX(working_limit) AS working_limit
  FROM dims.ref_storage_capacity GROUP BY ALL
),
grid AS (                                              -- every node × class declared or loaded, every period of the plan
  SELECT DISTINCT l.version_id, k.node_code, k.storage_class, l.period
  FROM (SELECT DISTINCT version_id, period FROM load) l
  CROSS JOIN (SELECT node_code, storage_class FROM cap UNION SELECT node_code, storage_class FROM load) k
)
SELECT g.version_id, g.node_code, g.storage_class, g.period, p.fiscal_year::INT AS fiscal_year, p.weeks_in_period AS weeks,
       COALESCE(l.end_pallets, 0) AS end_pallets, COALESCE(l.peak_pallets, 0) AS peak_pallets, l.finished_pallets, l.input_pallets,
       c.own_pallets, c.working_limit, c.own_pallets * c.working_limit AS working_pallets, c.overflow_pallets, c.overflow_rate,
       COALESCE(l.peak_pallets, 0) / NULLIF(c.own_pallets, 0) AS utilisation,
       GREATEST(0, COALESCE(l.peak_pallets, 0) - COALESCE(c.own_pallets, 0)) AS over_own,
       GREATEST(0, COALESCE(l.peak_pallets, 0) - COALESCE(c.own_pallets, 0)) * COALESCE(c.overflow_rate, 0) * p.weeks_in_period AS overflow_cost,
       GREATEST(0, COALESCE(l.peak_pallets, 0) - COALESCE(c.own_pallets, 0) - COALESCE(c.overflow_pallets, 0)) AS beyond_overflow,
       c.own_pallets IS NULL AS no_capacity
FROM grid g
JOIN dims.dim_period p ON p.period = g.period
LEFT JOIN load l ON l.version_id = g.version_id AND l.node_code = g.node_code AND l.storage_class = g.storage_class AND l.period = g.period
LEFT JOIN cap c ON c.node_code = g.node_code AND c.storage_class = g.storage_class
