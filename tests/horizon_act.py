"""Changing a version's horizon on the Versions page — an act with a receipt, checked through the routes.

    uv run python -m tests.horizon_act               # from build/, with the warehouse built; takes two runs from the version register down

Refused: by a person without the verb, without a reason, past what the models calculate, and for no change. Then the
holder shortens the latest view's horizon: the receipt counts Finance's saved figures that fall past it before anything
is placed; after the run every grid takes the shorter horizon (the version's plan periods, Finance's grid refusing a
period now past it), Finance's figures there read refused and stay on record, the horizon it was named with is kept,
and the act is on the change history. Everything it writes is removed and the run taken again, so the version is left
with the horizon it had.
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
from face import versions as VP                       # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
HOLDER, OTHER = "finance.manager@caldera", "gm@caldera"
LIVE = {"Content-Type": "application/json", "X-Live": "1"}


def main() -> None:
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    landing_before, receipts_before = set(VP.LANDING.files()), set(chassis.CONFIG.receipts.glob("*.json"))
    with app.test_request_context():
        V = M.reads.default_version()
        v = M.reads.version(V)
    n0, through0 = v["horizon_periods"], v["plan_through"]
    # short enough that some of Finance's saved figures fall past it — the receipt has to count them
    last_fig = q("select max(period) p from plan.finance_edit where version_id = ? and state = 'in_force'", V)[0]["p"]
    n1 = max(1, q("select count(*) n from dims.dim_period where period > ? and period < ?", v["from_period"], last_fig)[0]["n"])
    ran = False

    def act(n, reason="test: a shorter horizon", who=HOLDER):
        session.become(who)
        c.post("/versions/horizon", data={"version_id": V, "horizon_periods": str(n), "reason": reason})
        return session.last

    try:
        r = act(n1, who=OTHER)
        assert not r["placed"] and any("does not hold" in x["says"] and "version.name" not in x["says"] for x in r["checks"] if not x["ok"]), r
        assert not act(n1, reason="")["placed"]
        assert not act(60)["placed"] and any("the last period the models calculate" in x["says"] for x in session.last["checks"] if not x["ok"])
        assert not act(n0)["placed"] and any("already plans" in x["says"] for x in session.last["checks"] if not x["ok"])
        assert set(VP.LANDING.files()) == landing_before
        print(f"refused         by {OTHER}, without a reason, past the reach (60 periods), and for no change ({n0}); nothing placed")
        page = c.get("/versions").data.decode()
        assert "plan.version_horizon" not in page and 'action="/versions/horizon"' in page

        t = time.perf_counter()
        r = act(n1)
        assert r["placed"], r
        ran = True
        flag = next((x for x in r["checks"] if x.get("flag")), None)
        with app.test_request_context():
            v1 = M.reads.version(V); vp = M.reads.version_periods(V)
        assert v1["horizon_periods"] == n1 and v1["named_horizon_periods"] == n0 and len(vp["plan"]) == n1 and v1["plan_through"] < through0, v1
        past = q("select count(*) n from plan.finance_edit where version_id = ? and period > ? and state = 'refused: past the version''s horizon'", V, v1["plan_through"])[0]["n"]
        print(f"changed         {V}: {n0} → {n1} periods, to {v1['plan_through']} (named with {n0}), released in {time.perf_counter() - t:.0f} s; "
              f"the receipt said: {flag['says'] if flag else 'no saved figure moves'}; {past} of Finance's figures now read refused, on record")
        assert flag and past and f"{past} of Finance's saved figures" in flag["says"], (flag, past)
        last_p = vp["plan"][-1]
        gone = q("select min(period) p from dims.dim_period where period > ?", last_p)[0]["p"]
        r = c.post("/finance/cell", data=json.dumps({"page": {"version": V, "fy": v1["fiscal_year"], "customer": "ALL", "material": "ALL"},
                                                     "node": "ALL", "period": gone, "measure": "volume", "value": "1000"}), headers=LIVE)
        assert "not a plan period" in json.loads(r.data).get("fin-status", ""), r.data[:400]
        rec = q("select standing, what from plan.change_record where record = 'versions' and act = 'horizon' and version_id = ?", V)
        assert rec and rec[0]["standing"] == "stands" and f"{n1} periods" in rec[0]["what"], rec
        page = c.get("/versions").data.decode()
        assert f"named with {n0}" in page
        print(f"every grid      {V} plans {len(vp['plan'])} periods; Finance's grid refuses {gone}; the act is on the change history")
    finally:
        session.become(HOLDER)
        for f in set(VP.LANDING.files()) - landing_before:
            f.unlink()
        for f in set(chassis.CONFIG.receipts.glob("*.json")) - receipts_before:
            f.unlink()
        if ran:
            with app.test_request_context():
                log = M.Runner(VP.HORIZON_RUN).run()
            assert "✗" not in log, log[-800:]
            with app.test_request_context():
                assert M.reads.version(V)["horizon_periods"] == n0
        print(f"cleaned up: the act and receipts removed, the run taken again — {V} plans {n0} periods")


if __name__ == "__main__":
    main()
