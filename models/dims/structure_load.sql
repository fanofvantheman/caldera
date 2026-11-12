/* Each structure as the plan was given it: the system it came from and its loads, the latest and the one before. The plan
   reads these structures; it does not maintain them. */
MODEL (name dims.structure_load, kind FULL, grain (structure, load_id));
SELECT structure::TEXT AS structure, structure_name::TEXT AS structure_name, source_system::TEXT AS source_system, load_id::TEXT AS load_id,
       loaded_at::TIMESTAMP AS loaded_at, is_latest = 'Y' AS is_latest
FROM bronze.ctl_structure_load
