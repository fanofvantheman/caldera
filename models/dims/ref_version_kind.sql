/* What each kind of version reaches by default: the periods by month planned after its from point, then quarters. A
   version takes its horizon from its kind when it is named; from then on the horizon is the version's own. */
MODEL (name dims.ref_version_kind, kind FULL, grain (version_kind));
SELECT version_kind::TEXT AS version_kind, kind_label::TEXT AS kind_label, horizon_periods::INT AS horizon_periods,
       horizon_quarters::INT AS horizon_quarters, says::TEXT AS says, ord::INT AS ord
FROM bronze.ref_version_kind
