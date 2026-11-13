/* The strategic plan: one plan over five years, the latest view it reads inside its reach, its owner. */
MODEL (name plan.strategic_plan, kind FULL, grain (plan_id));
SELECT plan_id::TEXT AS plan_id, plan_name::TEXT AS plan_name, latest_view::TEXT AS latest_view, first_year::INT AS first_year,
       last_year::INT AS last_year, owner::TEXT AS owner, named_on::DATE AS named_on
FROM bronze.reg_strategic_plan
