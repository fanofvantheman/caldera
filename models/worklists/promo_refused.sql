/* Events refused at the door they came through, with the reason: a sender's event for an account whose promotions are
   entered in the plan goes back to the sender; an event typed at an account the sender masters is not the plan's to
   enter. Refused events stay on file and out of the calendar. Routed to trade marketing. */
MODEL (name plan.worklist_promo_refused, kind FULL, grain (version_id, event_id));
WITH readers AS (SELECT STRING_AGG(DISTINCT principal, ', ') AS whose FROM dims.effective_entitlements WHERE action = 'register.promo_calendar.maintain')
SELECT x.event_id, x.version_id, x.source, x.account_code, x.local_account, x.window_start, x.window_end, x.refused_because,
       x.event_id || ' from the ' || x.source || ': ' || x.refused_because AS item, r.whose
FROM (
  SELECT event_id, version_id, 'sender' AS source, account_code, local_account, window_start, window_end, refused_because
  FROM plan.promo_sender_event WHERE state = 'refused'
  UNION ALL
  SELECT event_id, version_id, 'plan', account_code, NULL, window_start, window_end, refused_because
  FROM plan.promo_typed_event WHERE state = 'refused'
) x CROSS JOIN readers r
