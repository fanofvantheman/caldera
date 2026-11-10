/* Every event the promotions sender has on file, resolved through the mapping: the latest send of each event id within
   the version replaces the earlier ones, its codes beside what they map to, its funding package folded onto the
   event's three priced columns, and its state —
     in         every code mapped and in force, status agreed or later, the account mastered by the sender: in the calendar
     held       a code with no mapping, or a proposal not yet reviewed, or the status still proposed: out of the calendar,
                listed with what it waits for; it enters on the first run after the wait is over
     refused    the account's promotions are mastered in the plan, or the window is reversed or outside the version's
                horizon: returned to the sender with the reason
     cancelled  the sender cancelled it: removed */
MODEL (name plan.promo_sender_event, kind FULL, grain (version_id, event_id));
WITH latest AS (
  SELECT * FROM (SELECT e.*, ROW_NUMBER() OVER (PARTITION BY e.version_id, e.event_id ORDER BY e.taken_in_at DESC, e.source_file DESC, e.file_row_number DESC) AS r,
                        COUNT(*) OVER (PARTITION BY e.version_id, e.event_id) AS sends
                 FROM bronze.tpm_event e) WHERE r = 1
),
fund AS (
  SELECT version_id, event_id,
         SUM(CASE WHEN priced AND event_column = 'tpr_per_case' THEN rate ELSE 0 END) AS tpr_per_case,
         SUM(CASE WHEN priced AND event_column = 'scan_funding_per_case' THEN rate ELSE 0 END) AS scan_funding_per_case,
         SUM(CASE WHEN priced AND event_column = 'fixed_fee' THEN rate ELSE 0 END) AS fixed_fee,
         STRING_AGG(CASE WHEN mapping_in_force AND NOT priced THEN funding_type || ' ' || format('{:,.0f}', rate) || CASE rate_basis WHEN 'LUMP' THEN ' lump sum' ELSE ' per case' END END, '; ' ORDER BY line_no) AS unpriced_funding,
         STRING_AGG(CASE WHEN NOT mapping_in_force THEN 'fund type ' || local_fund_type || CASE WHEN review_state = 'proposed' THEN ' (proposed, not reviewed)' ELSE ' (not mapped)' END END, '; ' ORDER BY line_no) AS fund_waits,
         STRING_AGG(local_fund_type, ' + ' ORDER BY line_no) AS local_fund_types
  FROM plan.promo_funding GROUP BY ALL
),
resolved AS (
  SELECT l.*, ca.target_code AS account_code, ma.target_code AS promo_group_code, me.target_code AS mechanic, st.target_code AS mapped_status,
         ca.in_force AS customer_ok, ma.in_force AS material_ok, me.in_force AS mechanic_ok, st.in_force AS status_ok,
         ca.review_state AS customer_state, ma.review_state AS material_state, me.review_state AS mechanic_state, st.review_state AS status_state
  FROM latest l
  LEFT JOIN plan.promo_mapping ca ON ca.sender = l.sender AND ca.subject = 'customer' AND ca.local_code = l.planning_account
  LEFT JOIN plan.promo_mapping ma ON ma.sender = l.sender AND ma.subject = 'material' AND ma.local_code = l.product_group
  LEFT JOIN plan.promo_mapping me ON me.sender = l.sender AND me.subject = 'mechanic' AND me.local_code = l.tactic
  LEFT JOIN plan.promo_mapping st ON st.sender = l.sender AND st.subject = 'status' AND st.local_code = l.status
),
judged AS (
  SELECT r.*, f.tpr_per_case, f.scan_funding_per_case, f.fixed_fee, f.unpriced_funding, f.local_fund_types,
         a.promotions_master, rs.enters_calendar,
         CONCAT_WS('; ',
           CASE WHEN NOT COALESCE(r.customer_ok, FALSE) THEN 'planning account ' || r.planning_account || CASE WHEN r.customer_state = 'proposed' THEN ' (proposed, not reviewed)' ELSE ' (not mapped)' END END,
           CASE WHEN NOT COALESCE(r.material_ok, FALSE) THEN 'product group ' || r.product_group || CASE WHEN r.material_state = 'proposed' THEN ' (proposed, not reviewed)' ELSE ' (not mapped)' END END,
           CASE WHEN NOT COALESCE(r.mechanic_ok, FALSE) THEN 'tactic ' || r.tactic || CASE WHEN r.mechanic_state = 'proposed' THEN ' (proposed, not reviewed)' ELSE ' (not mapped)' END END,
           CASE WHEN NOT COALESCE(r.status_ok, FALSE) THEN 'status ' || r.status || CASE WHEN r.status_state = 'proposed' THEN ' (proposed, not reviewed)' ELSE ' (not mapped)' END END,
           f.fund_waits) AS mapping_waits,
         v.version_id IS NOT NULL AND r.shopper_end::DATE >= r.shopper_start::DATE
           AND r.shopper_start::DATE >= (SELECT MIN(week_start) FROM dims.dim_week w WHERE w.period = v.horizon_start)
           AND r.shopper_end::DATE <= (SELECT MAX(week_end) FROM dims.dim_week w WHERE w.period = v.horizon_end) AS window_resolves
  FROM resolved r
  LEFT JOIN fund f ON f.version_id = r.version_id AND f.event_id = r.event_id
  LEFT JOIN dims.dim_account a ON a.account_code = r.account_code
  LEFT JOIN dims.ref_promo_status rs ON rs.status = r.mapped_status
  LEFT JOIN dims.ctl_version v ON v.version_id = r.version_id
)
SELECT j.event_id::TEXT AS event_id, j.version_id::TEXT AS version_id, j.sender::TEXT AS sender, j.sender_file::TEXT AS sender_file,
       j.taken_in_at::TEXT AS taken_in_at, j.sends, j.account_code, j.promo_group_code, j.mechanic, j.mapped_status AS status,
       j.planning_account::TEXT AS local_account, j.planning_account_name::TEXT AS local_account_name,
       j.product_group::TEXT AS local_product_group, j.product_group_name::TEXT AS local_product_group_name,
       j.tactic::TEXT AS local_tactic, j.tactic_name::TEXT AS local_tactic_name, j.status::TEXT AS local_status, j.local_fund_types,
       j.shopper_start::DATE AS window_start, j.shopper_end::DATE AS window_end, j.uplift_pct::DOUBLE AS uplift_pct, j.dip_pct::DOUBLE AS dip_pct,
       COALESCE(j.tpr_per_case, 0) AS tpr_per_case, COALESCE(j.scan_funding_per_case, 0) AS scan_funding_per_case, COALESCE(j.fixed_fee, 0) AS fixed_fee,
       j.unpriced_funding, NULLIF(j.baseline_version::TEXT, '') AS baseline_version, j.promotions_master,
       CASE WHEN j.mapping_waits = '' AND j.mapped_status = 'cancelled' THEN 'cancelled'
            WHEN j.mapping_waits = '' AND j.promotions_master = 'PLAN' THEN 'refused'
            WHEN j.mapping_waits = '' AND NOT j.window_resolves THEN 'refused'
            WHEN j.mapping_waits <> '' OR NOT j.enters_calendar THEN 'held'
            ELSE 'in' END AS state,
       NULLIF(CONCAT_WS('; ', NULLIF(j.mapping_waits, ''),
                        CASE WHEN j.mapping_waits = '' AND j.mapped_status = 'proposed' THEN 'status proposed: a candidate until the sender sends it agreed' END), '') AS waits_for,
       CASE WHEN j.mapping_waits = '' AND j.mapped_status <> 'cancelled' AND j.promotions_master = 'PLAN'
              THEN 'returned to the sender: ' || j.account_code || ' promotions are entered in the plan, not sent'
            WHEN j.mapping_waits = '' AND j.mapped_status <> 'cancelled' AND NOT j.window_resolves
              THEN 'returned to the sender: the window is reversed or outside the version''s horizon' END AS refused_because
FROM judged j
