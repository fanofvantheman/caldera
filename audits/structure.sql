AUDIT (name hierarchy_every_member_reaches_root);
/* blocking: a member that cannot reach the root is volume or money no total ever sees */
SELECT DISTINCT descendant_code FROM @this_model WHERE NOT reaches_root;

AUDIT (name week_in_one_period);
/* blocking: a week in two periods, or a period with no weeks, breaks every accrual */
SELECT week_id, COUNT(DISTINCT period) AS periods FROM @this_model GROUP BY week_id HAVING COUNT(DISTINCT period) <> 1;

AUDIT (name period_single_open);
/* blocking: exactly one open period, or nothing is current */
SELECT COUNT(*) AS open_periods FROM @this_model WHERE period_state = 'OPEN' HAVING COUNT(*) <> 1;

AUDIT (name version_vocabulary);
SELECT version_id, version_kind, status FROM @this_model
WHERE version_kind NOT IN ('actual', 'business_plan', 'latest_view', 'scenario') OR status NOT IN ('open', 'frozen', 'closed', 'retired');

AUDIT (name material_product_exists);
SELECT material_code FROM @this_model WHERE NOT product_exists;

AUDIT (name bom_component_known);
SELECT parent_material, component_material FROM @this_model WHERE NOT component_known;

AUDIT (name ship_to_account_exists);
SELECT ship_to_code FROM @this_model WHERE NOT account_exists;

AUDIT (name ship_to_serving_node_exists);
SELECT ship_to_code, serving_node FROM @this_model WHERE NOT serving_node_exists;

AUDIT (name line_area_exists);
SELECT line_code FROM @this_model WHERE NOT area_exists;

AUDIT (name lane_endpoints_known);
SELECT from_node, to_code FROM @this_model WHERE NOT endpoints_known;

AUDIT (name route_line_exists);
SELECT route_code, line_code FROM @this_model WHERE NOT line_exists;

AUDIT (name route_material_exists);
SELECT route_code, material_code FROM @this_model WHERE NOT material_exists;

AUDIT (name capacity_line_exists);
SELECT line_code, period FROM @this_model WHERE NOT line_exists;
