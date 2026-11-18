/* The override points (DEC-20261119-01 point 2): where the model lets a person's figure replace the calculated one. A
   figure is calculated unless an override stands on it; an override is typed with a reason, the calculated figure kept
   beside it, and is the only thing a port carries — from a sandbox into its Plan, or from one Plan into the next for the
   periods still planned (point 4). Each point names its stage, the figure it replaces, the register its acts are kept in
   (the latest act per cell stands; a withdrawal names an act), the cell, the figures typed and the right that types it.
   `ports` says whether the port carries it in this build; where it does not, `port_says` says why.
   Not an override point: a demand layer entry (a delta on a layer of the stack, not a figure that replaces one), and the
   opex schedule's typed month (an adjustment on top of its driver — a difference). */
MODEL (name dims.ref_override_point, kind FULL, grain point);
SELECT * FROM (VALUES
  (1, 'production', 'production', 'Cases to make',
   'the proposed quantity — the plant''s replenishment to its target', 'reg_production_act', 'plan.production_act',
   'material_code,plant_code,period', 'quantity', 'delta.supply.enter', 'Supply → Supply plan', TRUE, NULL),
  (2, 'purchase', 'materials', 'A key material''s purchase — quantity or price',
   'the calculated purchase: the requirement less the stock, at the source''s price', 'reg_purchase_act', 'plan.purchase_act',
   'input_code,plant_code,period', 'quantity,price', 'register.supply_plan.maintain', 'Supply → Material purchases', TRUE, NULL),
  (3, 'unit_cost', 'cost', 'A component of the planned unit cost, per case',
   'the figure its drivers make', 'reg_unit_cost_act', 'plan.unit_cost_act',
   'material_code,plant_code,period,component', 'per_case', 'overlay.finance.enter', 'Cost of goods → Standard by plant → Typed', TRUE, NULL),
  (4, 'finance', 'finance', 'Finance''s volume or price, at a node',
   'the demand plan''s figure beneath it', 'reg_finance_overlay', 'plan.finance_edit',
   'scope_customer,scope_material,period,measure', 'value', 'overlay.finance.enter', 'Revenue → Volume · Price', FALSE,
   'not yet: a figure typed at a node is written down by the Plan''s own shape, so it ports by typing it again on the receiving Plan through the grid'),
  (5, 'schedule_lock', 'finance', 'An opex month locked at a figure',
   'driver × rate', 'reg_schedule_edit', 'plan.schedule_edit',
   'entity_code,cost_centre_code,account_code,period', 'value', 'schedule.line.enter', 'Opex → Schedule', FALSE,
   'not yet: a lock is one act of the schedule''s save, ported with the save it belongs to')
) AS t (ord, point, stage, point_name, replaces, register, act_model, cell, figures, verb, typed_on, ports, port_says)
