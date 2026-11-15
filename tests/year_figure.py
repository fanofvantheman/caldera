"""A figure typed in the year column of Finance's grid — checked through the routes, against the warehouse.

    uv run python -m tests.year_figure                 # from build/, with the warehouse built; writes nothing

The year column is the year as the grid reads it, actual and plan together. A volume typed there: the year reads it, the
actual periods do not move, the periods past the year end do not move, and the year's forecast periods take the difference
by the demand plan's shape — the same weights a period figure spreads by. A price typed there: the year's price is what
was typed and every forecast period's price moves by one factor. One step, the mark on the year cell, which takes it out
whole; a period it reached says it came from the year. A volume below what the actual periods hold is refused. On a plain
post (no page script) a year left as it was moves nothing, so a period typed in the same post stands. A save would write
the period figures it made. Nothing is saved: the working copy is discarded at the end and no file reaches the landing.
"""
from __future__ import annotations

import datetime as dt
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

from face import SHELL, roles, session                # noqa: E402
from face import __main__ as M                        # noqa: E402
from face import finance_live as FL                   # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
FINANCE = "finance.manager@caldera"
LIVE = {"Content-Type": "application/json", "X-Live": "1"}


def main() -> None:
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    landing_before, receipts_before = set(M.FINANCE.files()), set(chassis.CONFIG.receipts.glob("*.json"))
    with app.test_request_context():
        V = M.reads.default_version()
        fy = int(M.reads.version(V)["fiscal_year"])
        vp = M.reads.version_periods(V)
    in_fy = [p for p in vp["periods"] if p["fiscal_year"] == fy]
    fore = [p["period"] for p in in_fy if not p["actual"]]
    past = [p["period"] for p in vp["periods"] if p["fiscal_year"] != fy and not p["actual"]]
    acts = [p["period"] for p in in_fy if p["actual"]]
    assert fore and acts, "a year with actual periods and forecast periods"
    page = {"version": V, "fy": fy, "customer": "ALL", "material": "ALL"}
    q_page = "&".join(f"{k}={v}" for k, v in page.items())

    def post(node, measure, value, period="FY"):
        r = c.post("/finance/cell", data=json.dumps({"page": page, "node": node, "period": period, "measure": measure, "value": str(value)}), headers=LIVE)
        assert r.status_code == 200, r.status_code
        return r.get_json()

    def copy():
        with app.test_request_context():
            return FL.working_copy(FINANCE, V, M.FINANCE)

    def grid():
        wc = copy()
        with app.test_request_context():
            return wc.grid if wc else FL.base(V, M.FINANCE)[1]

    def at(node, period, measure="volume", g=None):
        return FL.node_value(g or grid(), V, "ALL", node, period, measure)

    def actual_cells(node):
        g = grid()
        A, Ms = g.accounts_under["ALL"], g.materials_under.get(node, set())
        with app.test_request_context():
            return [{"source": "actual", "cases": r["cases"], "net_sales": r["net_sales"], "price": None} for r in M.reads.finance_actuals(vp["actual"])
                    if r["account_code"] in A and r["material_code"] in Ms and r["period"] in acts]

    def year(node, measure="volume"):
        g = grid()
        cells = [g.cells[k] for p in fore for k in g.scope(V, "ALL", node, p)]
        return FL.aggregate(cells + actual_cells(node), measure, g.rules)

    try:
        session.become(FINANCE)
        c.post("/finance/discard", data=page)
        with app.test_request_context():
            base = FL.base(V, M.FINANCE)[1]
            cat = max((n for n in M.reads.material_tree_under("ALL") if (FL.node_value(base, V, "ALL", n, fore[0], "volume") or 0) > 0),
                      key=lambda n: FL.node_value(base, V, "ALL", n, fore[0], "volume"))
        html = c.get(f"/revenue?{q_page}&material={cat}").data.decode()
        assert f'name="v|{cat}|FY"' in html, "the year cell takes a figure"
        page["material"] = cat; q_page = "&".join(f"{k}={v}" for k, v in page.items())

        # 1 · a volume for the year: the forecast periods take the difference by the demand plan's shape
        y0, a0 = year(cat), FL.aggregate(actual_cells(cat), "volume", base.rules) or 0
        before = {p: at(cat, p, g=base) for p in fore + past}
        w = {p: sum(max((base.cells[k]["source_cases"] if base.cells[k]["source"] == "fed" else base.cells[k]["cases"]) or 0, 0)
                    for k in base.scope(V, "ALL", cat, p)) for p in fore}
        target = round(y0 * 1.06)
        got = post(cat, "volume", target)
        assert f"fin-r-{cat}" in got and "fin-tiles" in got, sorted(got)
        assert abs(year(cat) - target) < 1e-4, (year(cat), target)
        assert abs((FL.aggregate(actual_cells(cat), "volume", base.rules) or 0) - a0) < 1e-9, "the actual periods do not move"
        for p in past:
            assert abs((at(cat, p) or 0) - (before[p] or 0)) < 1e-9, f"{p} is past the year end and does not move"
        W = sum(w.values())
        for p in fore:
            assert abs(at(cat, p) - (target - a0) * w[p] / W) < 1e-4, p
        steps = copy().history.done
        assert len(steps) == 1 and len(steps[0]) == len(fore) and all(t.year == fy for t in steps[0]), "one step, a figure per forecast period"
        print(f"year volume    {cat} FY{fy}: {y0:,.0f} → {target:,}; actual {a0:,.0f} unchanged; {len(fore)} forecast periods by the demand plan's shape; {len(past)} past the year end untouched")

        # 2 · the page: the mark on the year cell; a period it reached says where it came from
        html = c.get(f"/revenue?{q_page}").data.decode()
        first = steps[0][0].edit_id
        assert f'name="figure" value="{first}"' in html and html.count('form="fin-one" formaction="/finance/undo') >= 1
        assert f"typed for FY{fy} at this node" in html and "the mark on the year takes it out" in html
        assert f"for FY{fy}" in html[html.index('id="fin-steps"'):][:600], "Undo names the year figure once"
        print("year mark      ↶ on the year cell; each forecast period says it came from the year figure")

        # 3 · a save would write the period figures it made, under one reason
        rows = FL.rows_for_save(copy(), "FS-TEST", dt.datetime.now(), FINANCE, "MARKET", "")
        assert sum(1 for r in rows if r["action"] == "enter") == len(fore) and {r["period"] for r in rows if r["action"] == "enter"} == set(fore)
        print(f"year on record {len(fore)} period figures under the save's one reason")

        # 4 · the mark takes it out whole
        r = c.post("/finance/undo", data={**page, "figure": first}, headers={"X-Live": "1"})
        assert r.status_code == 200 and f"FY{fy}" in r.get_json().get("fin-toast", "")
        assert all(abs((at(cat, p) or 0) - (before[p] or 0)) < 1e-9 for p in fore) and not copy().typed
        print("year undone    the whole year figure out at once; the toast names it for the year")

        # 5 · a price for the year: the year reads it; every forecast period's price by one factor
        p0 = year(cat, "price")
        pb = {p: at(cat, p, "price", g=base) for p in fore}
        pt = round(p0 + 0.50, 2)
        post(cat, "price", pt)
        assert abs(year(cat, "price") - pt) < 1e-6, (year(cat, "price"), pt)
        k = {p: at(cat, p, "price") / pb[p] for p in fore}
        assert max(k.values()) - min(k.values()) < 1e-9, k
        assert abs(year(cat) - y0) < 1e-6, "a price moves no volume"
        print(f"year price     {cat} FY{fy}: {p0:.4f} → {pt}; every forecast period × {next(iter(k.values())):.6f}")
        c.post("/finance/discard", data=page)

        # 6 · refused: a volume below what the actual periods already hold
        got = post(cat, "volume", round(a0 * 0.5))
        assert "actual periods already hold" in got.get("fin-status", ""), got.get("fin-status")
        assert copy() is None or not copy().typed
        print(f"refused        {round(a0 * 0.5):,} for the year, below the actual {a0:,.0f}")

        # 7 · a plain post (no page script): every input comes back; the year as it was moves nothing, the period typed stands
        p1 = fore[0]
        new_p1 = round(at(cat, p1) + 900)
        form = {**page, f"v|{cat}|FY": f"{year(cat):.0f}", f"v|{cat}|{p1}": str(new_p1)}
        r = c.post("/finance/cell", data=form)
        assert r.status_code == 302
        assert abs(at(cat, p1) - new_p1) < 1e-6 and len(copy().history.done) == 1 and not copy().typed[0].year
        print(f"plain post     the year as drawn moves nothing; {p1} typed at {new_p1:,} stands")
        c.post("/finance/discard", data=page)
        assert set(M.FINANCE.files()) == landing_before, "nothing reaches the landing"
    finally:
        FL.discard(FINANCE, V)
        for f in set(chassis.CONFIG.receipts.glob("*.json")) - receipts_before:
            f.unlink()
    print("nothing saved; the working copy discarded")


if __name__ == "__main__":
    main()
