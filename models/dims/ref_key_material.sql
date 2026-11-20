/* The key raw materials at the plants that draw them (DEC-20261116-04 point 1): every input the material master marks as
   key (dims.dim_input_material.is_key_material — a purchase is prepared for it every month) at every plant whose bill
   uses it. How each is bought is declared input by input at its plant — contract: a price fixed, or tied to an index, for
   its term; spot: the price in force with its index; campaign intake: bought in the input's campaign window — with the
   cover a proposed purchase keeps (periods of the next period's requirement), the stock on hand when a plan opens and its
   cost against the price in force (periods of requirement for a contract or spot material; a campaign material opens with
   what it needs until its window, 5% over), and the receipts already contracted a period (contract_quantity — through the
   contract's term for a contract material, in each window period for a campaign one). A key material with no declaration
   is bought spot, one period's cover, one period on hand, nothing contracted.
   Specimen figures: Caldera loads no contracts, no open orders and no stock balance — the opening stock and the contracted
   receipts stand in for the ERP's at the actuals cutoff (DEC-20261120-02 point 1), declared, not a client's values. */
MODEL (name dims.ref_key_material, kind FULL, grain (input_code, plant_code));
WITH declared AS (
  SELECT * FROM (VALUES
    ('TOMATO',    'ECH', 'campaign', 0.0, NULL,  NULL,        NULL,      3.2, 1.06, 5000.0,    'grower contracts settled at intake; last season''s pack dearer'),
    ('PEACH',     'LOX', 'campaign', 0.0, NULL,  NULL,        NULL,      2.2, 0.97, 3000.0,    'intake January to March'),
    ('PEACH',     'ECH', 'campaign', 0.0, NULL,  NULL,        NULL,      2.2, 0.97, 700.0,     'intake January to March'),
    ('PEAR',      'ECH', 'campaign', 0.0, NULL,  NULL,        NULL,      3.2, 1.02, 600.0,     'intake February to April'),
    ('PEAR',      'LOX', 'campaign', 0.0, NULL,  NULL,        NULL,      3.2, 1.02, 170.0,     'intake February to April'),
    ('SUGAR',     'ECH', 'contract', 1.0, 870.0, 'SUGAR_IDX', '2028P06', 1.5, 1.01, 80.0,      'annual supply contract tied to the sugar index'),
    ('SUGAR',     'LOX', 'contract', 1.0, 870.0, 'SUGAR_IDX', '2028P06', 1.5, 1.01, 30.0,      'annual supply contract tied to the sugar index'),
    ('BEANS_DRY', 'ECH', 'contract', 2.0, 1360.0, NULL,       '2027P12', 2.5, 1.04, 110.0,     'fixed-price contract to December; spot after it'),
    ('CAN_410_E', 'ECH', 'contract', 1.0, 0.048, NULL,        '2028P06', 1.0, 1.00, 2200000.0, 'can supply agreement, fixed for the year'),
    ('CAN_410_E', 'LOX', 'contract', 1.0, 0.048, NULL,        '2028P06', 1.0, 1.00, 1100000.0, 'can supply agreement, fixed for the year'),
    ('CUP_120',   'LOX', 'spot',     1.5, NULL,  NULL,        NULL,      1.5, 1.05, NULL,      'imported cups bought spot, landed, with the resin index')
  ) AS t (input_code, plant_code, source, cover_periods, contract_price, contract_index, contract_through, opening_periods, opening_cost_factor, contract_quantity, note)
),
drawn AS (                                            -- every key material at every plant whose bill uses it
  SELECT DISTINCT b.component_material AS input_code, b.plant_code
  FROM dims.ref_bom b JOIN dims.dim_input_material i ON i.material_code = b.component_material AND i.is_key_material
)
SELECT w.input_code::TEXT AS input_code, w.plant_code::TEXT AS plant_code, COALESCE(d.source, 'spot')::TEXT AS source,
       COALESCE(d.cover_periods, 1.0)::DOUBLE AS cover_periods, d.contract_price::DOUBLE AS contract_price, d.contract_index::TEXT AS contract_index,
       d.contract_through::TEXT AS contract_through, COALESCE(d.opening_periods, 1.0)::DOUBLE AS opening_periods,
       COALESCE(d.opening_cost_factor, 1.0)::DOUBLE AS opening_cost_factor, d.contract_quantity::DOUBLE AS contract_quantity,
       COALESCE(d.note, 'no buying declared: spot, one period''s cover')::TEXT AS note
FROM drawn w LEFT JOIN declared d ON d.input_code = w.input_code AND d.plant_code = w.plant_code
