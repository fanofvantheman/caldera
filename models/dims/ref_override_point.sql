/* The override points (DEC-20261119-01 point 2): where the model lets a person's figure replace the calculated one. A
   figure is calculated unless an override stands on it; an override is typed with a reason, the calculated figure kept
   beside it, and is the only thing a port carries — from a sandbox into its Plan, or from one Plan into the next for the
   periods still planned (point 4). Each point names its stage, the figure it replaces, the register its acts are kept in
   (the latest act per cell stands; a withdrawal names an act), the cell, the figures typed and the right that types it.
   `ports` says whether the port carries it in this build; where it does not, `port_says` says why.
   Not an override point: a demand layer entry (a delta on a layer of the stack, not a figure that replaces one), and the
   opex schedule's typed month (an adjustment on top of its driver — a difference).
   A second kind, the **driver** (DEC-20261119-03): a row a calculation reads that the models cannot derive — a promotion
   typed here, a launch, a supersession link, an amended assumption. Demand is never ported; what it is calculated from is,
   as the row whole, a different row under the same key on the receiving Plan a clash. A judgement adjustment on a demand
   layer is neither kind and is not here. What identifies each row and which rows stand is the face's per-point query. */
MODEL (name dims.ref_override_point, kind FULL, grain point);
SELECT * REPLACE (port_says::TEXT AS port_says) FROM (VALUES
  (1, 'production', 'production', 'Cases to make',
   'the proposed quantity — the plant''s replenishment to its target', 'reg_production_act', 'plan.production_act',
   'material_code,plant_code,period', 'quantity', 'delta.supply.enter', 'Supply → Supply plan', TRUE, NULL, 'override'),
  (2, 'purchase', 'materials', 'A key material''s purchase — quantity or price',
   'the calculated purchase: the requirement less the stock, at the source''s price', 'reg_purchase_act', 'plan.purchase_act',
   'input_code,plant_code,period', 'quantity,price', 'register.supply_plan.maintain', 'Supply → Material purchases', TRUE, NULL, 'override'),
  (3, 'unit_cost', 'cost', 'A component of the planned unit cost, per case',
   'the figure its drivers make', 'reg_unit_cost_act', 'plan.unit_cost_act',
   'material_code,plant_code,period,component', 'per_case', 'overlay.finance.enter', 'Cost of goods → Standard by plant → Typed', TRUE, NULL, 'override'),
  (4, 'finance', 'finance', 'Finance''s volume or price, at a node',
   'the demand plan''s figure beneath it', 'reg_finance_overlay', 'plan.finance_edit',
   'scope_customer,scope_material,period,measure', 'value', 'overlay.finance.enter', 'Revenue → Volume · Price', TRUE,
   NULL, 'override'),
  (5, 'schedule_lock', 'finance', 'An opex month locked at a figure',
   'driver × rate', 'reg_schedule_edit', 'plan.schedule_edit',
   'entity_code,cost_centre_code,account_code,period', 'value', 'schedule.line.enter', 'Opex → Schedule', TRUE,
   NULL, 'override'),
  (6, 'promotion', 'demand', 'A promotion typed here',
   'nothing — an event the demand plan reads', 'reg_promo_event', 'plan.promo_typed_event',
   'event_id', 'account_code,promo_group_code,window_start,window_end,mechanic,uplift_pct,dip_pct,tpr_per_case,scan_funding_per_case,fixed_fee,media_fee,envelope_drawdown,status',
   'register.promo_calendar.maintain', 'Demand → Promotions → Events', TRUE, NULL, 'driver'),
  (7, 'launch', 'demand', 'A launch — an entry on the innovation layer',
   'nothing — a line the demand plan reads', 'layer_entry', 'plan.layer_entry',
   'scope_material,scope_customer,effect_type,period_from,period_to', 'value_kind,value,spread_rule',
   'layer.7.enter', 'Demand → Launches', TRUE, NULL, 'driver'),
  (8, 'supersession', 'demand', 'A supersession link',
   'nothing — a link the baseline reads', 'reg_supersession', 'plan.supersession_link',
   'link_id', 'kind,from_material,to_material,share,uplift_pct,switch,switch_week,end_week,accounts',
   'layer.7.enter', 'Demand → Launches → Supersession', TRUE, NULL, 'driver'),
  (9, 'assumption', 'valuation', 'An amended assumption',
   'nothing — a value from a period the valuation reads', 'reg_assumption_amend', 'plan.assumption_in_force',
   'assumption_code,valid_from', 'value', 'register.assumptions.maintain', 'Set-up → Assumptions', TRUE, NULL, 'driver')
) AS t (ord, point, stage, point_name, replaces, register, act_model, cell, figures, verb, typed_on, ports, port_says, kind)
