/* The kinds of entitlement the labour model has a calculation for — closed. An entitlement (an agreement's afternoon
   loading, a state's payroll tax) is a row under one of these; a clause that fits none is an item to resolve, not forced
   in. `priced`: the labour model reads the kind today; the others are listed so a row under them is kept and said not
   yet priced, never dropped. */
MODEL (name dims.ref_entitlement_kind, kind FULL, grain (kind));
SELECT kind::TEXT AS kind, kind_label::TEXT AS kind_label, what::TEXT AS what, calculates::TEXT AS calculates, priced::TEXT = 'Y' AS priced, ord::INT AS ord
FROM bronze.ref_entitlement_kind
