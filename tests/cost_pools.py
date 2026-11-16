"""Cost pools and the map — through the warehouse and the routes; the one act it places is removed again.

    uv run python -m tests.cost_pools        # from build/, with the warehouse built

1. Every cell of cost centre × account that carries a cost resolves to one pool or to not in cost of goods; none waits.
2. The map's order: a production hall's electricity is process energy, the warehouse's site energy; quality and
   technical is quality whatever the account; a non-factory cost centre is not in cost of goods.
3. Every pool's component agrees with its lines' drivers (variable: driven by cases made at the plant; fixed: not).
4. On every cell of the standard, each component is the sum of its pools; fixed overhead is the fixed pools' cost ÷ the
   denominator; indirect labour is its lines less the direct labour the routes take.
5. The Pools and Map pages, and a rule: refused without the right or without a key; placed by the holder as one act in
   the map's register (the file is removed again — nothing reaches a run).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

BUILD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BUILD))
if os.environ.get("FACE_ROOT"):
    sys.path.insert(0, os.environ["FACE_ROOT"])

import chassis                                        # noqa: E402
from chassis import app as chassis_app                # noqa: E402
from chassis.warehouse import q                       # noqa: E402

from face import SHELL, pools, roles, session         # noqa: E402
from face import __main__ as M                        # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
FINANCE, PLANNER = "finance.manager@caldera", "planner.westbrook@caldera"
EPS = 1e-9


def main() -> None:
    # 1 · every cell resolves
    cells = q("select * from plan.cost_pool_cell")
    assert cells and not [c for c in cells if c["unmapped"]], "a cell carrying a cost is in no pool"
    assert q("select count(*) n from plan.worklist_cost_pool_unmapped")[0]["n"] == 0
    assert not [c for c in cells if c["no_plant"]], "a cell in a pool of cost of goods at a cost centre with no plant"
    by = {(c["entity_code"], c["cost_centre_code"], c["account_code"]): c for c in cells}
    # 2 · the map's order
    assert by[("CF", "CC_E_TOM", "6200")]["pool_code"] == "PROCESS_ENERGY" and by[("CF", "CC_E_TOM", "6200")]["tier"] == 1
    assert by[("CF", "CC_E_WHSE", "6200")]["pool_code"] == "SITE_ENERGY" and by[("CF", "CC_E_WHSE", "6200")]["tier"] == 3
    assert by[("CF", "CC_QA", "6100")]["pool_code"] == "QUALITY" and by[("CF", "CC_QA", "6100")]["tier"] == 2
    assert by[("CF", "CC_E_MAINT", "6400")]["pool_code"] == "MAINTENANCE" and by[("CF", "CC_E_TOM", "6400")]["pool_code"] == "CONSUMABLES"
    assert all(c["pool_code"] == "NOT_COGS" for c in cells if c["cost_centre_code"] in ("CC_LOG", "CC_SALES", "CC_FIN", "CC_EXEC"))
    # 3 · the driver agrees with the pool on every cell
    assert not [c for c in cells if c["driver_disagrees"]], [(c["cost_centre_code"], c["account_code"]) for c in cells if c["driver_disagrees"]]
    lines = q("""select c.component, s.driver, c.plant_code from plan.opex_schedule s join plan.cost_pool_cell c using (entity_code, cost_centre_code, account_code)
                 where c.component in ('variable_overhead', 'fixed_overhead')""")
    assert all((l["driver"] == "cases_made_" + l["plant_code"].lower()) == (l["component"] == "variable_overhead") for l in lines)
    # 4 · each component is the sum of its pools
    bad = q(f"""with p as (select version_id, material_code, period,
                        sum(case when component = 'material' then per_case end) m, sum(case when component = 'labour' then per_case end) l,
                        sum(case when component = 'variable_overhead' then per_case end) v, sum(case when component = 'fixed_overhead' then per_case end) f
                   from plan.standard_cost_pool group by all)
               select count(*) n from plan.standard_cost s join p using (version_id, material_code, period)
               where abs(coalesce(s.material_cost, 0) - coalesce(p.m, 0)) > {EPS} or abs(coalesce(s.labour_cost, 0) - coalesce(p.l, 0)) > {EPS}
                  or abs(coalesce(s.variable_overhead, 0) - coalesce(p.v, 0)) > {EPS} or abs(coalesce(s.fixed_overhead, 0) - coalesce(p.f, 0)) > {EPS}""")[0]["n"]
    n = q("select count(*) n from plan.standard_cost")[0]["n"]
    assert bad == 0, f"{bad} cells whose components are not the sum of their pools"
    ind = q("""select r.version_id, r.plant_code, r.period, r.lines_amount, r.direct_labour, r.amount from plan.cost_pool_rate r where pool_code = 'INDIRECT_LABOUR'""")
    assert ind and all(abs(r["lines_amount"] - r["direct_labour"] - r["amount"]) < 1e-6 for r in ind)
    ab = q("""select a.version_id, a.plant_code, a.period, a.fixed_lines, sum(r.lines_amount) pools from plan.standard_absorption a
              join plan.cost_pool_rate r using (version_id, plant_code, period) where r.component = 'fixed_overhead' group by all""")
    assert ab and all(abs(a["fixed_lines"] - a["pools"]) < 1e-6 for a in ab), "the amount not absorbed reads the fixed pools"
    print(f"cells           {len(cells)} cells resolve: {sum(1 for c in cells if c['component'])} in a pool of cost of goods, "
          f"{sum(1 for c in cells if c['pool_code'] == 'NOT_COGS')} not in cost of goods; none waits, no driver disagrees")
    print(f"components      on all {n} cells of the standard each component is the sum of its pools; indirect labour is its lines less the routes' direct labour")

    # 5 · the pages and a rule
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    session.become(FINANCE)
    html = c.get("/costs/pools").data.decode()
    for name in ("Ingredients", "Direct labour", "Process energy", "Indirect labour", "Not in cost of goods"):
        assert name in html, name
    mp = c.get("/costs/pool_map").data.decode()
    assert 'action="/costs/pool_map/rule"' in mp and "Rules in force" in mp and "Site energy and occupancy" in mp
    before = set(pools.RULES.files())
    session.become(PLANNER)
    r = c.post("/costs/pool_map/rule", data={"cost_centre_code": "CC_E_TOM", "account_code": "6720", "pool_code": "SITE_ENERGY", "reason": "test"})
    assert r.status_code == 302 and set(pools.RULES.files()) == before, "a person without the right placed a rule"
    assert 'action="/costs/pool_map/rule"' not in c.get("/costs/pool_map").data.decode(), "the form offered without the right"
    session.become(FINANCE)
    c.post("/costs/pool_map/rule", data={"pool_code": "SITE_ENERGY", "reason": "no key"})
    assert set(pools.RULES.files()) == before, "a rule with neither cost centre nor account was placed"
    c.post("/costs/pool_map/rule", data={"cost_centre_code": "CC_E_TOM", "account_code": "9999", "pool_code": "", "reason": "remove nothing"})
    assert set(pools.RULES.files()) == before, "removing a rule that is not there was placed"
    c.post("/costs/pool_map/rule", data={"cost_centre_code": "CC_E_TOM", "account_code": "6720", "pool_code": "SITE_ENERGY", "reason": "insurance on the hall"})
    new = set(pools.RULES.files()) - before
    try:
        assert len(new) == 1, "the holder's rule was not placed as one act"
        text = next(iter(new)).read_text()
        assert re.search(r"set,,CC_E_TOM,6720,SITE_ENERGY,finance\.manager@caldera,", text), text
    finally:
        for p in new:
            p.unlink()
    print("pages           Pools and The map drawn; a rule refused without the right, without a key, and removing nothing; placed by the holder as one act (removed again)")


if __name__ == "__main__":
    main()
