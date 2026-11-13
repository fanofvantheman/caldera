/* Finance's growth by category for each year beyond the latest view's reach — the far-horizon rates the strategic plan
   grows its volume by. Varied as part of the modelling, so kept on the strategic plan's own page, not with the global
   assumptions (CH 2026-11-13). */
MODEL (name plan.strategic_growth, kind FULL, grain (plan_id, category_code, fiscal_year));
SELECT plan_id::TEXT AS plan_id, category_code::TEXT AS category_code, fiscal_year::INT AS fiscal_year, growth_pct::DOUBLE AS growth_pct,
       NULLIF(note::TEXT, '') AS note, entered_by::TEXT AS entered_by, entered_on::TEXT AS entered_on
FROM bronze.reg_strategic_growth
