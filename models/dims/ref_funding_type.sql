/* What the supplier pays for an event, and how. Three types are priced through the gross-to-net — the price reduction
   per case, scan funding per case and the fixed fee — each filling its column on the event; the others are carried on
   the event and shown, never dropped, until the financialisation prices them. */
MODEL (name dims.ref_funding_type, kind FULL, grain (funding_type), audits (funding_type_priced_has_column));
SELECT funding_type::TEXT AS funding_type, funding_type_name::TEXT AS funding_type_name, NULLIF(driver_basis::TEXT, '') AS driver_basis,
       priced::TEXT = 'Y' AS priced, NULLIF(event_column::TEXT, '') AS event_column
FROM bronze.ref_funding_type
