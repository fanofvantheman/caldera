/* The events typed in the plan, for the accounts whose promotions are mastered here: the header as entered — account,
   promo group, window, mechanic, the price reduction per case, scan funding per case, fixed fee, status — and the
   response the plan supplies: uplift and dip from the mechanic register unless the person overrode them, with a note.
   An event typed at an account the sender masters is refused; the face refuses it before it is placed, and the run
   refuses any that arrives another way. */
MODEL (name plan.promo_typed_event, kind FULL, grain (event_id));
SELECT e.event_id::TEXT AS event_id, e.version_id::TEXT AS version_id, e.account_code::TEXT AS account_code, e.promo_group_code::TEXT AS promo_group_code,
       e.window_start::DATE AS window_start, e.window_end::DATE AS window_end, e.mechanic::TEXT AS mechanic,
       COALESCE(e.uplift_pct::DOUBLE, m.default_uplift_pct) AS uplift_pct, COALESCE(e.dip_pct::DOUBLE, m.default_dip_pct) AS dip_pct,
       CASE WHEN e.uplift_pct IS NULL AND e.dip_pct IS NULL THEN 'mechanic default' ELSE 'entered' END AS response_source,
       COALESCE(e.tpr_per_case::DOUBLE, 0) AS tpr_per_case, COALESCE(e.scan_funding_per_case::DOUBLE, 0) AS scan_funding_per_case,
       COALESCE(e.fixed_fee::DOUBLE, 0) AS fixed_fee, e.status::TEXT AS status, e.owner::TEXT AS owner, e.baseline_version::TEXT AS baseline_version,
       NULLIF(e.note::TEXT, '') AS note, e.entered_on::TEXT AS entered_on, a.promotions_master,
       CASE WHEN a.promotions_master = 'TPM' THEN 'refused'
            WHEN NOT COALESCE(s.enters_calendar, FALSE) THEN 'held'
            ELSE 'in' END AS state,
       CASE WHEN a.promotions_master = 'TPM' THEN e.account_code || ' promotions come from the promotions system; enter them there' END AS refused_because
FROM bronze.reg_promo_event e
LEFT JOIN dims.ref_mechanic m ON m.mechanic = e.mechanic
LEFT JOIN dims.dim_account a ON a.account_code = e.account_code
LEFT JOIN dims.ref_promo_status s ON s.status = e.status
