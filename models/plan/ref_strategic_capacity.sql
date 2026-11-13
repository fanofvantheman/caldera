/* The capacities the strategic plan declares (CH 2026-11-13): production, storage, working capital, material, logistics —
   the few that would force a board decision if they broke; the rest are not modelled, and said not to be. Per kind: its
   unit, the tiers it steps through (capacities.md §Tiers by kind), whether Caldera computes it, and what it has and lacks. */
MODEL (name plan.ref_strategic_capacity, kind FULL, grain (kind));
SELECT * FROM (VALUES
  (1, 'production', 'Production', 'line hours, by plant', 'as registered (the shifts each line runs) → one more shift on every line → a further line', 'computed',
   'Available from the machine register; load from the demand plan through each material''s primary route. Tier 1 is derived from the register; no step cost or lead time is declared, and a further line is not.'),
  (2, 'storage', 'Storage', 'pallet positions, by plant and DC', 'own store → overflow at the 3PL → a further DC', 'no data',
   'The plants and three 3PL DCs are loaded as nodes that store; no pallet positions, no days of cover and no inventory plan — so neither what is available nor the load can be computed.'),
  (3, 'working_capital', 'Working capital', 'dollars, the business', 'cash and facility → a facility increase → a capital raise', 'load only',
   'Receivables at the accounts'' payment terms are computed from the plan''s net sales. No limit, facility or covenant is declared, and inventory and payables are not planned, so there is nothing to read the load against.'),
  (4, 'material', 'Material', 'tonnes of the key materials, by plant', 'contracted → additional at a premium → spot or an alternative recipe', 'no data',
   'The bills of material and the input materials are loaded; no supplier commitments and no intake plan — so no availability, and the drawdown is not read against anything.'),
  (5, 'logistics', 'Logistics', 'loads, by lane', 'own fleet → carrier spot → contracted lanes', 'no data',
   'The lanes are loaded with transit days and a cost per pallet; no loads, carriers or contracted volumes — so no capacity.')
) AS t(ord, kind, label, unit, tiers, computed, says)
