/* The first sourcing rule (DEC-20261117-02 point 1): each ship-to's serving node — a stocking DC, or a plant for a
   direct-ship customer. Read from the ship-to as loaded and checked against the lanes the build holds: a ship-to whose
   serving node has no lane to it is marked. Caldera serves every ship-to from a DC; no customer is served direct. */
MODEL (name dims.ref_serving_node, kind FULL, grain ship_to_code);
SELECT s.ship_to_code, s.account_code, s.serving_node AS node_code, l.transit_days, l.mode, l.from_node IS NOT NULL AS lane_known
FROM dims.dim_ship_to s
LEFT JOIN dims.ref_lane l ON l.from_node = s.serving_node AND l.to_code = s.ship_to_code AND l.to_kind = 'ship_to'
