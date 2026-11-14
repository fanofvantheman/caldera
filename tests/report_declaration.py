"""A report as a saved question over the measure register — checked through the routes, against the warehouse.

    uv run python -m tests.report_declaration        # from build/, with the warehouse built; writes one report file, removed after

1. The pick page offers every model's measures — the demand plan, the plan valued, labour, the strategic plan with
   Finance's plan and the schedule — each with how it adds up and what it can be read by.
2. A report asks only for what the plan defines: a measure not in the register, rows a measure cannot be read by, a
   comparison without two versions, and a filter on a node that does not exist are refused, and nothing is saved.
3. Saved, it is one row in the landing and drawn at once: net sales by unit and year equals the plan valued summed in the
   warehouse; net per case at the total is net sales ÷ cases, never the sum of the rows' prices.
4. It reads as whoever opens it: labour by cost centre shows figures to a holder of the right to read individual pay, and
   the cells that pay by name reaches are withheld for a person without it — not left out of the total.
5. The seeded report draws; the latest view less the business plan is read only where both have the figure; a strategic
   measure says versions do not apply.
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
from face import reports as RP                        # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
FINANCE, PLANT = "finance.manager@caldera", "plant.manager@caldera"


def text(html: str) -> str:
    html = html[html.find("<h1>"):]
    html = re.sub(r"<style.*?</style>|<script.*?</script>", "", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def num(s: str) -> float:
    return float(s.replace(",", ""))


def main() -> None:
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    landing_before, receipts_before = set(RP.LANDING.files()), set(chassis.CONFIG.receipts.glob("*.json"))
    with app.test_request_context():
        V = M.reads.default_version()
    try:
        session.become(FINANCE)
        page = text(c.get("/reports").data.decode())
        for g in ("Demand plan", "The plan valued", "Labour", "Strategic plan", "Revenue", "Opex schedule"):
            assert g in page, g
        print("pick            every model's measures offered: the demand plan, the plan valued, labour, the strategic plan, Finance's plan, the schedule")

        def save(**f):
            c.post("/reports", data={"report_name": "test report", "columns_axis": "fiscal_year", "versions": [V], **f})
            return session.last
        assert not save(measure=["valued.nonsense"], rows="material:category")["placed"]
        assert not save(measure=["valued.net_sales", "labour.cost"], rows="material:category")["placed"]
        assert not save(measure=["valued.net_sales"], rows="material:category", compare="Y")["placed"]
        assert not save(measure=["valued.net_sales"], rows="material:category", filter_material="NO_SUCH_NODE")["placed"]
        assert set(RP.LANDING.files()) == landing_before
        print("refused         a measure the plan does not define, rows labour cannot be read by, a comparison of one version, a filter on no node")

        r = save(measure=["valued.net_sales", "valued.net_per_case"], rows="customer:planning_unit", report_name="test: net sales by unit")
        assert r["placed"], r
        new = sorted(set(RP.LANDING.files()) - landing_before)
        assert len(new) == 1
        rid = r["subject"] if "subject" in r else next(x for x in new[0].read_text().split(",") if x.startswith("RP-"))
        page = text(c.get(f"/reports/{rid}").data.decode())
        want = {str(x["fy"]): x for x in q("select fiscal_year::text fy, sum(net_sales) ns, sum(case when priced then cases else 0 end) cs from plan.demand_financialised where version_id = ? group by 1", V)}
        fys = sorted(want)
        block = page[page.find("Net sales · " + V):page.find("Net per case")]
        total = re.search(r"Total ((?:-?[\d,]+ ?)+)", block).group(1).split()
        for fy, t in zip(fys, total):
            assert abs(num(t) - want[fy]["ns"]) < 1, (fy, t, want[fy]["ns"])
        ppc = page[page.find("Net per case · " + V):]
        ptot = re.search(r"Total ((?:-?[\d,.]+ ?)+)", ppc).group(1).split()
        for fy, t in zip(fys, ptot):
            assert abs(num(t) - want[fy]["ns"] / want[fy]["cs"]) < 0.006, (fy, t)
        print(f"drawn           {rid} at once from the landing: net sales by year equals the plan valued in the warehouse; "
              f"net per case at the total is net sales ÷ cases ({ptot[0]} in FY{fys[0]})")

        r = save(measure=["labour.cost"], rows="cost_centre", report_name="test: labour by cost centre")
        rid2 = sorted(set(RP.LANDING.files()) - landing_before - set(new))
        assert r["placed"] and rid2
        rid2 = next(x for x in rid2[0].read_text().replace("\n", ",").split(",") if x.startswith("RP-"))
        mine = text(c.get(f"/reports/{rid2}").data.decode())
        session.become(PLANT)
        theirs = text(c.get(f"/reports/{rid2}").data.decode())
        assert "withheld" not in mine and "withheld" in theirs and "individual pay" in theirs
        assert re.search(r"Total withheld", theirs), theirs[-600:]
        print(f"reads as whoever opens it  labour by cost centre: figures for {FINANCE}; the cells pay by name reaches, and the totals they sit in, withheld for {PLANT}")

        session.become(FINANCE)
        seed = text(c.get("/reports/RP-00001").data.decode())
        diff = seed[seed.find(f"{V} less"):]
        assert "less" in diff and "plans from" in seed
        row = re.search(r"Total ((?:-?[\d,]+ ?)+)", diff).group(1).split()
        assert len(row) == 1, row                    # only the year both versions have
        c.post("/reports", data={"report_name": "test: strategic", "measure": ["strategic.net_sales"], "rows": "category", "columns_axis": "fiscal_year"})
        assert session.last["placed"]
        rid3 = sorted(set(RP.LANDING.files()) - landing_before)[-1].read_text()
        rid3 = next(x for x in rid3.replace("\n", ",").split(",") if x.startswith("RP-"))
        assert "versions do not apply" in text(c.get(f"/reports/{rid3}").data.decode())
        print("seeded          the latest view less the business plan read only on the year both have; a strategic measure says versions do not apply")
    finally:
        for f in set(RP.LANDING.files()) - landing_before:
            f.unlink()
        for f in set(chassis.CONFIG.receipts.glob("*.json")) - receipts_before:
            f.unlink()
    print("cleaned up: the test's reports and receipts removed (no run was needed)")


if __name__ == "__main__":
    main()
