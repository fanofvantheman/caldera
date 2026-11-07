/* The same plan read at the grain the cycle reviews it: standard material × trading account × period, by version, with
   each layer's contribution beside the total so the review sees the decomposition, not an asserted number. */
MODEL (name plan.unconstrained_demand_period, kind FULL, grain (version_id, standard_material, account_code, period));
SELECT version_id, standard_material, account_code, period, fiscal_year, SUM(cases) AS cases, SUM(tonnes) AS tonnes,
       SUM(CASE WHEN layer_no = 1 THEN cases ELSE 0 END) AS l1_baseline, SUM(CASE WHEN layer_no = 2 THEN cases ELSE 0 END) AS l2_adjustment,
       SUM(CASE WHEN layer_no = 4 THEN cases ELSE 0 END) AS l4_distribution, SUM(CASE WHEN layer_no = 6 THEN cases ELSE 0 END) AS l6_promotions,
       SUM(CASE WHEN layer_no = 7 THEN cases ELSE 0 END) AS l7_innovation, SUM(CASE WHEN layer_no = 8 THEN cases ELSE 0 END) AS l8_exit
FROM plan.demand_stack
GROUP BY ALL
