/* The ledgers' actuals read at the plan's cost centre: each row through the mapping in force at its period's start, the
   entity and the ledger's own code kept beneath. `state` says where it stands — mapped, unmapped (waiting on the
   ledgers' queue, not in the plan) or left out (decided, with a reason). Nothing is dropped. */
MODEL (name plan.cost_actual, kind FULL, grain (entity_code, ledger_cost_centre, account_code, period));
SELECT a.entity_code, a.ledger_cost_centre, l.ledger_name, a.account_code, g.account_name, g.cost_family, g.is_labour,
       a.period, p.fiscal_year, p.fiscal_period, a.amount,
       m.cost_centre_code, pc.cost_centre_name, pc.is_factory,
       CASE WHEN m.ledger_cost_centre IS NULL THEN 'unmapped' WHEN m.cost_centre_code IS NULL THEN 'left_out' ELSE 'mapped' END AS state
FROM history.cost_actual a
JOIN dims.dim_period p ON p.period = a.period
LEFT JOIN dims.dim_ledger_cost_centre l ON l.entity_code = a.entity_code AND l.ledger_cost_centre = a.ledger_cost_centre
LEFT JOIN dims.dim_gl_account g ON g.account_code = a.account_code
LEFT JOIN plan.cost_centre_map m ON m.entity_code = a.entity_code AND m.ledger_cost_centre = a.ledger_cost_centre
      AND p.period_start >= m.valid_from AND (m.valid_to IS NULL OR p.period_start <= m.valid_to)
LEFT JOIN plan.planning_cost_centre pc ON pc.cost_centre_code = m.cost_centre_code
