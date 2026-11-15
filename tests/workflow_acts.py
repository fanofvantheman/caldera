"""Plan administration and workflow per process (DEC-20261115-03) — through the routes, against the warehouse.

    uv run python -m tests.workflow_acts        # from build/, with the warehouse built; takes a few scoped runs

1. Each process administers the plans of its own kind: Financial planning's administration page offers the acts on the
   business plan and lists the latest view read only; Integrated business planning's the reverse.
2. The workflow page of Financial planning shows every step at every cost centre as the seeded acts left it — submitted,
   accepted, sent back — with each step's due date, and the revenue step late.
3. A submitted or accepted cost centre takes no entry on the opex schedule; one sent back does.
4. Acts through the page, each checked: the plant manager submits a cost centre's opex, and it is locked; a send back with
   no reason is refused; Finance sends it back with one, and it takes entry again; someone without the right is refused.
5. Nothing the plan calculates waits on the state: the schedule's cells are the same before and after.
6. A due date set on the administration page is what the workflow page reads.
Everything it writes is removed afterwards and the workflow's part of the plan is run again.
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
from face import schedule as S                        # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
FINANCE, PLANT, PLANNER = "finance.manager@caldera", "plant.manager@caldera", "planner.westbrook@caldera"
LIVE = {"Content-Type": "application/json", "X-Live": "1"}


def state(V: str, step: str, node: str) -> str:
    return q("select state from plan.step_state where version_id = ? and step = ? and node = ?", V, step, node)[0]["state"]


def main() -> None:
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    landing_before, receipts_before = set(M.SUBMISSIONS.files()), set(chassis.CONFIG.receipts.glob("*.json"))
    with app.test_request_context():
        V = M.reads.default_version()
        P = S.base(V)["inp"].periods
    BP = q("select version_id from dims.ctl_version where version_kind = 'business_plan'")[0]["version_id"]

    def type_month(cc_line: tuple) -> dict:
        page = {"version": V, "fy": 0, "cc": cc_line[1], "entity": ""}
        r = c.post("/schedule/cell", data=json.dumps({"page": page, "cell": f"m|{S.line_id(cc_line)}|{P[2]}", "value": "12345"}), headers=LIVE)
        c.post("/schedule/discard", data=page)
        return json.loads(r.data)

    try:
        session.become(FINANCE)
        # 1 · administration per process
        fin = c.get("/versions?via=finplan").data.decode()
        ibp = c.get("/versions").data.decode()
        assert "Financial planning" in fin and "not reopened — LV-" in fin and "not reopened — LV-" not in ibp      # the business plan's own act, offered only where it is administered
        assert "Integrated business planning's — read only here" in fin
        assert "Financial planning's — read only here" in ibp
        print(f"administration  Financial planning acts on {BP} and reads {V}; Integrated business planning the reverse")

        # 2 · the workflow page as seeded
        wf = c.get(f"/workflow?via=finplan&version={V}").data.decode()
        assert all(s in wf for s in ("Revenue", "Labour", "Opex", "Capital")) and "late" in wf, "steps or lateness missing"
        seeded = {n: state(V, "opex", n) for n in ("CC_E_BEANS", "CC_E_FRUIT", "CC_L_PROD", "CC_E_MAINT")}
        assert seeded == {"CC_E_BEANS": "submitted", "CC_E_FRUIT": "accepted", "CC_L_PROD": "sent_back", "CC_E_MAINT": "open"}, seeded
        print(f"workflow        opex as seeded {seeded}; revenue late against its due date")

        # 3 · the lock on entry
        assert "takes no entry" in type_month(("CF", "CC_E_BEANS", "6200")).get("sch-status", "")
        assert "takes no entry" in type_month(("CF", "CC_E_FRUIT", "6200")).get("sch-status", "")
        assert "takes no entry" not in type_month(("RBF", "CC_L_PROD", "6200")).get("sch-status", "")
        print("locked          the submitted and the accepted cost centres refuse a month; the one sent back takes it")

        # 4 · acts through the page; 5 · the schedule's figures do not move
        before = {(x["entity_code"], x["account_code"], x["period"]): x["amount"] for x in q("select * from plan.opex_schedule where version_id = ? and cost_centre_code = 'CC_E_MAINT'", V)}
        session.become(PLANNER)
        c.post("/workflow/act?via=finplan", data={"step": "opex", "node": "CC_E_MAINT", "act": "submit"})
        assert not session.last["placed"], "a demand planner submitted a cost centre's opex"
        session.become(PLANT)
        c.post("/workflow/act?via=finplan", data={"step": "opex", "node": "CC_E_MAINT", "act": "submit"})
        assert session.last["placed"] and state(V, "opex", "CC_E_MAINT") == "submitted", session.last["checks"]
        session.become(FINANCE)
        assert "takes no entry" in type_month(("CF", "CC_E_MAINT", "6300")).get("sch-status", "")
        c.post("/workflow/act?via=finplan", data={"step": "opex", "node": "CC_E_MAINT", "act": "send_back"})
        assert not session.last["placed"] and any(x["check"] == "a reason to send it back" and not x["ok"] for x in session.last["checks"])
        c.post("/workflow/act?via=finplan", data={"step": "opex", "node": "CC_E_MAINT", "act": "send_back", "note": "test: the overhaul is in P09 now"})
        assert session.last["placed"] and state(V, "opex", "CC_E_MAINT") == "sent_back"
        assert "takes no entry" not in type_month(("CF", "CC_E_MAINT", "6300")).get("sch-status", "")
        after = {(x["entity_code"], x["account_code"], x["period"]): x["amount"] for x in q("select * from plan.opex_schedule where version_id = ? and cost_centre_code = 'CC_E_MAINT'", V)}
        assert after == before, "a state moved a figure"
        print(f"acts            {PLANNER} refused; {PLANT} submits CC_E_MAINT and it locks; a send back without a reason refused, with one placed and "
              f"the cost centre takes entry again; its {len(before)} cells unchanged throughout")

        # 6 · a due date set on the administration page
        c.post("/workflow/due?via=finplan", data={"step": "capital", "version": V, "due_on": "2026-12-04"})
        assert session.last["placed"], session.last["checks"]
        assert str(q("select max(due_on) d from plan.step_state where version_id = ? and step = 'capital'", V)[0]["d"]) == "2026-12-04"
        assert "due 2026-12-04" in c.get(f"/workflow?via=finplan&version={V}").data.decode()
        print("due date        capital due 2026-12-04, set on the administration page, read by the workflow page")
    finally:
        for f in set(M.SUBMISSIONS.files()) - landing_before:
            f.unlink()
        for f in set(chassis.CONFIG.receipts.glob("*.json")) - receipts_before:
            if "workflow" in f.name or "run_" in f.name:
                f.unlink()
        with app.test_request_context():
            log = M.Runner(M.SCOPED["workflow"]["commands"]).run()
        assert "✗" not in log, log[-800:]
        print("cleaned up: the test's files and receipts removed, the workflow's part of the plan run again")


if __name__ == "__main__":
    main()
