"""The compare and review views of the opex schedule and Headcount (DEC-20261115-02 points 4–5) — through the routes.

    uv run python -m tests.review_views        # from build/, with the warehouse built; takes two scoped runs

1. The views are tabs of the object's entry, offered by the right that makes them relevant: Finance (who holds the
   review rights) sees Schedule, Review and Compare; the plant manager, who enters, sees the schedule alone.
2. Compare at a node: the cost centres beneath side by side, each with its state, each figure the sum of the schedule's
   cells for it; Headcount the same, with FTE.
3. Review at a cost centre: its state, its lines against last year, what was entered on it; accept and send back offered
   on a submitted one, nothing typed. Accepting from the review view is placed and returns to it.
4. Against the reference (DEC-20261115-07): on the latest view the reference and last year are two columns on compare
   and review; the reference's figures, period for period, are its own schedule's for the periods it covers; a period it
   does not cover is empty and left out of its total, which says how many periods it compares; Headcount's reference is
   the reference's own labour over the same periods; the business plan, which has no reference, shows last year only.
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

        # 4 · against the reference, beside last year
        R = q("select reference_version r from dims.ctl_version where version_id = ?", V)[0]["r"]
        assert R and R != V, R
        sched = lambda v, cc: {r["period"]: r["a"] for r in q("select period, sum(amount) a from plan.opex_schedule where version_id = ? and cost_centre_code = ? group by 1", v, cc)}
        mine, theirs = sched(V, "CC_E_BEANS"), sched(R, "CC_E_BEANS")
        covered = sorted(p for p in mine if p in theirs)
        assert covered and len(covered) < len(mine), (covered, sorted(mine))      # the plan runs past the reference's year
        html = c.get(f"/schedule/compare?version={V}&cc=OPS").data.decode()
        head = html.split("<thead>")[1].split("</thead>")[0]
        assert "Same periods last year" in head and f"{R}<span" in head and f"{len(covered)} of {len(mine)} periods" in head, head
        html = c.get(f"/schedule/review?version={V}&cc=CC_E_BEANS").data.decode()
        lines_head = html.split("<h2>Lines")[1].split("</thead>")[0]
        assert R in lines_head and "Last year" in lines_head
        by = html.split("<h2>By period")[1].split("</table>")[0]
        cells = {p: re.findall(r'<td class="n">([^<]*)', row) for p, row in re.findall(r"<tr><td>(\d{4}P\d\d)</td>(.*?)</tr>", by, re.S)}
        assert sorted(cells) == sorted(mine), sorted(cells)
        for p, (plan, ref, rdiff, prior, pdiff) in cells.items():
            assert abs(amount(plan) - mine[p]) <= 500, (p, plan, mine[p])
            if p in theirs:
                assert abs(amount(ref) - theirs[p]) <= 500, (p, ref, theirs[p])                 # the reference's own figure
            else:
                assert ref == "" and rdiff == "", (p, ref, rdiff)                              # not covered: empty, not filled
        total = re.search(r'<tr class="total"><td>\d+ periods</td><td class="n">[^<]*</td><td class="n">([^<]*) <span class="small muted">(\d+) of (\d+)</span></td><td class="n">([^<]*)</td>', by)
        ref_tot = sum(theirs[p] for p in covered)
        assert total and abs(amount(total.group(1)) - ref_tot) <= 0.005 * ref_tot, (total and total.group(1), ref_tot)
        assert (int(total.group(2)), int(total.group(3))) == (len(covered), len(mine))
        want_diff = sum(mine[p] for p in covered) - ref_tot                                    # the plan less the reference, same periods
        assert abs(amount(total.group(4)) - want_diff) <= 1_000, (total.group(4), want_diff)
        hc = c.get(f"/headcount/compare?version={V}&cc=OPS").data.decode()
        fy = int(q("select fiscal_year f from dims.ctl_version where version_id = ?", V)[0]["f"])
        lab = q("""select sum(r.wages + r.on_costs) a from plan.labour_line r where r.version_id = ? and r.cost_centre_code = 'CC_E_BEANS'
                   and r.period in (select distinct period from plan.labour_line where version_id = ? and fiscal_year = ?)""", R, V, fy)[0]["a"]
        row = re.search(r'cc=CC_E_BEANS[^"]*">Echuca beans and spaghetti</a>.*?</tr>', hc, re.S).group(0)
        nums = re.findall(r'<td class="n[^"]*">([^<]*)</td>', row)
        assert f"{R} wages and on-costs" in hc and abs(amount(nums[3]) - lab) <= 0.005 * lab, (nums, lab)
        bp = c.get(f"/schedule/review?version={R}&cc=CC_E_BEANS").data.decode()
        assert "Last year" in bp.split("<h2>Lines")[1].split("</thead>")[0] and "periods covered" not in bp and "8 of 12" not in bp
        bpc = c.get(f"/schedule/compare?version={R}&cc=OPS").data.decode().split("<thead>")[1].split("</thead>")[0]
        assert "Same periods last year" in bpc and "over the same periods" not in bpc, bpc
        assert f"{R} wages and on-costs" not in c.get(f"/headcount/compare?version={R}&cc=OPS").data.decode()
        print(f"reference       {V} against {R} and last year, two columns; the beans hall's {len(covered)} covered periods read {R}'s own schedule "
              f"({ref_tot:,.0f}), the other {len(mine) - len(covered)} empty and out of its total; Headcount against {R}'s labour ({lab:,.0f}); {R} itself last year only")

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
            log = M.run_waiting()
        assert "✗" not in log, log[-800:]
        print("cleaned up: the test's files and receipts removed, the workflow's part of the plan run again")


if __name__ == "__main__":
    main()
