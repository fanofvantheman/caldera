/* Every item of the capital plan as entered — a project, a sustaining rate, a lease — on a version, in the order entered.
   The latest row of an item on a version stands (an amendment is a later row); a withdrawal is a later row naming an act
   or an item, and what it names stays on record here. Planned, not approved: there is no gate (DEC-20261115-01). */
MODEL (name plan.capex_item, kind FULL, grain (act_id));
WITH rows_ AS (
  SELECT act_id::TEXT AS act_id, COALESCE(NULLIF(action::TEXT, ''), 'enter') AS action, NULLIF(withdraws::TEXT, '') AS withdraws,
         version_id::TEXT AS version_id, kind::TEXT AS kind, item_id::TEXT AS item_id, item_name::TEXT AS item_name,
         NULLIF(project_kind::TEXT, '') AS project_kind, NULLIF(asset_class::TEXT, '') AS asset_class, entity_code::TEXT AS entity_code,
         cost_centre_code::TEXT AS cost_centre_code, NULLIF(plant_code::TEXT, '') AS plant_code, spend::DOUBLE AS spend,
         NULLIF(spend_from::TEXT, '') AS spend_from, NULLIF(spend_to::TEXT, '') AS spend_to, NULLIF(in_service_period::TEXT, '') AS in_service_period,
         life_years::DOUBLE AS life_years, lifetime_units::DOUBLE AS lifetime_units, rate::DOUBLE AS rate, lease_charge::DOUBLE AS lease_charge,
         NULLIF(lease_to_period::TEXT, '') AS lease_to_period, NULLIF(tier::TEXT, '') AS tier, NULLIF(note::TEXT, '') AS note,
         entered_by::TEXT AS entered_by, entered_on::TIMESTAMP AS entered_on, NULLIF(copied_from::TEXT, '') AS copied_from,
         source_file::TEXT AS source_file, file_row_number AS file_row_number
  FROM bronze.reg_capex
),
withdrawn AS (SELECT version_id, withdraws, ANY_VALUE(act_id) AS by_act, ANY_VALUE(entered_by) AS by_who FROM rows_ WHERE action = 'withdraw' GROUP BY ALL),
latest AS (SELECT act_id, ROW_NUMBER() OVER (PARTITION BY version_id, item_id ORDER BY entered_on DESC, source_file DESC, file_row_number DESC) AS rn
           FROM rows_ WHERE action <> 'withdraw')
SELECT r.* EXCLUDE (source_file, file_row_number), r.source_file,
       CASE WHEN r.action = 'withdraw' THEN 'withdrawal'
            WHEN w.by_act IS NOT NULL THEN 'withdrawn'
            WHEN l.rn = 1 THEN 'stands' ELSE 'amended' END AS standing,
       w.by_act AS withdrawn_by_act, w.by_who AS withdrawn_by
FROM rows_ r
LEFT JOIN latest l USING (act_id)
LEFT JOIN withdrawn w ON w.version_id = r.version_id AND w.withdraws IN (r.act_id, r.item_id)
