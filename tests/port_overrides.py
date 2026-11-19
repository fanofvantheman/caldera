"""Sandboxes, the port and recalculation — through the routes and whole runs; everything it places is removed and the plan
run again.

    uv run python -m tests.port_overrides        # from build/, with the warehouse built; takes seven runs

DEC-20261119-01:
1. The override points are a declared list (five; three port) and the Port page shows it.
2. A sandbox: a what-if named from the latest view carries its overrides (the buyer's purchase act among them). Overrides
   typed on the sandbox and on the Plan, under manual recalculation, are placed and not run: the stage they sit at reads
   *overrides waiting* and every stage after it *behind*, on its own Plan only. Recalculating (a holder of run.plan) runs
   them in and nothing is behind; the sandbox's figures did not move the Plan.
3. The port, sandbox → its Plan: only what was typed on the sandbox is offered (not the copies of the Plan's own); a cell
   the Plan holds differently is a clash, shown with both figures; refused to a person without the point's right; ported
   with the clash kept: one purchase row naming the act it came from, one port act. Nothing ports into a sandbox.
4. The setting changed to automatic (by the plan administrator); a second port taking the clash recalculates at once: the
   Plan's production quantity is the sandbox's figure, materials read it, nothing behind; a third look offers nothing new.
5. Plan → the next Plan: a sandbox of the business plan (from 2026P12) ports into the latest view (from 2027P04) only the
   periods the latest view still plans — an override in 2027P03 is not offered.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BUILD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BUILD))
if os.environ.get("FACE_ROOT"):
    sys.path.insert(0, os.environ["FACE_ROOT"])

import chassis                                        # noqa: E402
from chassis import app as chassis_app                # noqa: E402
from chassis.warehouse import q                       # noqa: E402

from face import SHELL, roles, session                # noqa: E402
from face import __main__ as M                        # noqa: E402
from face import overrides as OV                      # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
LV, BP = "F202705", "B202701"
SB, BSB = f"{LV}-A", f"{BP}-A"
FINANCE, SUPPLY, PLANNER = "finance.manager@caldera", "supply.planner@caldera", "planner.westbrook@caldera"
MAT, PLANT, PER = "CUP_PEACH-CUP_4x120", "LOX", "2027P08"
INP = "CUP_120"
RUN = [["uv", "run", "python", "-m", "ingest.pipeline"], ["uv", "run", "sqlmesh", "plan", "prod", "--restate-model", "*", "--auto-apply", "--no-prompts"]]


def run() -> None:
    for cmd in RUN:
        r = subprocess.run(cmd, cwd=BUILD, capture_output=True, text=True)
        assert r.returncode == 0 and "Error" not in r.stdout[-2000:], (cmd, r.stdout[-1500:], r.stderr[-1500:])


def landing_files() -> set:
    return set(chassis.CONFIG.landing.rglob("*.csv"))


def qty(version: str, mat: str = MAT, per: str = PER) -> dict:
    return q("select proposed, quantity, typed from plan.production_requirement where version_id = ? and material_code = ? and plant_code = ? and period = ?",
             version, mat, PLANT, per)[0]


def main() -> None:
    pts = OV.points()
    over = [p for p in pts if p["kind"] == "override"]          # the drivers beside them are tests/port_drivers.py's (DEC-20261119-03)
    assert [p["point"] for p in over] == ["production", "purchase", "unit_cost", "finance", "schedule_lock"] and all(p["ports"] for p in over)
    assert OV.mode() == "manual"
    print("override points five declared — production quantity, a key material's purchase, a unit cost component, Finance's volume or price, an opex month locked; "
          "every one ports; recalculation manual by default")

    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    before = landing_files()
    lv_mat_req = q("select sum(quantity) s from plan.material_requirement where version_id = ? and plant_code = ? and period = ?", LV, PLANT, PER)[0]["s"]
    try:
        # 2 · a sandbox, and overrides typed on it and on the Plan
        session.become(FINANCE)
        c.post("/versions/name", data={"base_version": LV, "version_id": SB, "reason": "test: a sandbox", "from_period": "2027P04"})
        assert q("select 1 from dims.ctl_version where version_id = ?", SB), session.last
        assert q("select count(*) n from plan.purchase_act where version_id = ?", SB)[0]["n"] == 1, "the buyer's purchase act copied into the sandbox"
        h = c.get(f"/port?version={LV}").data.decode()
        assert "What ports" in h and "Cases to make" in h and "driver" in h      # the override points beside the drivers (DEC-20261119-03)
        p0 = qty(LV)
        typed_from = landing_files()
        session.become(SUPPLY)
        c.post(f"/supply/plan/type?version={SB}", data={"key": f"{MAT}|{PLANT}", "period": PER, "quantity": "70000", "reason": "test: the sandbox's run length"})
        c.post(f"/supply/purchases/type?version={SB}", data={"key": f"{INP}|{PLANT}", "period": PER, "price": "0.071", "reason": "test: a quote"})
        c.post(f"/supply/plan/type?version={LV}", data={"key": f"{MAT}|{PLANT}", "period": PER, "quantity": "65000", "reason": "test: the Plan's own"})
        assert len([p for p in landing_files() - typed_from if "reg_production_act" in str(p) or "reg_purchase_act" in str(p)]) == 3, (landing_files() - typed_from, session.last)
        assert OV.behind(SB) == {"demand": "", "valuation": "", "inventory": "", "production": "overrides waiting", "materials": "overrides waiting", "cost": "behind",
                                 "finance": "behind", "statements": "behind"}, OV.behind(SB)
        sh = c.get(f"/stages?version={SB}").data.decode()
        assert "Recalculate" in sh and "behind" in sh
        assert qty(LV)["quantity"] == p0["quantity"], "manual: nothing recalculated"
        print(f"sandbox         {SB} named from {LV} with its purchase act; a production quantity and a price typed on it and a quantity on {LV}, manual: placed, not run — "
              "production and materials read overrides waiting, cost to statements behind")
        session.become(SUPPLY)
        c.post(f"/stages/recalculate?version={SB}")
        assert not any(OV.behind(SB).values()) and not any(OV.behind(LV).values())
        assert abs(qty(SB)["quantity"] - 70000) < 1e-6 and abs(qty(LV)["quantity"] - 65000) < 1e-6 and qty(LV)["typed"]
        print(f"recalculated    by the supply planner: {SB} makes 70,000 of {MAT} at {PLANT} in {PER}, {LV} 65,000 (proposed {p0['proposed']:,.0f}); nothing behind")

        # 3 · the port, sandbox → its Plan
        ph = c.get(f"/port?from={SB}&to={LV}").data.decode()
        rows = OV.offer(OV_v(SB), OV_v(LV), "sandbox")
        assert sorted((r["point"], r["status"]) for r in rows) == [("production", "clash"), ("purchase", "port")], [(r["point"], r["status"], r["act_id"]) for r in rows]
        assert "a different override" in ph and "keep" in ph and "65,000" in ph and "70,000" in ph
        assert OV.pair(OV_v(LV), OV_v(SB))[0] is False and "nothing ports into a sandbox" in OV.pair(OV_v(LV), OV_v(SB))[1]
        ids = [r["id"] for r in rows]
        mark = landing_files()
        session.become(PLANNER)
        c.post("/port", data={"from": SB, "to": LV, "take": ids, "reason": "test"})
        assert landing_files() == mark, "a port by someone without the points' rights"
        session.become(SUPPLY)
        c.post("/port", data={"from": SB, "to": LV, "take": ids, "reason": "test: the quote agreed"})       # the clash kept as the Plan holds it
        new = landing_files() - mark
        pur = [p for p in new if "reg_purchase_act" in str(p)]
        assert len(new) == 2 and len(pur) == 1 and any("reg_version_act" in str(p) for p in new), new
        body = pur[0].read_text()
        assert "ported_from" in body.splitlines()[0] and LV in body and "0.071" in body
        print(f"port            {SB} → {LV}: offers the sandbox's two (not the copies of {LV}'s own), the production quantity a clash shown 70,000 against 65,000; "
              "refused to a planner; ported with the clash kept — one purchase row naming its act, one port act; nothing ports into a sandbox")

        # 4 · automatic, and a port that takes the clash
        session.become(FINANCE)
        c.post("/stages/recalc_setting", data={"mode": "automatic", "reason": "test: a weekly cycle"})
        assert OV.mode() == "automatic"
        session.become(SUPPLY)
        prod = next(r["id"] for r in OV.offer(OV_v(SB), OV_v(LV), "sandbox") if r["point"] == "production")
        assert {r["point"]: r["status"] for r in OV.offer(OV_v(SB), OV_v(LV), "sandbox")} == {"production": "clash", "purchase": "same"}
        c.post("/port", data={"from": SB, "to": LV, "take": [prod], f"choose:{prod}": "take", "reason": "test: the sandbox's run length agreed"})
        assert abs(qty(LV)["quantity"] - 70000) < 1e-6 and not any(OV.behind(LV).values())
        price = q("select purchase_price from plan.material_stock where version_id = ? and input_code = ? and plant_code = ? and period = ?", LV, INP, PLANT, PER)[0]["purchase_price"]
        req = q("select sum(quantity) s from plan.material_requirement where version_id = ? and plant_code = ? and period = ?", LV, PLANT, PER)[0]["s"]
        ported = q("select count(*) n from bronze.reg_production_act where version_id = ? and ported_from is not null and ported_from <> ''", LV)[0]["n"]
        assert abs(price - 0.071) < 1e-9 and req > lv_mat_req and ported == 1, (price, req, lv_mat_req, ported)
        assert q("select count(*) n from plan.version_act where act = 'port' and version_id = ?", LV)[0]["n"] == 2
        assert all(r["status"] == "same" for r in OV.offer(OV_v(SB), OV_v(LV), "sandbox"))
        print(f"automatic       set by Finance; the clash taken: after the port {LV} makes 70,000 at once, materials at {PLANT} in {PER} read {req:,.0f} (were {lv_mat_req:,.0f}), "
              f"{INP} at {price}; two port acts on the record; looked at again, both already stand")

        # 5 · Plan → the next Plan, the periods still planned only
        session.become(FINANCE)
        c.post("/versions/name", data={"base_version": BP, "version_id": BSB, "reason": "test: a sandbox of the business plan", "from_period": "2026P12"})
        session.become(SUPPLY)
        c.post(f"/stages/recalc_setting", data={"mode": "manual", "reason": "test"})              # refused: Finance keeps it
        assert OV.mode() == "automatic"
        c.post(f"/supply/plan/type?version={BSB}", data={"key": f"BEANS-CAN_410|ECH", "period": "2027P03", "quantity": "50000", "reason": "test: actual on the next"})
        c.post(f"/supply/plan/type?version={BSB}", data={"key": f"CUP_MIXED-CUP_4x120|{PLANT}", "period": PER, "quantity": "52000", "reason": "test: still planned on the next"})
        ok, says, kind = OV.pair(OV_v(BSB), OV_v(LV))
        offered = OV.offer(OV_v(BSB), OV_v(LV), kind)
        assert ok and kind == "next" and [(r["cell"]["material_code"], r["cell"]["period"], r["status"]) for r in offered] == [("CUP_MIXED-CUP_4x120", PER, "port")], offered
        print(f"next Plan       {BSB} (actual to 2026P12) → {LV} (actual to 2027P04): of two overrides only {PER}'s is offered — 2027P03 is actual on {LV}")
    finally:
        session.become(FINANCE)
        for p in landing_files() - before:
            p.unlink()
        run()
        assert OV.mode() == "manual" and not q("select 1 from dims.ctl_version where version_id in (?, ?)", SB, BSB)
        assert abs(qty(LV)["quantity"] - qty(LV)["proposed"]) < 1e-6
        print("cleaned up      every file the test placed removed and the plan run again — no sandbox, manual, the proposal stands")


def OV_v(vid: str) -> dict:
    from face import reads
    return reads.version(vid) or {}


if __name__ == "__main__":
    main()
