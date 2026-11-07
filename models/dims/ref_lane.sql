/* Lanes: from one of our nodes to another node or to a customer ship-to — mode, transit time, cost per pallet. */
MODEL (name dims.ref_lane, kind FULL, grain (from_node, to_code), audits (lane_endpoints_known));
SELECT l.from_node::TEXT AS from_node, l.to_code::TEXT AS to_code, l.to_kind::TEXT AS to_kind, l.mode::TEXT AS mode,
       l.transit_days::INT AS transit_days, l.cost_per_pallet::DOUBLE AS cost_per_pallet,
       f.node_code IS NOT NULL AND (n.node_code IS NOT NULL OR s.ship_to_code IS NOT NULL) AS endpoints_known
FROM bronze.ref_lane l
LEFT JOIN bronze.dim_node f ON f.node_code = l.from_node
LEFT JOIN bronze.dim_node n ON n.node_code = l.to_code AND l.to_kind = 'node'
LEFT JOIN bronze.dim_ship_to s ON s.ship_to_code = l.to_code AND l.to_kind = 'ship_to'
