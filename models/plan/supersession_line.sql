/* What each link does to the demand plan (DEC-20261118-01): from its switch week (and until its end, where it has one),
   the predecessor's baseline at the accounts the link applies to moves — off the predecessor, onto each successor at its
   share, in the baseline layer — the rest of it lost volume, shown; a declared uplift is the successor's taken share ×
   the uplift, in the innovation layer. A link withdrawn takes its lines with it: the history is where it was. */
MODEL (name plan.supersession_line, kind FULL, grain (version_id, link_id, layer_no, material_code, ship_to_code, week_id, part));
WITH l AS (
  SELECT k.*, s.switch_week AS effective_week FROM plan.supersession_link k
  JOIN plan.supersession_switch s ON s.version_id = k.version_id AND s.link_id = k.link_id
),
base AS (                                              -- the predecessor's baseline the link reaches, before any link
  SELECT l.version_id, l.link_id, l.from_material, b.ship_to_code, b.account_code, b.week_id, SUM(b.cases) AS cases
  FROM (SELECT DISTINCT version_id, link_id, from_material, effective_week, end_week, accounts FROM l) l
  JOIN plan.layer1_lines b ON b.version_id = l.version_id AND b.material_code = l.from_material
  WHERE b.week_id >= l.effective_week AND (l.end_week IS NULL OR b.week_id <= l.end_week)
    AND (l.accounts IS NULL OR list_contains(string_split(l.accounts, ','), b.account_code))
  GROUP BY ALL
)
SELECT b.version_id, b.link_id, 1 AS layer_no, b.from_material AS material_code, b.ship_to_code, b.account_code, b.week_id, 'off' AS part, -b.cases AS cases
FROM base b
UNION ALL
SELECT b.version_id, b.link_id, 1, l.to_material, b.ship_to_code, b.account_code, b.week_id, 'on', b.cases * l.share
FROM base b JOIN l ON l.version_id = b.version_id AND l.link_id = b.link_id AND l.from_material = b.from_material
UNION ALL
SELECT b.version_id, b.link_id, 7, l.to_material, b.ship_to_code, b.account_code, b.week_id, 'uplift', b.cases * l.share * l.uplift_pct / 100
FROM base b JOIN l ON l.version_id = b.version_id AND l.link_id = b.link_id AND l.from_material = b.from_material
WHERE COALESCE(l.uplift_pct, 0) <> 0
