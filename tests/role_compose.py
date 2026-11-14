"""Rights, roles of the client's own, and the kind of plan on an assignment — checked through the routes.

    uv run python -m tests.role_compose             # from build/, with the warehouse built; takes one run from the role register down

1. The rights register covers every right any role grants, each with a group and a class; the page reads it by either.
2. The client's own role (the sales budget holder) is listed as its own beside the shipped set, held at the Sales cost
   centre for the business plan only.
3. The kind of plan on the assignment: the sales director holds the schedule's months at Sales for the business plan, not
   the latest view — asked with no kind, held; on the latest view's schedule, a month is refused and says why.
4. Composing: refused for a person without the right, for a shipped role's name, for a right the plan does not have and
   for no right; a role that would enter demand and the supply constraint is told so, not refused; composed, it is in the
   register as the client's own after the run, with its rights, and grants nothing until assigned.
Everything it writes is removed afterwards and the run taken again.
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
from face import rights as R                          # noqa: E402
from face import schedule as S                        # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
HOLDER, OTHER, SALES = "finance.manager@caldera", "gm@caldera", "sales.director@caldera"
LIVE = {"Content-Type": "application/json", "X-Live": "1"}


def main() -> None:
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    landing_before, receipts_before = set(R.LANDING.files()), set(chassis.CONFIG.receipts.glob("*.json"))
    ran = False
    try:
        # 1 · the rights register
        granted = {r["action"] for r in q("select distinct action from dims.ctl_role_action")}
        reg = {r["verb"]: r for r in q("select * from dims.ref_verb")}
        assert granted <= set(reg), granted - set(reg)
        assert {r["right_class"] for r in reg.values()} == {"enter", "maintain", "decide", "read", "run"}
        session.become(HOLDER)
        by_group = c.get("/roles?by=group").data.decode(); by_class = c.get("/roles?by=class").data.decode()
        assert "Layers" in by_group and "Budget" in by_group and "Decides — decide" in by_class and "the right to type Finance" in by_group
        print(f"rights          {len(reg)} in the register, every right a role grants among them; the page reads them by group and by class of right")

        # 2 · the client's own role beside the shipped set
        page = c.get("/roles/list").data.decode()
        assert "Sales budget holder" in page and "your own" in page and "business plan only" in page, page[-2000:]
        print("roles           the sales budget holder listed as your own, held by the sales director at Sales for the business plan only")

        # 3 · the kind of plan on the assignment
        with app.test_request_context():
            V = M.reads.default_version()
            assert roles.may(SALES, "schedule.line.enter", "CC_SALES", dimension="organisation", kind="business_plan")
            assert not roles.may(SALES, "schedule.line.enter", "CC_SALES", dimension="organisation", kind="latest_view")
            assert roles.may(SALES, "schedule.line.enter", "CC_SALES", dimension="organisation")
            assert roles.may("plant.manager@caldera", "schedule.line.enter", "CC_E_TOM", dimension="organisation", kind="latest_view")
            P = S.base(V)["inp"].periods
        session.become(SALES)
        travel = ("CF", "CC_SALES", "6950")
        r = c.post("/schedule/cell", data=json.dumps({"page": {"version": V, "fy": int(P[0][:4]), "cc": "CC_SALES", "entity": ""},
                                                      "cell": f"m|{S.line_id(travel)}|{P[1]}", "value": "1000"}), headers=LIVE)
        said_ = json.loads(r.data).get("sch-status", "")
        assert "for latest view — held for business plan only" in said_, said_
        print(f"kind of plan    {SALES}: the Sales months held for the business plan, refused on {V}: “{said_.split('·')[0].strip()[:150]}”")

        # 4 · composing
        def compose(**f):
            c.post("/roles/compose", data=f)
            return session.last
        session.become(OTHER)
        assert not compose(role_name="Test role", verb=["read.plan"])["placed"]
        session.become(HOLDER)
        assert not compose(role_name="Demand planner", verb=["read.plan"])["placed"]
        assert not compose(role_name="Test role", verb=["read.plan", "layer.0.enter"])["placed"]
        assert not compose(role_name="Test role")["placed"]
        assert set(R.LANDING.files()) == landing_before
        print("refused         without the right, under a shipped role's name, with a right the plan does not have, and with no right")
        r = compose(role_name="Test role mixed", description="test", verb=["layer.2.enter", "delta.supply.enter", "read.plan"])
        assert r["placed"] and any(x.get("flag") and "back door" in x["says"] for x in r["checks"]), r
        ran = True
        own = q("select * from dims.ctl_role_definition where role_code = 'TEST_ROLE_MIXED'")
        acts = {x["action"] for x in q("select action from dims.ctl_role_action where role_code = 'TEST_ROLE_MIXED'")}
        assert own and own[0]["own"] and not own[0]["built_in"] and acts == {"layer.2.enter", "delta.supply.enter", "read.plan"}, (own, acts)
        assert not q("select 1 from dims.effective_entitlements where role_code = 'TEST_ROLE_MIXED'")
        assert "Test role mixed" in c.get("/roles/list").data.decode()
        print("composed        a role that enters demand and the supply constraint: told on the receipt, placed; after the run it is your own, three rights, held by nobody")
    finally:
        for f in set(R.LANDING.files()) - landing_before:
            f.unlink()
        for f in set(chassis.CONFIG.receipts.glob("*.json")) - receipts_before:
            f.unlink()
        if ran:
            with app.test_request_context():
                log = M.Runner(R.RUN).run()
            assert "✗" not in log, log[-800:]
        print("cleaned up: the test's file and receipts removed, the role register run again")


if __name__ == "__main__":
    main()
