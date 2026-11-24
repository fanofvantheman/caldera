/* The planning processes (DEC-20261124-08 point 1): each a planning process with a review cycle of its own. A short
   declared list. The process is set on a planning fact and on a role type; everything else in the role architecture
   inherits it. */
MODEL (name dims.ref_process, kind FULL, grain (process));
SELECT * FROM (VALUES
  ('ibp',       'Integrated business planning', 1),
  ('financial', 'Financial planning',           2)
) AS t (process, process_name, ord)
