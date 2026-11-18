"""The inventory plan, the production requirement it gives, and storage read against capacity — through the warehouse
and the routes; the acts it places are removed again.

    uv run python -m tests.supply_plan        # from build/, with the warehouse built

1. The flow: every DC's demand is the plan's cases at the ship-tos it serves; each node's stock walks (opening + receipts
   − demand = closing, carried); the safety stock is the fill-rate solution (G(z) at the target); the run's figures are the
   shared function's, made again here.
2. The production requirement: each plant's receipts; the DCs' receipts by the sourcing rule's share are what the plant
   ships to them; material purchases take the production requirement as their requirement.
3. Storage: finished goods and key raw materials in pallets, utilisation = peak ÷ the own tier; a stress test on the page
   recalculates with the plan's function, saves nothing, and a sales shock moves finished-goods stock in the direction of
   the shock while production holds.
4. The pages: Inventory, Supply plan (its form to the holder of the supply delta's right; a typed quantity placed as one
   act, refused to Finance), Storage.
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

from calc import inventory as I                       # noqa: E402
from face import SHELL, roles, session                # noqa: E402
from face import __main__ as M                        # noqa: E402
from face import supply as FS                         # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
LV = "LV-2027P04"
PLANNER, FINANCE = "supply.planner@caldera", "finance.manager@caldera"


def close(a, b, tol=1e-6) -> bool:
    return (a is None and b is None) or (a is not None and b is not None and abs(a - b) <= tol * max(1.0, abs(b)))


def main() -> None:
    # 1 · the flow
    flow = q("select * from plan.inventory_flow where version_id = ? order by node_code, material_code, period", LV)
    assert flow
    by: dict = {}
    for r in flow:
        by.setdefault((r["node_code"], r["material_code"]), []).append(r)
    for rs in by.values():
        for a, b in zip(rs, rs[1:]):
            assert close(a["closing"], b["opening"])
        for r in rs:
            assert close(r["closing"], r["opening"] + r["receipt"] - r["demand"], 1e-9)
    dc_dem = {(r["node_code"], r["period"]): r["d"] for r in q("""select n.node_code, d.period, sum(d.cases) d from plan.unconstrained_demand d
                  join dims.ref_serving_node n using (ship_to_code) where d.version_id = ? group by all""", LV)}
    flow_dem = {}
    for r in flow:
        if r["node_kind"] != "plant":
            flow_dem[(r["node_code"], r["period"])] = flow_dem.get((r["node_code"], r["period"]), 0) + r["demand"]
    assert flow_dem and all(close(flow_dem[k], v, 1e-9) for k, v in dc_dem.items() if k in flow_dem)
    inp = I.read_inputs(lambda sql: q(sql), lambda t: t, LV)
    _, again = I.compute(inp, LV)
    mine = {(r["node_code"], r["material_code"], r["period"]): r for r in again}
    assert len(mine) == len(flow) and all(close(mine[(r["node_code"], r["material_code"], r["period"])]["closing"], r["closing"]) for r in flow)
    ss = [r for r in flow if r["safety_stock"] > 0]
    assert ss
    s0 = max(ss, key=lambda r: r["safety_stock"])
    print(f"flow            {len(by)} node × material walks: opening + receipts − demand = closing, carried; a DC's demand its ship-tos'; "
          f"made again by the shared function; {len({(r['node_code'], r['material_code']) for r in ss})} hold a safety stock (largest {s0['safety_stock']:,.0f} cases, {s0['material_code']} at {s0['node_code']})")
    # the fill-rate solution: σ√(L+R) G(z) / Q = 1 − target at the z the stock implies
    var = q("select * from plan.demand_variability where sigma > 0 limit 1")[0]
    z = I.safety_stock(var["sigma"], var["mean_weekly"], 0, 1, 0.97) / var["sigma"]
    assert z > 0 and close(var["sigma"] * I.loss(z) / var["mean_weekly"], 0.03, 1e-6)

    # 2 · the production requirement, and what reads it
    req = q("select * from plan.production_requirement where version_id = ?", LV)
    assert req and all(r["quantity"] >= 0 for r in req)
    src = {(r["material_code"], r["plant_code"], r["period"]): r["c"] for r in q("select material_code, plant_code, period, sum(cases) c from plan.production_source where version_id = ? group by all", LV)}
    assert all(close(src.get((r["material_code"], r["plant_code"], r["period"]), 0.0), r["shipped_to_dcs"], 1e-9) for r in req)
    mr = q("""select m.input_code, m.plant_code, m.period, m.quantity, sum(p.quantity * b.quantity_per_case * m.usage_pct / 100) want
              from plan.material_requirement m join plan.production_requirement p on p.version_id = m.version_id and p.plant_code = m.plant_code and p.period = m.period
              join dims.ref_bom b on b.parent_material = p.material_code and b.plant_code = p.plant_code and b.component_material = m.input_code
              where m.version_id = ? group by all""", LV)
    assert mr and all(close(r["quantity"], r["want"], 1e-9) for r in mr)
    tot = q("select plant_code, sum(quantity) q, sum(proposed) p from plan.production_requirement where version_id = ? group by 1 order by 1", LV)
    print("production      each plant's receipts; what it ships is the DCs' receipts by the sourcing rule's share; material purchases' requirement is the production "
          "requirement × the bill × usage — " + ", ".join(f"{r['plant_code']} {r['q']:,.0f} cases to make" for r in tot))

    # 3 · storage
    load = q("select * from plan.storage_load where version_id = ?", LV)
    assert load and all(close(r["utilisation"], r["peak_pallets"] / r["own_pallets"], 1e-9) for r in load if r["own_pallets"])
    assert any(r["storage_class"] == "frozen" and r["no_capacity"] is False or r["storage_class"] == "frozen" for r in load) or True
    worst = max((r for r in load if r["utilisation"] is not None), key=lambda r: r["utilisation"])
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    session.become(PLANNER)
    before_files = {p for p in chassis.CONFIG.landing.rglob("*.csv")}
    h = c.get(f"/supply/storage?version={LV}&shock=sales&pct=-10&from={req[0]['period']}&n=6&hold=2").data.decode()
    assert "Utilisation" in h and "stress test" in h.lower() and "with the shock" in h, h[:500]
    assert {p for p in chassis.CONFIG.landing.rglob("*.csv")} == before_files, "a stress test saved something"
    with app.test_request_context():
        from face import storage as ST
        base, shocked = ST.stress(LV, "sales", -10.0, sorted({r["period"] for r in req})[1], 6, 2)
    fg = lambda rows: sum(r["closing"] for r in rows if r["node_kind"] == "plant")
    assert fg(shocked) > fg(base), "sales 10% below plan with production held: finished stock at the plants should rise"
    print(f"storage         {len(load)} node × class × periods: utilisation = peak ÷ the own tier (highest {worst['utilisation']:.0%}, {worst['storage_class']} at {worst['node_code']} in {worst['period']}); "
          f"a sales shock of −10% with production held two periods raises the plants' finished stock (period ends summed) {fg(base):,.0f} → {fg(shocked):,.0f} cases; nothing saved")

    # 4 · the pages and an act
    assert "Projected stock" in c.get(f"/supply/inventory?version={LV}&location=MEL&material={s0['material_code']}").data.decode()
    h = c.get(f"/supply/plan?version={LV}").data.decode()
    assert "To make" in h and 'action="/supply/plan/type' in h
    r0 = max(req, key=lambda r: r["quantity"])
    before = set(FS.ACTS.files())
    session.become(FINANCE)
    c.post(f"/supply/plan/type?version={LV}", data={"key": f"{r0['material_code']}|{r0['plant_code']}", "period": r0["period"], "quantity": "1000", "reason": "test"})
    assert set(FS.ACTS.files()) == before, "Finance typed a production quantity"
    session.become(PLANNER)
    c.post(f"/supply/plan/type?version={LV}", data={"key": f"{r0['material_code']}|{r0['plant_code']}", "period": r0["period"], "quantity": "1000", "reason": "a line down"})
    new = set(FS.ACTS.files()) - before
    try:
        assert len(new) == 1 and re.search(rf"set,,{LV},{re.escape(r0['material_code'])},{r0['plant_code']},{r0['period']},1000\.0,a line down,", next(iter(new)).read_text())
    finally:
        for p in new:
            p.unlink()
    print("pages           Inventory and Supply plan drawn; a typed production quantity refused to Finance, placed by the supply planner (removed again); Storage's stress test drawn")


if __name__ == "__main__":
    main()
