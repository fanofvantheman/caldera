/* Ship-to points: the leaf of the demand plan — the customer's receiving locations, not nodes of our network.
   Each is served from one of our nodes by a lane. */
MODEL (name dims.dim_ship_to, kind FULL, grain (ship_to_code), audits (ship_to_account_exists, ship_to_serving_node_exists));
SELECT s.ship_to_code::TEXT AS ship_to_code, s.account_code::TEXT AS account_code, s.ship_to_name::TEXT AS ship_to_name,
       s.state::TEXT AS state, s.serving_node::TEXT AS serving_node, s.stores_served::INT AS stores_served,
       a.account_code IS NOT NULL AS account_exists, n.node_code IS NOT NULL AS serving_node_exists
FROM bronze.dim_ship_to s
LEFT JOIN bronze.dim_account a ON a.account_code = s.account_code
LEFT JOIN bronze.dim_node n ON n.node_code = s.serving_node
