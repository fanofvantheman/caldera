"""The capital plan — checked through the routes and against the warehouse.

    uv run python -m tests.capex_plan        # from build/, with the warehouse built; takes two scoped runs

1. The page answers for a holder of the project-entry right and for a reader; the reader is offered no form.
2. Every asset as loaded opens the latest view's first plan period at its book value as loaded (the register's date is
   the latest view's from point), and every item's book value walks: opening + additions − depreciation = closing, and the
   next period opens where this one closed.
3. Units of production: the second filler's depreciation in a period is (cost − residual) × the cases made at Echuca ÷
   its lifetime cases.
4. The opex schedule's depreciation and lease lines are the capital plan's charge, cell for cell, filled by the capital
   plan and refused to anyone typing them.
5. A project entered through the page is refused outside the person's cost centres and with its spend out of order; one
   entered by Finance at IT is placed, run, and moves IT's depreciation line by its own depreciation and nothing else; it
   is withdrawn through the page and the schedule is back cell for cell. Everything it writes is removed afterwards.
"""
from __future__ import annotations

import json
import os
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
from face import capex as C                           # noqa: E402
from face import schedule as S                        # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
FINANCE, PLANT, READER = "finance.manager@caldera", "plant.manager@caldera", "board.pack@caldera"
LIVE = {"Content-Type": "application/json", "X-Live": "1"}


def close(a, b, tol=0.01) -> bool:
    return abs((a or 0) - (b or 0)) <= tol


def main() -> None:
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    landing_before, receipts_before = set(C.LANDING.files()), set(chassis.CONFIG.receipts.glob("*.json"))
    with app.test_request_context():
        V = M.reads.default_version()
    try:
        # 1 · the page
        session.become(FINANCE)
        r = c.get(f"/capex?version={V}")
        assert r.status_code == 200 and b"Projects and depreciation" in r.data and b'action="/capex/enter' in r.data, r.status_code
        session.become(READER)
        r = c.get(f"/capex?version={V}")
        assert r.status_code == 200 and b'action="/capex/enter' not in r.data
        print(f"page            answers for {FINANCE} with the entry form, for {READER} without it")

        # 2 · the register as loaded opens the plan, and every book value walks
        first = q("select min(period) p from plan.capex_line where version_id = ?", V)[0]["p"]
        for a in q("select a.*, l.opening_nbv from dims.reg_asset a join plan.capex_line l on l.item_id = a.asset_id and l.version_id = ? and l.period = ?", V, first):
            assert close(a["opening_nbv"], a["cost"] - a["accumulated"]), (a["asset_id"], a["opening_nbv"], a["cost"] - a["accumulated"])
        bad = q("""select item_id, period from (select *, lag(closing_nbv) over (partition by version_id, item_id order by period) prev from plan.capex_line)
                   where abs(opening_nbv + additions - depreciation - closing_nbv) > 0.01 or (prev is not null and abs(prev - opening_nbv) > 0.01)""")
        assert not bad, bad[:3]
        n = q("select count(*) n from plan.capex_line")[0]["n"]
        print(f"book value      every asset opens {first} at cost − accumulated as loaded; all {n:,} rows walk (opening + additions − depreciation = closing)")

        # 3 · units of production
        cls = q("select * from dims.ref_asset_class where asset_class = 'LINE'")[0]
        tom2 = q("select * from plan.capex_item where version_id = ? and item_id = 'P-E-TOM2' and standing = 'stands'", V)[0]
        rows = q("""select l.period, l.depreciation, l.units from plan.capex_line l where l.version_id = ? and l.item_id = 'P-E-TOM2' and l.period >= ?
                    order by l.period""", V, tom2["in_service_period"])
        made = {r["period"]: r["q"] for r in q("""select d.period, sum(d.cases) q from plan.demand_financialised d join dims.ref_route r using (material_code)
                                                   where r.is_primary and r.plant_code = 'ECH' and d.version_id = ? group by 1""", V)}
        for r in rows:
            want = tom2["spend"] * (1 - cls["residual_pct"]) * made[r["period"]] / tom2["lifetime_units"]
            assert close(r["depreciation"], want), (r, want)
        print(f"units of prod.  {tom2['item_name']}: {len(rows)} periods, each (cost − residual) × Echuca's cases ÷ {tom2['lifetime_units']:,.0f}")

        # 4 · the schedule's lines are the capital plan's charge, and nobody types them
        charge = {(x["entity_code"], x["cost_centre_code"], x["account_code"], x["period"]): x["amount"]
                  for x in q("select * from plan.capex_charge where version_id = ?", V)}
        cells = {(x["entity_code"], x["cost_centre_code"], x["account_code"], x["period"]): x for x in q("select * from plan.opex_schedule where version_id = ? and driver = 'capex_model'", V)}
        assert cells and all(close(x["amount"], charge.get(k)) and x["state"] == "model" for k, x in cells.items())
        assert all(k in cells for k in charge if k[3] in {x[3] for x in cells}), "a charge the schedule does not carry"
        line = next(iter(cells))[:3]
        session.become(FINANCE)
        page = {"version": V, "fy": 0, "cc": line[1], "entity": ""}
        reply = json.loads(c.post("/schedule/cell", data=json.dumps({"page": page, "cell": f"m|{S.line_id(line)}|{next(iter(cells))[3]}", "value": "1"}), headers=LIVE).data)
        assert "capital plan" in reply.get("sch-status", ""), reply.get("sch-status")
        c.post("/schedule/discard", data=page)
        print(f"schedule        {len(cells)} cells on {len({k[:3] for k in cells})} lines are the capital plan's charge, cent for cent; typing one is refused")

        # 5 · entering and withdrawing a project through the page
        plan_p = M.reads.version_periods(V)["plan"]
        form = {"kind": "project", "item_name": "Test — warehouse scanners", "project_kind": "growth", "asset_class": "IT", "spend": "480000",
                "spend_from": plan_p[1], "spend_to": plan_p[2], "in_service_period": plan_p[3], "life_years": "", "note": "a test"}
        session.become(PLANT)
        c.post("/capex/enter", data={**form, "cc": "CF|CC_IT"})
        assert session.last and not session.last["placed"], "a plant manager entered at IT"
        session.become(FINANCE)
        c.post("/capex/enter", data={**form, "cc": "CF|CC_IT", "spend_from": plan_p[3], "spend_to": plan_p[1]})
        assert not session.last["placed"] and any(not x["ok"] and x["check"] == "spend periods in order" for x in session.last["checks"])
        print("refused         a plant manager at IT; spend periods out of order")
        before = {(x["entity_code"], x["cost_centre_code"], x["account_code"], x["period"]): x["amount"] for x in q("select * from plan.opex_schedule where version_id = ?", V)}
        c.post("/capex/enter", data={**form, "cc": "CF|CC_IT"})
        assert session.last["placed"], session.last["checks"]
        item = q("select item_id from plan.capex_item where version_id = ? and item_name = ? and standing = 'stands'", V, form["item_name"])
        assert item, "the project is not in the plan after the run"
        dep = {x["period"]: x["depreciation"] for x in q("select period, depreciation from plan.capex_line where version_id = ? and item_id = ?", V, item[0]["item_id"])}
        after = {(x["entity_code"], x["cost_centre_code"], x["account_code"], x["period"]): x["amount"] for x in q("select * from plan.opex_schedule where version_id = ?", V)}
        moved = {k for k in set(before) | set(after) if not close(before.get(k), after.get(k), 1e-6)}
        assert moved and all(k[:3] == ("CF", "CC_IT", "6750") for k in moved), sorted(moved)[:5]
        assert all(close(after[k] - before.get(k, 0), dep.get(k[3])) for k in moved)
        print(f"entered         {item[0]['item_id']}: IT's depreciation moved in {len(moved)} periods by the project's own, {sum(dep.values()):,.0f}; nothing else moved")
        c.post("/capex/withdraw", data={"item_id": item[0]["item_id"], "reason": "test"})
        assert session.last["placed"], session.last["checks"]
        back = {(x["entity_code"], x["cost_centre_code"], x["account_code"], x["period"]): x["amount"] for x in q("select * from plan.opex_schedule where version_id = ?", V)}
        assert set(back) == set(before) and all(close(back[k], before[k], 1e-6) for k in before)
        print(f"withdrawn       the schedule is back, all {len(before):,} cells as before")
    finally:
        for f in set(C.LANDING.files()) - landing_before:
            f.unlink()
        for f in set(chassis.CONFIG.receipts.glob("*.json")) - receipts_before:
            if "capex" in f.name or "run_" in f.name:
                f.unlink()
        with app.test_request_context():
            log = M.run_waiting()
        assert "✗" not in log, log[-800:]
        print("cleaned up: the test's files and receipts removed, the capital plan run again")


if __name__ == "__main__":
    main()
