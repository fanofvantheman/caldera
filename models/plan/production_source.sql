/* Where each plant's requirement comes from (DEC-20261117-02 point 7): the DCs' receipts by the share of the sourcing
   rule, by version × material × plant × DC × period. Read at the period the receipt lands; every lane Caldera holds is
   under a week, so it is also the period it is sent. */
MODEL (name plan.production_source, kind FULL, grain (version_id, material_code, plant_code, node_code, period));
SELECT f.version_id, f.material_code, s.plant_code, f.node_code, f.period, f.receipt * s.share AS cases
FROM plan.inventory_flow f JOIN plan.sourcing_rule s ON s.node_code = f.node_code AND s.material_code = f.material_code
WHERE f.node_kind <> 'plant' AND f.receipt > 0
