/* Neighbour lines declared on events: a promoted range taking volume from a neighbouring range of our own at the same
   account (cannibalisation, a negative rate) or lending volume to it (halo, a positive rate), as a rate on the
   neighbour's baseline in the event's window. Declared, never estimated; absent means none declared, not none assumed.
   The register is a log, one row per act; the latest row per version × event × neighbour scope is the line in force,
   and a rate of zero takes it out. A neighbour is a promo group or a material, our own range only, at the event's
   account; any material of the neighbour that is itself in the promoted range is left out — the event's own uplift
   already speaks for it. A line moves cases only: the neighbour carries no price reduction and no funding of the event,
   its cases are priced at its own list and terms. Lines on an event not in the calendar wait with the event. */
MODEL (name plan.promo_neighbour, kind FULL, grain (version_id, event_id, scope_material, material_code), audits (promo_neighbour_valid));
WITH acts AS (
  SELECT n.*, ROW_NUMBER() OVER (PARTITION BY n.version_id, n.event_id, n.scope_material
                                 ORDER BY n.entered_at DESC, CASE WHEN n.source_file LIKE '20%' THEN n.source_file ELSE '0' END DESC, n.file_row_number DESC) AS recency
  FROM bronze.reg_promo_neighbour n
),
lines AS (
  SELECT neighbour_id::TEXT AS neighbour_id, version_id::TEXT AS version_id, event_id::TEXT AS event_id, scope_material::TEXT AS scope_material,
         effect_type::TEXT AS effect_type, rate::DOUBLE AS rate, entered_by::TEXT AS entered_by, entered_at::TEXT AS entered_at, NULLIF(note::TEXT, '') AS note,
         NULLIF(copied_from::TEXT, '') AS copied_from
  FROM acts WHERE recency = 1 AND rate::DOUBLE <> 0
),
scope AS (   -- a neighbour scope resolves to materials: a promo group's members, or a material (its standard material)
  SELECT promo_group_code AS scope_material, material_code FROM dims.ref_promo_group
  UNION
  SELECT material_code, material_code FROM dims.dim_material WHERE material_code = standard_material
)
SELECT l.*, s.material_code, e.account_code, e.promo_group_code, e.window_start, e.window_end, e.event_id IS NOT NULL AS event_in_calendar,
       s.material_code IS NOT NULL AS scope_resolves,
       (l.effect_type = 'cannibalisation' AND l.rate < 0) OR (l.effect_type = 'halo' AND l.rate > 0) AS sign_fits
FROM lines l
LEFT JOIN scope s ON s.scope_material = l.scope_material
LEFT JOIN plan.promo_event e ON e.event_id = l.event_id AND e.version_id = l.version_id AND e.event_known
WHERE s.material_code IS NULL
   OR NOT EXISTS (SELECT 1 FROM dims.ref_promo_group g WHERE g.promo_group_code = e.promo_group_code AND g.material_code = s.material_code)
