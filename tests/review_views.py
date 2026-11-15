"""The compare and review views of the opex schedule and Headcount (DEC-20261115-02 points 4–5) — through the routes.

    uv run python -m tests.review_views        # from build/, with the warehouse built; takes two scoped runs

1. The views are tabs of the object's entry, offered by the right that makes them relevant: Finance (who holds the
   review rights) sees Schedule, Review and Compare; the plant manager, who enters, sees the schedule alone.
2. Compare at a node: the cost centres beneath side by side, each with its state, each figure the sum of the schedule's
   cells for it; Headcount the same, with FTE.
3. Review at a cost centre: its state, its lines against last year, what was entered on it; accept and send back offered
   on a submitted one, nothing typed. Accepting from the review view is placed and returns to it.
Everything it writes is removed afterwards and the workflow's part of the plan is run again.
"""
from __future__ import annotations

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

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
FINANCE, PLANT = "finance.manager@caldera", "plant.manager@caldera"


def amount(s: str) -> float:
    """A figure as the page writes it ($6.06M, $412k, $950)."""
    s = s.replace("$", "").replace(",", "").strip()
    mult = {"M": 1e6, "k": 1e3, "K": 1e3}.get(s[-1:], 1)
    return float(s[:-1] if mult != 1 else s or 0) * mult


def tabs(html: str) -> list[str]:
    t = re.search(r'<nav class="tabs">(.*?)</nav>', html, re.S)
    return re.findall(r">([^<]+)</a>", t.group(1)) if t else []


def main() -> None:
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    landing_before, receipts_before = set(M.SUBMISSIONS.files()), set(chassis.CONFIG.receipts.glob("*.json"))
    with app.test_request_context():
        V = M.reads.default_version()
    try:
        # 1 · the views as tabs, by the right
        session.become(FINANCE)
        assert tabs(c.get("/schedule?cc=OPS").data.decode()) == ["Schedule", "Review", "Compare"]
        assert {"Review", "Compare"} <= set(tabs(c.get("/headcount/role?cc=OPS").data.decode()))
        session.become(PLANT)
        assert tabs(c.get("/schedule?cc=OPS").data.decode()) == [] and c.get("/schedule/review?cc=CC_E_BEANS").status_code == 200
        assert "accept" not in c.get("/schedule/review?cc=CC_E_BEANS").data.decode().split("<h2>Lines")[0].lower().split("</h1>")[1]
        print(f"tabs            {FINANCE}: Schedule · Review · Compare; {PLANT}: the schedule alone, and no accept if they open a review")

        # 2 · compare
        session.become(FINANCE)
        html = c.get(f"/schedule/compare?version={V}&cc=OPS").data.decode()
        rows = re.findall(r'<a href="/schedule\?[^"]*cc=(CC_\w+)[^"]*">[^<]*</a> <span class="small muted">\w+</span></td><td class="small">[^<]*</td><td class="n">([^<]*)</td>.*?<span class="state (\w+)">', html, re.S)
        got = {cc: (amount(p), st) for cc, p, st in rows}
        assert got.get("CC_E_BEANS", (0, ""))[1] == "submitted" and got["CC_E_FRUIT"][1] == "accepted" and got["CC_L_PROD"][1] == "sent_back", got
        want = q("select sum(amount) a from plan.opex_schedule where version_id = ? and cost_centre_code = 'CC_E_BEANS'", V)[0]["a"]
        assert abs(got["CC_E_BEANS"][0] - want) <= 0.001 * want + 5_000, (got["CC_E_BEANS"], want)      # as written, to the page's rounding
        hc = c.get(f"/headcount/compare?version={V}&cc=OPS").data.decode()
        assert "Echuca beans and spaghetti" in hc and "FTE" in hc
        print(f"compare         {len(got)} cost centres beneath OPS side by side, the beans hall's {want:,.0f} as the page writes it; states as handed over; Headcount with FTE")

        # 3 · review, and an accept taken from it
        html = c.get(f"/schedule/review?version={V}&cc=CC_E_BEANS").data.decode()
        assert "submitted" in html and ">accept</button>" in html and ">send back</button>" in html and 'name="m|' not in html
        r = c.post("/workflow/act?via=finplan", data={"step": "opex", "node": "CC_E_BEANS", "act": "accept", "next": f"/schedule/review?version={V}&cc=CC_E_BEANS"})
        assert session.last["placed"] and "/schedule/review" in r.headers["Location"], (session.last["checks"], r.headers.get("Location"))
        assert q("select state from plan.step_state where version_id = ? and step = 'opex' and node = 'CC_E_BEANS'", V)[0]["state"] == "accepted"
        print("review          the beans hall: its lines against last year, accept and send back offered, nothing to type; accepted from here, and back here")
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
