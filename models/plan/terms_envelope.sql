/* Each account's co-op envelope as the agreement reads it: the amount committed for its year, what the events in the
   calendar draw from it in that year, and what remains. The money is counted once, at the event (its drawdown is a
   lump sum on the event in the gross-to-net); the envelope itself values nothing. An envelope drawn beyond its amount
   reads negative remaining, and is listed so. */
MODEL (name plan.terms_envelope, kind FULL, grain (version_id, instrument_code, valid_from));
WITH env AS (SELECT * FROM plan.terms WHERE instrument_kind = 'coop_envelope'),
drawn AS (
  SELECT e.version_id, v.instrument_code, v.valid_from, SUM(e.envelope_drawdown) AS drawn, COUNT(*) AS events,
         STRING_AGG(e.event_id || ' ' || format('{:,.0f}', e.envelope_drawdown), '; ' ORDER BY e.window_start) AS drawn_by
  FROM plan.promo_event e
  JOIN env v ON v.account_code = e.account_code AND e.window_start >= v.valid_from AND (v.valid_to IS NULL OR e.window_start <= v.valid_to)
  WHERE e.envelope_drawdown > 0
  GROUP BY ALL
),
versions AS (SELECT version_id FROM dims.ctl_version WHERE version_kind <> 'actual')
SELECT x.version_id, v.instrument_code, v.account_code, v.valid_from, v.valid_to, v.rate AS committed, COALESCE(d.drawn, 0) AS drawn,
       v.rate - COALESCE(d.drawn, 0) AS remaining, COALESCE(d.events, 0) AS events, d.drawn_by
FROM env v CROSS JOIN versions x
LEFT JOIN drawn d ON d.version_id = x.version_id AND d.instrument_code = v.instrument_code AND d.valid_from = v.valid_from
