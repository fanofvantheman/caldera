/* Our network's nodes — plant, DC, cross-dock — with roles, ownership and status. Customer ship-tos are not nodes. */
MODEL (name dims.dim_node, kind FULL, grain (node_code));
SELECT node_code::TEXT AS node_code, node_name::TEXT AS node_name, node_kind::TEXT AS node_kind, roles::TEXT AS roles,
       roles LIKE '%make%' AS can_make, roles LIKE '%store%' AS can_store, roles LIKE '%ship%' AS can_ship,
       ownership::TEXT AS ownership, state::TEXT AS state, status::TEXT AS status
FROM bronze.dim_node
