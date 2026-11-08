/* The reasons an entry may give, and the layers each is offered on. A reason is a vocabulary, so bias can be found by
   reason as well as by owner. */
MODEL (name plan.ref_reason_code, kind FULL, grain (reason_code));
SELECT reason_code::TEXT AS reason_code, description::TEXT AS description, layers::TEXT AS layers FROM bronze.ref_reason_code
