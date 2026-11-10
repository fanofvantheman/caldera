/* The mechanic register: what the shopper sees, its family, and the response the plan assumes when an event typed in the
   plan says nothing else — the uplift on the baseline in the window and the dip in the week after. An event from the
   promotions sender carries its own response; the family is read from here either way. */
MODEL (name dims.ref_mechanic, kind FULL, grain (mechanic), audits (mechanic_family_known));
SELECT mechanic::TEXT AS mechanic, mechanic_name::TEXT AS mechanic_name, family::TEXT AS family,
       default_uplift_pct::DOUBLE AS default_uplift_pct, default_dip_pct::DOUBLE AS default_dip_pct
FROM bronze.ref_mechanic
