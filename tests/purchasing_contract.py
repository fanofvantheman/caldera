"""The purchasing plan held apart from the Plan (DEC-20261120-04) — the smallest round trip, through the app and the
runs; everything it writes is removed again (three runs).

    uv run python -m tests.purchasing_contract        # from build/, with the warehouse built

1. One receipt typed in the purchasing plan moves its balance and nothing in the Plan.
2. Published, it arrives in the Plan's register; after the run the Plan carries it as typed, proposes the rest again
   from its own consumption, and Material stock shows the balance.
3. Consumption moved upstream (a production quantity typed) changes nothing in the purchasing plan until its planner
   takes the new revision, and the page says it is behind; taken, the balance reads it.
4. The same receipt from a spreadsheet leaves the Plan's figures as they were: only where it came from differs.
"""
from __future__ import annotations

import io
import os
import shutil
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
from face import purchasing_plan as W                 # noqa: E402
from face import supply as FS                         # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
LV, INP, PLANT, PER = "F202705", "TOMATO", "ECH", "2027P10"
BUYER = "supply.planner@caldera"


def cell(rows, inp=INP, plant=PLANT, per=PER) -> dict:
    return next(r for r in rows if r["input_code"] == inp and r["plant_code"] == plant and r["period"] == per)


def plan_cell() -> dict:
    return q("select * from plan.material_stock where version_id = ? and input_code = ? and plant_code = ? and period = ?", LV, INP, PLANT, PER)[0]


def main() -> None:
    data = BUILD / "data"
    made = [data / "workspaces" / "purchasing" / LV, data / "shared"]
    before = {p for p in (data / "landing").rglob("*.csv")}
    had = {p: p.exists() for p in made}
    if any(had.values()):
        sys.exit("a purchasing workspace or shared store already exists — this test starts from none")
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    session.become(BUYER)
    try:
        # 1 · typed in the workspace: its balance moves, the Plan does not
        assert c.get(f"/supply/purchases?version={LV}").status_code == 200
        ws0, st = W.balance(LV, BUYER)
        p0 = plan_cell()
        x0 = cell(ws0)
        typed_qty = round(x0["additional_quantity"] + 500)
        c.post("/supply/purchases/type", data={"version": LV, "reason": "a second grower", f"additional_quantity|{INP}~{PLANT}|{PER}": str(typed_qty)})
        ws1, _ = W.balance(LV, BUYER)
        x1 = cell(ws1)
        assert x1["quantity_typed"] and x1["additional_quantity"] == typed_qty, x1
        assert abs(x1["closing_quantity"] - x0["closing_quantity"] - (typed_qty - x0["additional_quantity"])) < 1e-6
        assert {p for p in (data / "landing").rglob("*.csv")} == before, "typing in the workspace wrote to the landing"
        assert plan_cell() == p0
        print(f"workspace       {INP} at {PLANT} in {PER}: {typed_qty:,} typed — the purchasing plan's closing moves by {typed_qty - x0['additional_quantity']:,.0f}; the landing and the Plan untouched")

        # 2 · published: the Plan carries it as typed, proposes the rest again, shows the balance
        c.post("/supply/purchases/publish", data={"version": LV})
        arr = W.arrivals(LV, 1)[0]
        assert arr["placed"] and arr["source"] == "the purchasing plan" and arr["made_against"] == st["pin"]["consumption"] and len(arr["taken"]) == 1, arr
        assert all(r["published"] for r in W.typed(LV))
        M.run_waiting()
        p1 = plan_cell()
        assert p1["quantity_typed"] and p1["additional_quantity"] == typed_qty, p1
        rows = q("select * from plan.material_stock where version_id = ? and input_code = ? and plant_code = ? order by period", LV, INP, PLANT)
        for a, b in zip(rows, rows[1:]):
            assert abs(a["closing_quantity"] - b["opening_quantity"]) < 1e-6
        others = [r for r in rows if r["period"] != PER]
        assert not any(r["quantity_typed"] for r in others) and all(abs(r["additional_quantity"]) < 1e-9 for r in others)
        html = c.get(f"/costs/material_stock?version={LV}&f_material={INP}").data.decode()
        assert "published into the Plan" in html and "the purchasing plan" in html
        print(f"published       one receipt arrived (made against {arr['made_against']}); after the run the Plan carries {p1['additional_quantity']:,.0f} typed, its other periods proposed again; Material stock shows it")

        # 3 · consumption moves upstream: nothing here moves until taken
        revs = W.revisions(LV)
        pr = q("""select p.material_code, p.quantity from plan.production_requirement p join dims.ref_bom b on b.parent_material = p.material_code and b.plant_code = p.plant_code
                  where p.version_id = ? and p.plant_code = ? and p.period = ? and b.component_material = ? order by p.quantity desc limit 1""", LV, PLANT, PER, INP)[0]
        FS.ACTS.place([{"act_id": "PRD-TEST-CONTRACT", "action": "set", "withdraws": "", "version_id": LV, "material_code": pr["material_code"], "plant_code": PLANT,
                        "period": PER, "quantity": pr["quantity"] * 2 + 1000, "reason": "test", "entered_by": BUYER, "entered_at": "2026-11-20T00:00:00"}], BUYER)
        M.run_waiting()
        assert len(W.revisions(LV)) == len(revs) + 1, "the run published no new revision"
        ws2, st2 = W.balance(LV, BUYER)
        assert st2["behind"] and cell(ws2)["consumption_quantity"] == x1["consumption_quantity"]
        assert "later consumption" in c.get(f"/supply/purchases?version={LV}").data.decode()
        c.post("/supply/purchases/take", data={"version": LV, "revision": st2["latest"]["revision"]})
        ws3, st3 = W.balance(LV, BUYER)
        req = q("select quantity from plan.material_requirement where version_id = ? and input_code = ? and plant_code = ? and period = ?", LV, INP, PLANT, PER)[0]["quantity"]
        assert not st3["behind"] and abs(cell(ws3)["consumption_quantity"] - req) < 1e-6 and req > x1["consumption_quantity"]
        print(f"pinned          consumption moved to {req:,.0f}: the purchasing plan still read {x1['consumption_quantity']:,.0f} and said it was behind; taken, it reads {req:,.0f}")

        # 4 · the same receipt from a spreadsheet: the Plan's figures as they were
        p2 = plan_cell()
        sheet = f"input_code,plant_code,period,quantity,price,reason\n{INP},{PLANT},{PER},{typed_qty},,a second grower\n{INP},{PLANT},2026P01,10,,too early\n"
        c.post("/supply/purchases/sheet", data={"version": LV, "sheet": (io.BytesIO(sheet.encode()), "receipts.csv")}, content_type="multipart/form-data")
        arr = W.arrivals(LV, 1)[0]
        assert arr["placed"] and arr["source"] == "a spreadsheet" and len(arr["taken"]) == 1 and len(arr["dropped"]) == 1 and not arr["clashes"], arr
        M.run_waiting()
        p3 = plan_cell()
        assert all(p3[k] == p2[k] for k in p3 if k != "typed_act"), {k: (p2[k], p3[k]) for k in p3 if p3[k] != p2[k]}
        acts = q("select act_id from plan.purchase_act where version_id = ? and input_code = ? and plant_code = ? and period = ?", LV, INP, PLANT, PER)
        assert acts[0]["act_id"].startswith("SHT-")
        print("spreadsheet     the same receipt from a spreadsheet (a period not planned dropped): the Plan's balance unchanged, only its source differs")
    finally:
        for p in {p for p in (data / "landing").rglob("*.csv")} - before:
            p.unlink()
        for p in made:
            if p.exists() and not had[p]:
                shutil.rmtree(p)
        M.run_waiting()
        for p in made:                                # the clean-up run publishes again: take that out too
            if p.exists() and not had[p]:
                shutil.rmtree(p)
    print("removed         every file written; the run after it leaves the Plan as it was")


if __name__ == "__main__":
    main()
