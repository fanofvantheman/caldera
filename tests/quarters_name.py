"""Quarters past the months on Finance's grid, and the Plan's name — through the routes, against the warehouse.

    uv run python -m tests.quarters_name           # from build/, with the warehouse built; takes two runs

DEC-20261118-03 point 7 with DEC-20261113-11 point 8, and DEC-20261119-02:
1. The name: the latest view is `FY27 P05 | FCST 4+8` wherever it is shown with its name (the Plans page, Revenue's header,
   the context block), the rolling reach `4+18+5Q` nowhere in it; the business plan `FY27 P01 | Budget`, and `BUD` gone.
2. The quarters: past eighteen periods `F202705` runs to 2029P12 in quarters — FY28 Q4 (P11–P12, a part quarter) and FY29
   Q1–Q4 — and the business plan has none. Each quarter column on Revenue's grid is the sum of its periods; cost of goods
   is empty there (the cost side plans the months).
3. A volume typed on a quarter: its periods take it by the demand plan's shape, nothing else moves, one step and one mark;
   a period past the months typed straight is refused, and a quarter outside the horizon. Saved: three period figures in
   force after the run, the quarter in Finance's plan reading the figure. Removed and run again.
"""
from __future__ import annotations

import json
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
from face import finance_live as FL                   # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
FINANCE = "finance.manager@caldera"
LV, BP = "F202705", "B202701"
LIVE = {"Content-Type": "application/json", "X-Live": "1"}
RUN = [["uv", "run", "python", "-m", "ingest.pipeline"], ["uv", "run", "sqlmesh", "plan", "prod", "--restate-model", "*", "--auto-apply", "--no-prompts"]]


def run() -> None:
    for cmd in RUN:
        r = subprocess.run(cmd, cwd=BUILD, capture_output=True, text=True)
        assert r.returncode == 0 and "Error" not in r.stdout[-2000:], (cmd, r.stdout[-1500:], r.stderr[-1500:])


def num(s: str) -> float:
    return float(s.replace(",", "").split()[0])


def main() -> None:
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    session.become(FINANCE)
    # 1 · the name
    codes = M.reads.plan_codes()
    assert codes[LV] == ("FY27 P05", "FY27 P05 | FCST 4+8") and codes[BP] == ("FY27 P01 | Budget", "FY27 P01 | Budget"), codes
    plans = c.get("/versions").data.decode()
    rev = c.get(f"/revenue?version={LV}&measure=volume").data.decode()
    for h in (plans, rev):
        assert "FY27 P05 | FCST 4+8" in h and "4+18" not in h and "BUD" not in h
    assert "FY27 P01 | Budget" in plans and "18 periods, to 2028P10; then 5 quarters" in plans, "the rolling reach stays on the Plans page"
    print("name           FY27 P05 | FCST 4+8 on the Plans page, Revenue's header and the context block; FY27 P01 | Budget; the reach (18 periods, then 5 quarters) on the Plans page only")

    # 2 · the quarters
    with app.test_request_context():
        vp, bp = M.reads.version_periods(LV), M.reads.version_periods(BP)
    qs = [(x["label"], x["periods"]) for x in vp["quarter_cols"]]
    assert qs == [("FY28 Q4", ["2028P11", "2028P12"]), ("FY29 Q1", ["2029P01", "2029P02", "2029P03"]), ("FY29 Q2", ["2029P04", "2029P05", "2029P06"]),
                  ("FY29 Q3", ["2029P07", "2029P08", "2029P09"]), ("FY29 Q4", ["2029P10", "2029P11", "2029P12"])] and not bp["quarter_cols"], qs
    page = {"version": LV, "fy": 2027, "customer": "ALL", "material": "ALL", "measure": "volume"}
    c.post("/finance/discard", data=page)
    with app.test_request_context():
        fin = M._finance_ctx(LV, 2027, page, who=FINANCE)
        base = FL.base(LV, M.FINANCE)[1]
    idx = {p["period"]: i for i, p in enumerate(fin["periods"])}
    top = fin["rows"][0]
    for x in vp["quarter_cols"]:
        want = sum(FL.node_value(base, LV, "ALL", "ALL", per, "volume") or 0 for per in x["periods"])
        got = num(top["cells"]["volume"][idx[x["id"]]]["show"])
        assert abs(got - want) <= 0.5, (x["id"], got, want)
        assert top["cells"]["volume"][idx[x["id"]]]["input"] == f"v|ALL|{x['id']}", "a quarter takes a figure"
    with app.test_request_context():
        cogs = M._finance_ctx(LV, 2027, {**page, "measure": "cogs"}, who=FINANCE)
    ci = {p["period"]: i for i, p in enumerate(cogs["periods"])}
    assert all(not cogs["rows"][0]["cells"]["cogs"][ci[x["id"]]]["show"] for x in vp["quarter_cols"]), "cost of goods plans the months"
    assert "then 5 quarters to 2029P12" in rev
    print(f"quarters       F202705: {', '.join(l for l, _ in qs)} to 2029P12 (FY28 Q4 two periods); each column the sum of its periods; cost of goods empty there; the business plan none")

    # 3 · a volume typed on a quarter
    mark = set(chassis.CONFIG.landing.rglob("*.csv"))
    def post(node, period, value):
        r = c.post("/finance/cell", data=json.dumps({"page": page, "node": node, "period": period, "measure": "volume", "value": str(value)}), headers=LIVE)
        assert r.status_code == 200
        return r.get_json()
    try:
        Q = vp["quarter_cols"][2]                                    # FY29 Q2
        before = {per: FL.node_value(base, LV, "ALL", "ALL", per, "volume") for per in vp["plan"] + [p for x in vp["quarter_cols"] for p in x["periods"]]}
        q0 = sum(before[p] for p in Q["periods"])
        target = round(q0 * 1.1)
        post("ALL", Q["id"], target)
        with app.test_request_context():
            wc = FL.working_copy(FINANCE, LV, M.FINANCE)
        after = {per: FL.node_value(wc.grid, LV, "ALL", "ALL", per, "volume") for per in before}
        assert abs(sum(after[p] for p in Q["periods"]) - target) < 1e-3
        for p in Q["periods"]:
            assert abs(after[p] - before[p] * target / q0) < 1.0, (p, after[p], before[p] * target / q0)    # the demand plan's shape
        assert all(abs((after[p] or 0) - (before[p] or 0)) < 1e-6 for p in before if p not in Q["periods"]), "nothing outside the quarter moves"
        steps = wc.history.done
        assert len(steps) == 1 and len(steps[0]) == 3 and all(t.span == Q["id"] for t in steps[0])
        h = c.get(f"/revenue?version={LV}&measure=volume").data.decode()
        assert f"for {Q['id']}" in h or "FY29 Q2" in h[h.index('id="fin-steps"'):][:600]
        r1 = post("ALL", "2029P05", 1)                               # a period past the months, straight
        r2 = post("ALL", "2030Q1", 1)                                # a quarter past the horizon
        assert "not a plan period" in json.dumps(r1) and "not a quarter" in json.dumps(r2), (str(r1)[:300], str(r2)[:300])
        print(f"quarter typed  FY29 Q2 at all materials: {q0:,.0f} → {target:,}; its three periods by the demand plan's shape, nothing else moved; one step; "
              "a period past the months and a quarter past the horizon refused")
        reason = next(r["reason_code"] for r in M.reads.finance_reasons() if not r.get("note_required"))
        c.post("/finance/save", data={**page, "reason_code": reason, "note": "test: a quarter"})
        st = q("select period, state from plan.finance_edit where version_id = ? and period in (?, ?, ?) and entered_on >= current_date::TEXT", LV, *Q["periods"])
        assert sorted(r["period"] for r in st) == Q["periods"] and {r["state"] for r in st} == {"in_force"}, st
        got = q("select sum(cases) s from plan.finance_plan where version_id = ? and period in (?, ?, ?)", LV, *Q["periods"])[0]["s"]
        assert abs(got - target) < 0.5, (got, target)
        print(f"quarter saved  three period figures in force after the run; Finance's plan reads {got:,.0f} for FY29 Q2")
    finally:
        c.post("/finance/discard", data=page)
        new = set(chassis.CONFIG.landing.rglob("*.csv")) - mark
        for p in new:
            p.unlink()
        if new:
            run()
        print("cleaned up     the save removed and the plan run again" if new else "cleaned up     nothing was saved")


if __name__ == "__main__":
    main()
