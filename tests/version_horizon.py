"""Which periods are actual is the version's to say, not the calendar's — checked through the routes, against the warehouse.

    uv run python -m tests.version_horizon              # from build/, with the warehouse built; no run, nothing saved

Checks that the grids' periods come from the version — its actual periods of the year it is named for, then the plan for
its horizon, past the year end — on Finance's grid, the opex schedule (its own shorter window, never longer than the
version's) and the demand plan; that an actual period is refused for entry by the server on Finance's grid, the schedule
and the demand plan, for a holder of the verb, and that a year or a period past the horizon is refused too; that the
finance calculation itself writes nothing into an actual period; and that a figure typed on a total spreads over plan
periods only. Nothing is saved: the working copies are discarded and any receipt the refusals wrote is removed.
"""
from __future__ import annotations

import json
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

from face import SHELL, roles, session                # noqa: E402
from face import __main__ as M                        # noqa: E402
from face import finance_live as FL                   # noqa: E402
from face import schedule as S                        # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
FINANCE = "finance.manager@caldera"
LIVE = {"Content-Type": "application/json", "X-Live": "1"}


def main() -> None:
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    receipts_before = set(chassis.CONFIG.receipts.glob("*.json"))
    landing_before = set(M.ENTRIES.files()) | set(M.FINANCE.files()) | set(S.LANDING.files())
    with app.test_request_context():
        V = M.reads.default_version()
        v = M.reads.version(V)
        vp = M.reads.version_periods(V)
        fy = int(v["fiscal_year"])
        every = [r["period"] for r in q("select period from dims.dim_period order by period")]
    try:
        session.become(FINANCE)
        # 1 · the version says which periods are actual and how far the plan runs; the calendar is not asked
        upto, n = v["from_period"], int(v["horizon_periods"])
        assert vp["from"] == upto and vp["actual"] == [p for p in every if p[:4] == str(fy) and p <= upto], vp["actual"]
        assert vp["plan"] == [p for p in every if p > upto][:n] and vp["plan"][-1] == v["plan_through"] <= v["horizon_end"], vp["plan"]
        assert any(int(p[:4]) > fy for p in vp["plan"]), "the horizon runs past the year end"
        print(f"version         {V}: actual {vp['actual'][0]}–{vp['actual'][-1]}, plan {vp['plan'][0]}–{vp['plan'][-1]} ({n} periods)")

        # 2 · Finance's grid shows exactly those periods, the actual ones marked and without an input, the year after its last
        page = {"version": V, "fy": fy, "customer": "ALL", "material": "ALL", "measure": "volume"}
        html = c.get("/revenue?" + "&".join(f"{k}={x}" for k, x in page.items())).get_data(as_text=True)
        head = re.search(r"<thead>(.*?)</thead>", html, re.S).group(1)
        n_actual_th = len(re.findall(r'<th class="n actual"', head))
        n_th = len(re.findall(r"<th class=\"n", head))
        assert n_actual_th == len(vp["actual"]) and n_th == len(vp["actual"]) + len(vp["plan"]) + 1, (n_actual_th, n_th)
        inputs = set(re.findall(r'name="v\|[^|"]+\|(\d{4}P\d{2})"', html))
        assert inputs and inputs <= set(vp["plan"]) and not inputs & set(vp["actual"]), sorted(inputs)
        print(f"finance grid    {n_th} columns: {n_actual_th} actual (no input), {len(vp['plan'])} plan, the year; inputs only in plan periods")

        # 3 · the schedule plans its own window — the lesser of its step's and the version's — from the version's from point
        step = int(q("select horizon_periods from dims.ref_step_horizon where step = 'opex_schedule'")[0]["horizon_periods"])
        with app.test_request_context():
            sp = S.base(V)["inp"].periods
            win = S.base(V)["inp"].window
        assert sp == vp["plan"][:min(step, n)] and win[-1] == upto, (sp, win)
        print(f"opex schedule   plans {sp[0]}–{sp[-1]} ({len(sp)} = min({step}, {n})); its rates over {win[0]}–{win[-1]}")

        # 4 · an actual period is refused by the server — on Finance's grid, the schedule and the demand plan
        cat = q("select descendant_code c from dims.dim_material_hierarchy where ancestor_code = 'ALL' and depth = 1 order by 1 limit 1")[0]["c"]
        def fin_post(node, period, value=1000):
            r = c.post("/finance/cell", data=json.dumps({"page": page, "node": node, "period": period, "measure": "volume", "value": str(value)}), headers=LIVE)
            assert r.status_code == 200, r.status_code
            return r.get_data(as_text=True)
        c.post("/finance/discard", data=page)
        for period, says in ((vp["actual"][1], "an actual period"), (f"FY{fy}", "not a plan period"),
                             (next(p for p in every if p > vp["plan"][-1]), "not a plan period")):
            reply = fin_post(cat, period)
            assert says in reply, (period, reply[:400])
            with app.test_request_context():
                wc = FL.working_copy(FINANCE, V, M.FINANCE)
            assert wc is None or not wc.typed, period
        print(f"refused         Finance's grid: {vp['actual'][1]} (actual), FY{fy} (a year), the period after {vp['plan'][-1]} (past the horizon)")

        travel = ("CF", "CC_SALES", "6950")
        r = c.post("/schedule/cell", data=json.dumps({"page": {"version": V, "fy": fy, "cc": "CAL", "entity": ""},
                                                       "cell": f"m|{S.line_id(travel)}|{vp['actual'][2]}", "value": "1234"}), headers=LIVE)
        assert r.status_code == 200 and "an actual period" in r.get_data(as_text=True), r.get_data(as_text=True)[:400]
        with app.test_request_context():
            assert not (S.working_copy(FINANCE, V) and S.working_copy(FINANCE, V).acts)
        print(f"refused         the opex schedule: {vp['actual'][2]} on {travel}")

        planner = q("""select principal from dims.effective_entitlements where action = 'layer.2.enter' order by principal limit 1""")[0]["principal"]
        session.become(planner)
        acct = q("select account_code from dims.dim_account order by account_code limit 1")[0]["account_code"]
        mat = q("select material_code from dims.dim_material order by material_code limit 1")[0]["material_code"]
        r = c.post("/cell", data=json.dumps({"version": V, "layer": 2, "reason": "MARKET", "material": mat, "account": acct,
                                             "period": vp["actual"][0], "typed": "100", "current": "0"}), headers={"Content-Type": "application/json"})
        body = json.loads(r.data)
        assert not body["placed"] and "an actual period" in body["says"], body
        print(f"refused         the demand plan: {mat} at {acct} in {vp['actual'][0]}, by {planner}")
        session.become(FINANCE)

        # 5 · the calculation itself: nothing is written into an actual period, whoever asks and at whatever node
        with app.test_request_context():
            stamp, base = FL.base(V, M.FINANCE)
            g = base.copy()
            assert g.type(V, "ALL", cat, vp["actual"][0], "volume", 1e6, "T-1") == []
            assert not any(k[3] in vp["actual"] for k in g.cells), "the grid holds no cell in an actual period"
            # a figure typed on a total — all customers × a category — spreads over one plan period's cells only
            P = vp["plan"][0]
            written = g.type(V, "ALL", cat, P, "volume", 1e6, "T-2")
            assert written and {k[3] for k, _ in written} == {P}, {k[3] for k, _ in written}
            assert abs(sum(x for _, x in written) - 1e6) < 1e-3
        print(f"calculation     a figure on an actual period writes nothing; on a total in {P} it reaches {len(written)} cells, all in {P}")
    finally:
        session.become(FINANCE)
        with app.test_request_context():
            FL.discard(FINANCE, V)
            S.COPIES.drop(FINANCE, ("schedule", V))
        landing_now = set(M.ENTRIES.files()) | set(M.FINANCE.files()) | set(S.LANDING.files())
        assert landing_now == landing_before, sorted(landing_now - landing_before)
        for f in set(chassis.CONFIG.receipts.glob("*.json")) - receipts_before:
            f.unlink()
    print("nothing saved; the refusals' receipts removed")


if __name__ == "__main__":
    main()
