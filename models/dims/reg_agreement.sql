/* Each entity's agreement as the labour model reads it: classification × hourly rate, effective from a period — read
   from the agreement's entitlements (dims.reg_entitlement): the base rates of its rates schedule, and from each dated
   increase a later row, each rate × (1 + the increase) to the cent. Penalties, allowances and leave are entitlements of
   kinds the labour model does not price yet. */
MODEL (name dims.reg_agreement, kind FULL, grain (agreement, classification, valid_from_period));
WITH e AS (SELECT * FROM dims.reg_entitlement WHERE layer = 'agreement' AND kind_known),
base AS (SELECT instrument AS agreement, instrument_name AS agreement_name, entity_code, classification, classification_name,
                value AS hourly_rate, valid_from_period FROM e WHERE kind = 'base_rate'),
inc AS (SELECT instrument AS agreement, value AS pct, valid_from_period FROM e WHERE kind = 'dated_increase')
SELECT agreement, agreement_name, entity_code, classification, classification_name, hourly_rate, valid_from_period FROM base
UNION ALL
SELECT b.agreement, b.agreement_name, b.entity_code, b.classification, b.classification_name,
       ROUND(b.hourly_rate * EXP(SUM(LN(1 + i2.pct))), 2) AS hourly_rate, i.valid_from_period
FROM base b
JOIN inc i ON i.agreement = b.agreement AND i.valid_from_period > b.valid_from_period
JOIN inc i2 ON i2.agreement = b.agreement AND i2.valid_from_period > b.valid_from_period AND i2.valid_from_period <= i.valid_from_period
GROUP BY b.agreement, b.agreement_name, b.entity_code, b.classification, b.classification_name, b.hourly_rate, i.valid_from_period
