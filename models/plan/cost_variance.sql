/* The planned unit cost against the standard, by version × material × period, each line calculated and never entered
   (DEC-20261116-02 point 5). A variance is planned − standard: positive is adverse, negative favourable.
     material price   Σ inputs (planned price − standard price) × planned usage
     material usage   Σ inputs (planned usage − standard usage) × standard price — an input the standard has not got is
                      usage at its planned price; one the plan no longer uses is its standard cost, saved
     labour rate      (planned rate − standard rate) × planned hours
     labour efficiency (planned hours − standard hours) × standard rate
     variable overhead planned − standard, the sum of its pools
     fixed overhead   planned − standard per case: nil where the rate is held from the business plan of the year
   The lines sum to the planned unit cost less the standard. A period of a year with no standard for the material reads
   none. Fixed overhead's spending and volume are a plant's money, not a case's: plan.fixed_variance.
   A component typed over its drivers (DEC-20261116-02 point 7) has no price and usage, rate and efficiency to split: its
   variance is read whole — material or labour planned − standard, the split lines empty. */
MODEL (name plan.cost_variance, kind FULL, grain (version_id, material_code, period));
WITH u AS (
  SELECT u.*, p.fiscal_year::INT AS fiscal_year FROM plan.planned_unit_cost u JOIN dims.dim_period p ON p.period = u.period
),
s AS (SELECT * FROM plan.standard_cost),
pin AS (SELECT version_id, material_code, period, input_code, quantity, price FROM plan.planned_material_input),
sin AS (                                              -- the standard's inputs laid on every cell of its material and year
  SELECT u.version_id, u.material_code, u.period, si.input_code, si.std_quantity, si.std_price
  FROM u JOIN plan.standard_input si ON si.material_code = u.material_code AND si.plant_code = u.plant_code AND si.fiscal_year = u.fiscal_year
),
inputs AS (
  SELECT COALESCE(pin.version_id, sin.version_id) AS version_id, COALESCE(pin.material_code, sin.material_code) AS material_code,
         COALESCE(pin.period, sin.period) AS period,
         SUM(CASE WHEN sin.std_price IS NOT NULL AND pin.price IS NOT NULL THEN (pin.price - sin.std_price) * pin.quantity ELSE 0 END) AS mat_price,
         SUM(CASE WHEN sin.std_price IS NULL THEN pin.quantity * pin.price
                  WHEN pin.price IS NULL THEN -sin.std_quantity * sin.std_price
                  ELSE (pin.quantity - sin.std_quantity) * sin.std_price END) AS mat_usage
  FROM pin FULL JOIN sin ON sin.version_id = pin.version_id AND sin.material_code = pin.material_code AND sin.period = pin.period AND sin.input_code = pin.input_code
  GROUP BY ALL
)
SELECT u.version_id, u.material_code, u.plant_code, u.period, u.fiscal_year, s.set_on,
       u.unit_cost, s.std_cost, s.std_material, s.std_labour, s.std_variable, s.std_fixed,
       u.crew_hours AS planned_hours, u.loaded_rate AS planned_rate, s.std_hours, s.std_rate,
       CASE WHEN NOT u.typed_material THEN i.mat_price END AS mat_price, CASE WHEN NOT u.typed_material THEN i.mat_usage END AS mat_usage,
       CASE WHEN NOT u.typed_labour THEN (u.loaded_rate - s.std_rate) * u.crew_hours END AS lab_rate,
       CASE WHEN NOT u.typed_labour THEN (u.crew_hours - s.std_hours) * s.std_rate END AS lab_eff,
       CASE WHEN u.typed_material THEN u.material_cost - s.std_material ELSE COALESCE(i.mat_price, 0) + COALESCE(i.mat_usage, 0) END AS var_material,
       CASE WHEN u.typed_labour THEN u.labour_cost - s.std_labour
            ELSE (u.loaded_rate - s.std_rate) * u.crew_hours + (u.crew_hours - s.std_hours) * s.std_rate END AS var_labour,
       u.variable_overhead - s.std_variable AS var_oh,
       u.fixed_overhead - s.std_fixed AS fixed_oh,
       u.unit_cost - s.std_cost AS var_total,
       u.typed_material, u.typed_labour, u.typed_variable, u.typed_fixed
FROM u JOIN s ON s.material_code = u.material_code AND s.plant_code = u.plant_code AND s.fiscal_year = u.fiscal_year
LEFT JOIN inputs i ON i.version_id = u.version_id AND i.material_code = u.material_code AND i.period = u.period
WHERE u.complete
