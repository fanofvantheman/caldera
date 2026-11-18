/* The review period at each kind of stocking point (DEC-20261117-02 point 2; location_and_drp.md §Replenishment logic):
   the execution cadence, in weeks — weekly at a DC and at a plant — not the plan's cycle. A declared assumption. */
MODEL (name dims.ref_replenishment, kind FULL, grain node_kind);
SELECT * FROM (VALUES ('3pl_dc', 1, 'replenished weekly from the plant'), ('plant', 1, 'production planned weekly')) AS t (node_kind, review_weeks, note)
