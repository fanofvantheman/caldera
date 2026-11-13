/* The name-based headcount: each person (or named vacancy) in an overhead cost centre with their own terms — an annual
   salary, an incentive at target as a share of it, a start and an end. Individual pay: read under read.pay only. */
MODEL (name dims.reg_person, kind FULL, grain (person_id));
SELECT person_id::TEXT AS person_id, entity_code::TEXT AS entity_code, cost_centre_code::TEXT AS cost_centre_code, "name"::TEXT AS person_name,
       title::TEXT AS title, annual_salary::DOUBLE AS annual_salary, incentive_pct::DOUBLE AS incentive_pct, start_date::DATE AS start_date,
       NULLIF(end_date::TEXT, '')::DATE AS end_date, vacancy = 'Y' AS vacancy
FROM bronze.reg_person
