/* The production requirement (DEC-20261117-02 point 4): each plant's cases to make by material × period — its
   replenishment of the DCs it supplies, less its own finished stock, on its own order-up-to target (plan.inventory_flow)
   — not sequenced against the lines: whether they can make it is the capacity reading's question. `proposed` is what the
   flow asks; `quantity` what stands, a typed figure where the supply plan's owner typed one (plan.production_act).
   What the materials stage and storage read. */
MODEL (name plan.production_requirement, kind FULL, grain (version_id, material_code, plant_code, period));
SELECT f.version_id, f.material_code, f.node_code AS plant_code, f.period, f.fiscal_year, f.proposed, f.receipt AS quantity, f.typed,
       f.demand AS shipped_to_dcs, f.closing AS finished_stock, f.safety_stock, a.act_id, a.reason, a.entered_by
FROM plan.inventory_flow f
LEFT JOIN plan.production_act a ON a.version_id = f.version_id AND a.material_code = f.material_code AND a.plant_code = f.node_code AND a.period = f.period
WHERE f.node_kind = 'plant'
