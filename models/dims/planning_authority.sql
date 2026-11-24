/* What follows from the four steps (DEC-20261124-07): for each person, through each live role they are assigned, the
   authority its type has over each fact, in the role's own place. The role is the owner; whoever fills it acts as it. */
MODEL (name dims.planning_authority, kind FULL, grain (person, role_no, fact));
SELECT a.person, t.process, r.role_no, r.role_name, r.type_code, t.type_name, e.fact, e.level, r.site, r.customer, r.cost_centre
FROM dims.planning_assignment a
JOIN dims.planning_role r ON r.role_no = a.role_no AND r.live
JOIN dims.planning_role_type t ON t.type_code = r.type_code
JOIN dims.planning_entitlement e ON e.type_code = r.type_code
WHERE a.live
