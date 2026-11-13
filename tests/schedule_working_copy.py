"""The opex schedule recalculating as a person types — checked through the routes, end to end, against the warehouse.

    uv run python -m tests.schedule_working_copy        # from build/, with the warehouse built; takes one scoped run

Types a month, a rate and a driver through the endpoint the page's script posts to; checks what comes back and what the
working copy holds (a month holds, driver × rate follows a typed rate, a changed driver keeps the typed months); checks
a second person sees none of it and a person without the verb is refused; resets a typed month after the confirmation
names it; Recalculate leaves typed months alone; then saves, lets the save's run carry it into plan.opex_schedule, and
asserts that every cell of the version is what the page showed before saving. Everything it writes (the save's file,
its receipts) is removed afterwards and the schedule's part of the plan is run again.
"""
from __future__ import annotations

import json
import os
import sys
import time
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
FINANCE, PLANT, OTHER = "finance.manager@caldera", "plant.manager@caldera", "gm@caldera"
LIVE = {"Content-Type": "application/json", "X-Live": "1"}


def main() -> None:
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    landing_before, receipts_before = set(S.LANDING.files()), set(chassis.CONFIG.receipts.glob("*.json"))
    with app.test_request_context():
        V = M.reads.default_version()
        b = S.base(V)
        P = b["inp"].periods
    fy = int(P[0][:4])
    page = {"version": V, "fy": fy, "cc": "CAL", "entity": ""}
    timings: list[float] = []

    def post(cell: str, value) -> dict:
        t = time.perf_counter()
        r = c.post("/schedule/cell", data=json.dumps({"page": page, "cell": cell, "value": str(value)}), headers=LIVE)
        timings.append(time.perf_counter() - t)
        assert r.status_code == 200, r.status_code
        return json.loads(r.data)

    def cell(line: tuple, period: str, who: str = FINANCE) -> dict:
        with app.test_request_context():
            return S.cells_for(who, V)[0][(*line, period)]

    elec = ("RBF", "CC_L_PROD", "6200")           # driven by cases made at Loxton
    repairs = ("CF", "CC_E_MAINT", "6300")         # a flat amount
    travel = ("CF", "CC_SALES", "6950")            # last year
    try:
        session.become(FINANCE)
        c.post("/schedule/discard", data=page)
        assert c.get("/schedule?" + "&".join(f"{k}={v}" for k, v in page.items())).status_code == 200

        # 1 · a month typed holds; the calculated amount stays beneath it; the line's total and the grand total move
        p1 = P[1]
        before = cell(travel, p1)
        reply = post(f"m|{S.line_id(travel)}|{p1}", round(before["amount"] + 5000))
        assert f"sch-l-{S.line_id(travel)}" in reply and "sch-t" in reply and "sch-status" in reply, list(reply)
        now = cell(travel, p1)
        assert now["state"] == "typed" and abs(now["amount"] - round(before["amount"] + 5000)) < 1e-9 and abs(now["amount_calc"] - before["amount_calc"]) < 1e-9
        print(f"month typed     {travel} × {p1}: {before['amount']:,.2f} → {now['amount']:,.2f}, calculated beneath {now['amount_calc']:,.2f}")

        # 2 · a rate typed: every calculated month of the line follows driver × rate at once; a typed month would hold
        p2 = P[2]
        e0 = cell(elec, p2)
        post(f"r|{S.line_id(elec)}", 0.25)
        e1 = cell(elec, p2)
        assert e1["rate"] == 0.25 and abs(e1["amount"] - e1["driver_qty"] * 0.25) < 1e-6 and e1["rate_typed"]
        print(f"rate typed      {elec}: {e0['rate']:.4f} → 0.25; {p2} {e0['amount']:,.2f} → {e1['amount']:,.2f} = {e1['driver_qty']:,.0f} cases × 0.25")

        # 3 · a month on the flat line, then its driver changed: the typed month stays, the rate returns to calculated
        p3 = P[5]                                      # clear of the months typed when the schedule was seeded
        post(f"m|{S.line_id(repairs)}|{p3}", 250000)
        post(f"r|{S.line_id(repairs)}", 200000)
        reply = c.post("/schedule/cell", data={**page, f"d|{S.line_id(repairs)}": "cases_made_ech"})
        assert reply.status_code == 302
        r3 = cell(repairs, p3); r4 = cell(repairs, P[6])
        assert r3["state"] == "typed" and r3["amount"] == 250000 and r4["driver"] == "cases_made_ech" and not r4["rate_typed"]
        assert abs(r4["amount"] - r4["driver_qty"] * r4["rate_calc"]) < 1e-6
        print(f"driver changed  {repairs}: none → cases made at Echuca; the typed {p3} kept at {r3['amount']:,.0f}; the typed rate back to calculated {r4['rate_calc']:.4f}")

        # 4 · a second person sees none of it; a person without the verb is refused at a cost centre outside their scope
        session.become(OTHER)
        assert cell(travel, p1, OTHER)["state"] == "calculated"
        r = c.get("/schedule?" + "&".join(f"{k}={v}" for k, v in page.items()))
        assert b"not saved" not in r.data
        session.become(PLANT)
        reply = post(f"m|{S.line_id(travel)}|{p1}", 1)
        assert "does not hold the right to type a cost centre" in reply.get("sch-status", "") and "schedule.line.enter" not in reply.get("sch-status", ""), reply.get("sch-status")
        reply = post(f"r|{S.line_id(elec)}", 0.3)
        assert "does not hold the right to set a schedule line" in reply.get("sch-status", "")
        print("refused         the plant manager at Sales (outside OPS) and on a rate; the general manager sees none of Finance's changes")
        session.become(FINANCE)
        wages = ("CF", "CC_E_TOM", "6100")
        reply = post(f"m|{S.line_id(wages)}|{p1}", 1)
        assert "filled by the labour model" in reply.get("sch-status", ""), reply.get("sch-status")
        print("refused         a month on a labour line: it is the labour model's, from the headcount and the agreement")

        # 5 · Reset to base: the confirmation names the typed months it removes; confirmed, the month is calculated again
        r = c.get(f"/schedule/reset?line={S.line_id(repairs)}&" + "&".join(f"{k}={v}" for k, v in page.items()))
        assert b"2 typed figures" in r.data and p3.encode() in r.data, r.data[-600:]           # the one typed at onboarding and ours
        c.post("/schedule/reset", data={**page, "line": S.line_id(repairs), "period": [p3]})
        assert cell(repairs, p3)["state"] == "calculated" and cell(repairs, "2027P08")["state"] == "typed"
        post(f"m|{S.line_id(repairs)}|{p3}", 250000)              # typed again, to be saved
        print(f"reset           {repairs} × {p3}: the confirmation named the line's 2 typed figures; the one ticked off is calculated again, the other held")

        # 6 · Recalculate leaves every typed month alone
        with app.test_request_context():
            typed_before = {k for k, x in S.cells_for(FINANCE, V)[0].items() if x["state"] == "typed"}
        c.post("/schedule/recalculate", data=page)
        with app.test_request_context():
            typed_after = {k for k, x in S.cells_for(FINANCE, V)[0].items() if x["state"] == "typed"}
        assert typed_before == typed_after and len(typed_after) >= 4, (typed_before, typed_after)
        print(f"recalculate     {len(typed_after)} typed months before and after")

        # 7 · save: one file, the scoped run; every cell of the version equals the page before saving
        with app.test_request_context():
            shown = {k: (x["amount"], x["amount_calc"], x["rate"], x["state"], x["driver"]) for k, x in S.cells_for(FINANCE, V)[0].items()}
            n = len(S.working_copy(FINANCE, V).acts)
        r = c.post("/schedule/save", data={**page, "reason_code": "OTHER", "note": "test: the page before saving equals the plan after"})
        assert r.status_code == 302
        new = sorted(set(S.LANDING.files()) - landing_before)
        assert len(new) == 1, new
        rows = q("select * from plan.opex_schedule where version_id = ?", V)
        model = {(x["entity_code"], x["cost_centre_code"], x["account_code"], x["period"]): (x["amount"], x["amount_calc"], x["rate"], x["state"], x["driver"]) for x in rows}
        assert set(model) == set(shown), (len(model), len(shown))
        worst = 0.0
        for k, a in shown.items():
            m = model[k]
            assert a[3:] == m[3:], (k, a, m)
            for x, y in zip(a[:3], m[:3]):
                assert (x is None) == (y is None), (k, a, m)
                if x is not None:
                    worst = max(worst, abs(x - y))
        assert worst < 0.005, worst
        print(f"saved           {n} acts, one file ({new[0].name}); after the scoped run every one of {len(model):,} cells equals the page (largest difference {worst:.2e})")
        timings.clear()
        for i in range(5):
            post(f"m|{S.line_id(travel)}|{P[7]}", 40000 + i)
        c.post("/schedule/discard", data=page)
        print(f"per edit, the whole schedule: {', '.join(f'{t * 1000:.0f}' for t in timings)} ms")
    finally:
        for f in set(S.LANDING.files()) - landing_before:
            f.unlink()
        for f in set(chassis.CONFIG.receipts.glob("*.json")) - receipts_before:
            if "schedule" in f.name or "run_" in f.name:
                f.unlink()
        S.COPIES.drop(FINANCE, ("schedule", V))
        with app.test_request_context():
            log = M.Runner(S.RUN).run()
        assert "✗" not in log, log[-800:]
        print("cleaned up: the test's file and receipts removed, the schedule's part of the plan run again")


if __name__ == "__main__":
    main()
