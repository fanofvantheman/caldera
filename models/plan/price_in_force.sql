/* The list price in force for every material on every price list in every week: the effective-dated row whose validity
   covers the week's start. In the list's currency; the version's FX assumption converts at valuation. */
MODEL (name plan.price_in_force, kind FULL, grain (price_list, material_code, week_id));
SELECT w.week_id, p.price_list, p.material_code, p.currency, p.price_per_case, p.valid_from, p.price_event
FROM dims.dim_week w
JOIN history.price_list p ON p.valid_from <= w.week_start AND (p.valid_to IS NULL OR p.valid_to >= w.week_start)
QUALIFY ROW_NUMBER() OVER (PARTITION BY w.week_id, p.price_list, p.material_code ORDER BY p.valid_from DESC) = 1
