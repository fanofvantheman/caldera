/* The ledgers' queue: a ledger cost centre with actuals and no planning cost centre in force — its actuals wait outside
   the plan, with what they would bring over the last twelve closed periods. One item per entity × ledger cost centre;
   decided once on the cost centres page (map to one of ours · open a new one · leave out), the decision logged in the
   doors' one register and standing until someone acts again. The first columns are the doors' queue contract (door GL). */
MODEL (name plan.worklist_cost_centre_unmapped, kind FULL, grain (item_code, scope_code));
WITH yr AS (SELECT period FROM dims.dim_period WHERE period_state = 'CLOSED' ORDER BY period DESC LIMIT 12),
w AS (
  SELECT a.entity_code, a.ledger_cost_centre, ANY_VALUE(a.ledger_name) AS ledger_name, MIN(a.period) AS since,
         SUM(CASE WHEN a.period IN (SELECT period FROM yr) THEN a.amount ELSE 0 END) AS year_amount, COUNT(DISTINCT a.account_code) AS accounts
  FROM plan.cost_actual a WHERE a.state = 'unmapped' GROUP BY ALL
)
SELECT 'GL' AS door, 'unmapped_cost_centre' AS kind, w.ledger_cost_centre AS item_code, w.entity_code AS scope_code, '' AS reaches,
       w.ledger_name || ' · ' || e.entity_name AS description,
       'in the ' || e.ledger || ' since ' || w.since || ', ' || w.accounts || ' account' || CASE WHEN w.accounts = 1 THEN '' ELSE 's' END AS as_sent,
       FORMAT('${:,} over the last twelve closed periods', ROUND(w.year_amount)::BIGINT) AS would_bring,
       'its actuals are outside the plan' AS meanwhile, NULL::TEXT AS proposed_target, NULL::TEXT AS proposal,
       (SELECT STRING_AGG(DISTINCT x.principal, ', ' ORDER BY x.principal) FROM dims.effective_entitlements x WHERE x.action = 'register.cost_centre_map.maintain') AS whose,
       w.ledger_cost_centre || ' ' || w.ledger_name || ' (' || e.entity_name || ') has no planning cost centre — $' || FORMAT('{:,}', ROUND(w.year_amount)::BIGINT) || ' a year outside the plan' AS item,
       w.entity_code, w.year_amount
FROM w JOIN dims.dim_entity e ON e.entity_code = w.entity_code
