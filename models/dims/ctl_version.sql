/* Every forward view is a version — named by the cycle that produced it, with a horizon, a calendar variant,
   the standard it is valued at and the reference it is read against. Versions are data: a key on every planned fact. */
MODEL (name dims.ctl_version, kind FULL, grain (version_id), audits (version_vocabulary));
SELECT version_id::TEXT AS version_id, version_kind::TEXT AS version_kind, cycle::TEXT AS cycle, fiscal_year::TEXT AS fiscal_year,
       horizon_start::TEXT AS horizon_start, horizon_end::TEXT AS horizon_end, calendar_variant::TEXT AS calendar_variant,
       standard_version::TEXT AS standard_version, NULLIF(reference_version::TEXT, '') AS reference_version,
       status::TEXT AS status, owner::TEXT AS owner, named_on::DATE AS named_on
FROM bronze.ctl_version
