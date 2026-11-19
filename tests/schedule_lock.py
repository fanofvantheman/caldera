"""A schedule month adjusted or locked (DEC-20261115-05) — checked through the routes, end to end, against the warehouse.

    uv run python -m tests.schedule_lock        # from build/, with the warehouse built; takes one scoped run

1. What was typed before stands as typed: every month act on file is a locked month at its figure, nothing moved.
2. A figure typed is an adjustment: the month follows its driver — a rate typed moves it, with the adjustment on top.
3. The lock is a tick: a locked month holds when the rate moves again, the calculated amount beneath it and ◆ once it
   has moved; typing into it keeps it locked at the new figure; unticking returns it to its driver with its adjustment.
4. A person without the month's right is refused the tick.
5. Reset to base removes the adjustment and the lock together.
6. Saved, the scoped run makes every cell what the page showed — states, adjustments and amounts.
Everything it writes is removed afterwards and the schedule's part of the plan is run again.
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
from face import schedule as S                        # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
FINANCE, PLANT = "finance.manager@caldera", "plant.manager@caldera"
LIVE = {"Content-Type": "application/json", "X-Live": "1"}


def main() -> None:
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    landing_before, receipts_before = set(S.LANDING.files()), set(chassis.CONFIG.receipts.glob("*.json"))
    with app.test_request_context():
        V = M.reads.default_version()
        P = S.base(V)["inp"].periods
    elec = ("RBF", "CC_L_PROD", "6200")                # driven by cases made at Loxton
    page = {"version": V, "fy": 0, "cc": elec[1], "entity": ""}

    def post(cell: str, value) -> dict:
        r = c.post("/schedule/cell", data=json.dumps({"page": page, "cell": cell, "value": str(value)}), headers=LIVE)
        assert r.status_code == 200, r.status_code
        return json.loads(r.data)

    def cell(line: tuple, period: str) -> dict:
        with app.test_request_context():
            return S.cells_for(FINANCE, V)[0][(*line, period)]

    try:
        # 1 · the carry-over: every month typed before is locked at its figure
        acts = q("select * from plan.schedule_edit where version_id = ? and action = 'month' and withdrawn_by_act is null", V)
        for a in acts:
            x = q("""select state, amount from plan.opex_schedule where version_id = ? and entity_code = ? and cost_centre_code = ? and account_code = ?
                     and period = ?""", V, a["entity_code"], a["cost_centre_code"], a["account_code"], a["period"])[0]
            assert x["state"] == "locked" and abs(x["amount"] - a["value"]) < 1e-9, (a, x)
        print(f"carried over    {len(acts)} months typed before are locked at the figures typed")

        session.become(FINANCE)
        c.post("/schedule/discard", data=page)
        p = P[3]
        e0 = cell(elec, p)
        # 2 · typed: an adjustment, and the month follows the driver
        post(f"m|{S.line_id(elec)}|{p}", round(e0["amount"] + 10_000))
        e1 = cell(elec, p)
        assert e1["state"] == "adjusted" and abs(e1["adjustment"] - (round(e0["amount"] + 10_000) - e0["amount_calc"])) < 1e-6
        post(f"r|{S.line_id(elec)}", 0.30)
        e2 = cell(elec, p)
        assert abs(e2["amount_calc"] - e2["driver_qty"] * 0.30) < 1e-6 and abs(e2["amount"] - (e2["amount_calc"] + e1["adjustment"])) < 1e-6
        print(f"adjusted        {p}: {e0['amount']:,.0f} typed to {e1['amount']:,.0f} (adj {e1['adjustment']:+,.0f}); the rate to 0.30 moves it to {e2['amount']:,.0f}")

        # 3 · the lock holds; typing into it keeps it locked; unticking returns it to the driver with its adjustment
        reply = post(f"k|{S.line_id(elec)}|{p}", "1")
        assert f"sch-l-{S.line_id(elec)}" in reply and "checked" in reply[f"sch-l-{S.line_id(elec)}"]
        e3 = cell(elec, p)
        assert e3["state"] == "locked" and abs(e3["amount"] - e2["amount"]) < 1e-6
        post(f"r|{S.line_id(elec)}", 0.40)
        e4 = cell(elec, p)
        assert e4["state"] == "locked" and abs(e4["amount"] - e3["amount"]) < 1e-6 and abs(e4["amount_calc"] - e4["driver_qty"] * 0.40) < 1e-6 and e4["moved"]
        post(f"m|{S.line_id(elec)}|{p}", 99_000)
        e5 = cell(elec, p)
        assert e5["state"] == "locked" and e5["amount"] == 99_000
        post(f"k|{S.line_id(elec)}|{p}", "")
        e6 = cell(elec, p)
        assert e6["state"] == "adjusted" and abs(e6["amount"] - (e6["amount_calc"] + e1["adjustment"])) < 1e-6
        print(f"locked          held at {e3['amount']:,.0f} when the rate moved to 0.40 (calculated {e4['amount_calc']:,.0f} ◆); typed 99,000 and still locked; "
              f"unticked, back to its driver with its adjustment: {e6['amount']:,.0f}")

        # 4 · a person without the month's right at the cost centre is refused the tick
        session.become("gm@caldera")
        reply = post(f"k|{S.line_id(elec)}|{P[4]}", "1")
        assert "does not hold" in reply.get("sch-status", ""), reply.get("sch-status")
        session.become(FINANCE)
        print("refused         the tick, to someone without the right at the cost centre")

        # 5 · reset removes adjustment and lock together
        post(f"k|{S.line_id(elec)}|{P[5]}", "1")
        c.post("/schedule/reset", data={**page, "line": S.line_id(elec), "period": [p, P[5]]})
        assert cell(elec, p)["state"] == "calculated" and cell(elec, P[5])["state"] == "calculated" and cell(elec, p)["adjustment"] is None
        post(f"m|{S.line_id(elec)}|{p}", round(cell(elec, p)["amount"] + 2_500))      # adjusted again,
        post(f"k|{S.line_id(elec)}|{P[6]}", "1")                                           # and another locked, to be saved
        print("reset           an adjusted and a locked month back to driver × rate in one confirmation")

        # 6 · save: the plan after the run is the page before it
        with app.test_request_context():
            shown = {k: (x["state"], x["amount"], x["adjustment"]) for k, x in S.cells_for(FINANCE, V)[0].items()}
        r = c.post("/schedule/save", data={**page, "reason_code": "OTHER", "note": "test: adjusted and locked"})
        assert r.status_code == 302
        model = {(x["entity_code"], x["cost_centre_code"], x["account_code"], x["period"]): (x["state"], x["amount"], x["adjustment"])
                 for x in q("select * from plan.opex_schedule where version_id = ?", V)}
        assert set(model) == set(shown)
        for k, a in shown.items():
            m = model[k]
            assert a[0] == m[0] and abs((a[1] or 0) - (m[1] or 0)) < 0.005 and (a[2] is None) == (m[2] is None), (k, a, m)
        n = sum(1 for x in model.values() if x[0] in ("adjusted", "locked"))
        print(f"saved           after the scoped run all {len(model):,} cells are what the page showed; {n} adjusted or locked")
        st = {x["act"] for x in q("select act from plan.change_record where record = 'opex schedule' and standing = 'stands' and version_id = ?", V)}
        assert {"adjust", "lock"} <= st, st
    finally:
        for f in set(S.LANDING.files()) - landing_before:
            f.unlink()
        for f in set(chassis.CONFIG.receipts.glob("*.json")) - receipts_before:
            if "schedule" in f.name or "run_" in f.name:
                f.unlink()
        S.COPIES.drop(FINANCE, ("schedule", V))
        with app.test_request_context():
            log = M.run_waiting()
        assert "✗" not in log, log[-800:]
        print("cleaned up: the test's file and receipts removed, the schedule's part of the plan run again")


if __name__ == "__main__":
    main()
