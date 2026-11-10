/* An event's status words, and which of them put the event in the calendar: agreed or later enters; proposed is a
   candidate that never touches the plan; cancelled removes. */
MODEL (name dims.ref_promo_status, kind FULL, grain (status));
SELECT status::TEXT AS status, status_name::TEXT AS status_name, enters_calendar::TEXT = 'Y' AS enters_calendar
FROM bronze.ref_promo_status
