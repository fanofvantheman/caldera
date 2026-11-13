/* The plan's cost centres: the organisation's (dims.dim_cost_centre), and any opened from the ledgers' queue —
   provisional, under the company, carrying the ledger centre's code and name until the organisation places it. */
MODEL (name plan.planning_cost_centre, kind FULL, grain (cost_centre_code));
SELECT c.cost_centre_code, c.cost_centre_name, c.parent_code, c.kind, c.is_factory, FALSE AS provisional
FROM dims.dim_cost_centre c
UNION ALL
SELECT m.ledger_cost_centre, ANY_VALUE(l.ledger_name), (SELECT cost_centre_code FROM dims.dim_cost_centre WHERE parent_code IS NULL LIMIT 1),
       'overhead', FALSE, TRUE
FROM plan.cost_centre_map m JOIN dims.dim_ledger_cost_centre l ON l.entity_code = m.entity_code AND l.ledger_cost_centre = m.ledger_cost_centre
WHERE m.how = 'open_new' AND m.ledger_cost_centre NOT IN (SELECT cost_centre_code FROM dims.dim_cost_centre)
GROUP BY m.ledger_cost_centre
