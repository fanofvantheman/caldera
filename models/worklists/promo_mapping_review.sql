/* The sender's codes waiting for a person: every code an event on file uses whose mapping is a first-pass proposal not
   yet reviewed, or that has no mapping at all (the first pass did not run, or could not place it). Lowest confidence
   first; each row says how many events it holds. Routed to those who review the mapping and keep the calendar. */
MODEL (name plan.worklist_promo_mapping_review, kind FULL, grain (sender, subject, local_code));
WITH used AS (
  SELECT sender, 'customer' AS subject, local_account AS local_code, local_account_name AS local_description, event_id FROM plan.promo_sender_event WHERE state <> 'cancelled'
  UNION ALL SELECT sender, 'material', local_product_group, local_product_group_name, event_id FROM plan.promo_sender_event WHERE state <> 'cancelled'
  UNION ALL SELECT sender, 'mechanic', local_tactic, local_tactic_name, event_id FROM plan.promo_sender_event WHERE state <> 'cancelled'
  UNION ALL SELECT sender, 'status', local_status, local_status, event_id FROM plan.promo_sender_event
  UNION ALL SELECT sender, 'funding_type', local_fund_type, local_fund_type_name, event_id FROM plan.promo_funding
),
codes AS (
  SELECT sender, subject, local_code, ANY_VALUE(local_description) AS local_description, COUNT(DISTINCT event_id) AS events
  FROM used GROUP BY ALL
),
readers AS (SELECT STRING_AGG(DISTINCT principal, ', ') AS whose FROM dims.effective_entitlements
            WHERE action = 'register.promo_calendar.maintain' AND principal IN (SELECT principal FROM dims.effective_entitlements WHERE action = 'mapping.accept'))
SELECT c.sender, c.subject, c.local_code, c.local_description, c.events,
       COALESCE(m.review_state, 'missing') AS review_state, m.target_code AS proposed_target, m.target_name AS proposed_target_name,
       m.confidence, m.rationale, m.origin,
       CASE m.confidence WHEN 'low' THEN 0 WHEN 'medium' THEN 1 WHEN 'high' THEN 2 ELSE -1 END AS confidence_rank,
       c.subject || ' ' || c.local_code || ' (' || COALESCE(c.local_description, '') || ') — ' ||
         CASE WHEN m.review_state = 'proposed' THEN 'proposed ' || m.target_code || ', ' || COALESCE(m.confidence, '?') || ' confidence' ELSE 'not mapped' END ||
         ', holds ' || c.events || ' event' || CASE WHEN c.events = 1 THEN '' ELSE 's' END AS item,
       r.whose
FROM codes c
LEFT JOIN plan.promo_mapping m ON m.sender = c.sender AND m.subject = c.subject AND m.local_code = c.local_code
CROSS JOIN readers r
WHERE m.local_code IS NULL OR NOT m.in_force
