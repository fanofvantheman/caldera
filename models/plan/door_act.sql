/* Every door's decisions, in one log register: one row per act — a person's decision on an item, or a proposal (the
   promotions mapping tool's first pass) waiting for a person. The latest act per door × kind × item × scope is the one
   that stands, for this arrival and every later one, until someone acts again; a proposal never stands. */
MODEL (name plan.door_act, kind FULL, grain (door, kind, item_code, scope_code), depends_on (plan.ref_door_resolution), audits (door_act_vocabulary));
WITH acts AS (
  SELECT r.*, ROW_NUMBER() OVER (PARTITION BY r.door, r.kind, r.item_code, COALESCE(NULLIF(r.scope_code, ''), 'ALL')
                                 ORDER BY r.acted_at DESC, r.source_file DESC, r.file_row_number DESC) AS recency,
         COUNT(*) OVER (PARTITION BY r.door, r.kind, r.item_code, COALESCE(NULLIF(r.scope_code, ''), 'ALL')) AS acts
  FROM bronze.reg_door_act r
)
SELECT a.act_id::TEXT AS act_id, a.door::TEXT AS door, a.kind::TEXT AS kind, a.item_code::TEXT AS item_code,
       COALESCE(NULLIF(a.scope_code::TEXT, ''), 'ALL') AS scope_code, a.resolution::TEXT AS resolution,
       NULLIF(a.target_code::TEXT, '') AS target_code, a.state::TEXT AS state, a.origin::TEXT AS origin,
       NULLIF(a.confidence::TEXT, '') AS confidence, NULLIF(a.rationale::TEXT, '') AS rationale,
       NULLIF(a.item_description::TEXT, '') AS item_description, NULLIF(a.reason::TEXT, '') AS reason,
       a.acted_by::TEXT AS acted_by, a.acted_at::TIMESTAMP AS acted_at, a.acts, a.state = 'decided' AS in_force
FROM acts a WHERE a.recency = 1
