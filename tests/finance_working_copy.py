"""Finance's grid recalculating as Finance types — checked through the routes, end to end, against the warehouse.

    uv run python -m tests.finance_working_copy          # from build/, with the warehouse built; takes one scoped run (~10 s)

Types at a leaf and at a parent, volume and price, through the endpoint the page's script posts to; checks what comes
back and what the working copy holds; checks a second person sees none of it; navigates and comes back; discards; then
saves, lets the save's run carry it into plan.finance_plan, and asserts that every cell of the version — not only the
ones typed — is what the grid showed before saving, to the cent and the case. Everything it writes (the save's file,
its receipts) is removed afterwards and Finance's part of the plan is run again, so the plan is left as it was found.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

BUILD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BUILD))
if os.environ.get("FACE_ROOT"):                       # a copy of face/ under test, elsewhere
    sys.path.insert(0, os.environ["FACE_ROOT"])

import chassis                                        # noqa: E402
from chassis import app as chassis_app                # noqa: E402
from chassis.warehouse import q                       # noqa: E402

from face import SHELL, roles, session                # noqa: E402
from face import __main__ as M                        # noqa: E402
from face import finance_live as FL                   # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
FINANCE_USER, OTHER = "finance.manager@caldera", "gm@caldera"
UNSAVED_CELL = re.compile(r'<td class="n[^"]*\bunsaved\b')
LIVE = {"Content-Type": "application/json", "X-Live": "1"}


def main() -> None:
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    landing_before, receipts_before = set(M.FINANCE.files()), set(chassis.CONFIG.receipts.glob("*.json"))
    with app.test_request_context():
        V = M.reads.default_version()
        fy = int(M.reads.version(V)["fiscal_year"])
        P = M.reads.open_periods(V)[0] if int(M.reads.open_periods(V)[0][:4]) == fy else None
    assert P, "an open period in the version's own year"
    page = {"version": V, "fy": fy, "dim": "customer", "node": "ALL", "grain": "period", "fc": "ALL", "fm": "ALL"}
    timings: list[float] = []

    def post(node: str, measure: str, value: float, fc: str = "ALL", fm: str = "ALL", period: str = P):
        t = time.perf_counter()
        r = c.post("/finance/cell", data=json.dumps({"page": {**page, "fc": fc, "fm": fm}, "node": node, "period": period, "measure": measure, "value": str(value)}), headers=LIVE)
        timings.append(time.perf_counter() - t)
        assert r.status_code == 200, r.status_code
        return r

    def at(fc: str, node: str, measure: str, period: str = P, who: str = FINANCE_USER, source: bool = False):
        with app.test_request_context():
            wc = FL.working_copy(who, V, M.FINANCE)
            g = wc.grid if wc else FL.base(V, M.FINANCE)[1]
            return FL.node_value(g, V, fc, node, period, measure, source)

    def children(node: str) -> list[str]:
        with app.test_request_context():
            return list(M.reads.material_tree_under(node))

    try:
        session.become(FINANCE_USER)
        c.post("/finance/discard", data=page)
        assert c.get("/revenue?" + "&".join(f"{k}={v}" for k, v in page.items())).status_code == 200
        # a fed category with at least two children carrying volume, and a fed account × material leaf beneath it
        cat = max((n for n in children("ALL") if (at("ALL", n, "volume") or 0) > 0 and len([k for k in children(n) if (at("ALL", k, "volume") or 0) > 0]) >= 2),
                  key=lambda n: at("ALL", n, "volume"))
        kids = [k for k in children(cat) if (at("ALL", k, "volume") or 0) > 0]
        fy_before = sum(at("ALL", "ALL", "volume", p) or 0 for p in M.reads.open_periods(V) if p.startswith(str(fy)))
        var_before = (at("ALL", "ALL", "revenue") or 0) - (at("ALL", "ALL", "revenue", source=True) or 0)

        # 1 · a parent volume: written down to the children by the demand plan's shape (Finance's own where built); they sum to it
        def shape(node: str) -> float:
            with app.test_request_context():
                g = FL.base(V, M.FINANCE)[1]
                return sum(max((g.cells[k]["source_cases"] if g.cells[k]["source"] == "fed" else g.cells[k]["cases"]) or 0, 0) for k in g.scope(V, "ALL", node, P))
        src = {k: shape(k) for k in children(cat)}
        S = sum(src.values())
        target = round(at("ALL", cat, "volume") * 1.10)
        r = post(cat, "volume", target)
        parts = r.headers["X-Live-Parts"].split(",")
        assert f"fin-r-{cat}" in parts and "fin-r-ALL" in parts and "fin-tiles" in parts, parts
        assert abs(at("ALL", cat, "volume") - target) < 1e-6
        assert abs(sum(at("ALL", k, "volume") or 0 for k in children(cat)) - target) < 1e-6
        for k in children(cat):                        # by the source's shape
            assert abs((at("ALL", k, "volume") or 0) - target * src[k] / S) < 1e-6, k
        fy_after = sum(at("ALL", "ALL", "volume", p) or 0 for p in M.reads.open_periods(V) if p.startswith(str(fy)))
        print(f"parent volume  {cat} × {P}: typed {target:,} → children sum {sum(at('ALL', k, 'volume') or 0 for k in children(cat)):,.2f}; "
              f"FY volume {fy_before:,.0f} → {fy_after:,.0f}")
        assert abs(fy_after - fy_before - (target - target / 1.10)) < 2

        # 2 · a parent price: every price beneath moves by one factor; the node reads revenue ÷ volume = what was typed
        p_cat = round(at("ALL", cat, "price") * 1.05, 2)
        post(cat, "price", p_cat)
        rev, vol = at("ALL", cat, "revenue"), at("ALL", cat, "volume")
        assert abs(rev / vol - p_cat) < 1e-9 and abs(at("ALL", cat, "price") - p_cat) < 1e-9
        print(f"parent price   {cat} × {P}: typed {p_cat} → revenue ÷ volume {rev:,.2f} ÷ {vol:,.2f} = {rev / vol:.6f}")

        # 3 · a leaf volume and a leaf price at account × material: last input wins — the typed parent moves with it
        with app.test_request_context():
            g = FL.working_copy(FINANCE_USER, V, M.FINANCE).grid
            leaf = max((k for k in g.scope(V, "ALL", kids[0], P) if g.cells[k]["source"] == "fed"), key=lambda k: g.cells[k]["cases"])
        acct, mat = leaf[1], leaf[2]
        cat_before, leaf_before = at("ALL", cat, "volume"), at(acct, mat, "volume")
        post(mat, "volume", round(leaf_before + 500), fc=acct, fm=kids[0])
        assert abs(at(acct, mat, "volume") - round(leaf_before + 500)) < 1e-6
        assert abs(at("ALL", cat, "volume") - (cat_before - leaf_before + round(leaf_before + 500))) < 1e-6
        print(f"leaf volume    {acct} × {mat}: {leaf_before:,.2f} → {round(leaf_before + 500):,}; the typed parent {cat} {cat_before:,.2f} → {at('ALL', cat, 'volume'):,.2f} (last input wins)")
        lp = round(at(acct, mat, "price") + 0.40, 2)
        cat_price_before = at("ALL", cat, "price")
        post(mat, "price", lp, fc=acct, fm=kids[0])
        assert abs(at(acct, mat, "price") - lp) < 1e-9 and abs(at(acct, mat, "revenue") - lp * at(acct, mat, "volume")) < 1e-6
        print(f"leaf price     {acct} × {mat}: → {lp}; revenue = volume × price = {at(acct, mat, 'revenue'):,.2f}; parent price {cat_price_before:.4f} → {at('ALL', cat, 'price'):.4f}")
        var_after = (at("ALL", "ALL", "revenue") or 0) - (at("ALL", "ALL", "revenue", source=True) or 0)
        print(f"variance       All × All × {P}: {var_before:,.2f} → {var_after:,.2f}")
        assert abs(var_after - var_before) > 1

        # 4 · navigating away and back: still marked unsaved
        r = c.get(f"/revenue?version={V}&fy={fy}&fc={acct}&fm={kids[0]}")
        assert b"not saved" in r.data and UNSAVED_CELL.search(r.data.decode())
        r = c.get(f"/revenue?version={V}&fy={fy}&fc=ALL&fm=ALL")
        assert b"4 figures typed and not saved" in r.data, "the working copy survives navigation"

        # 5 · a second person sees none of it
        session.become(OTHER)
        r = c.get(f"/revenue?version={V}&fy={fy}&fc=ALL&fm=ALL")
        assert r.status_code == 200 and b"not saved" not in r.data and not UNSAVED_CELL.search(r.data.decode())
        assert at("ALL", cat, "volume", who=OTHER) != at("ALL", cat, "volume")
        session.become(FINANCE_USER)

        # 6 · discard drops it; type again, then save
        c.post("/finance/discard", data=page)
        assert FL.working_copy(FINANCE_USER, V, M.FINANCE) is None
        post(cat, "volume", target)
        post(cat, "price", p_cat)
        post(mat, "volume", round(leaf_before + 500), fc=acct, fm=kids[0])
        post(mat, "price", lp, fc=acct, fm=kids[0])
        with app.test_request_context():
            wc = FL.working_copy(FINANCE_USER, V, M.FINANCE)
            shown = {k: (cell["cases"], cell["price"], cell["net_sales"]) for k, cell in wc.grid.cells.items()}
            n_typed = len(wc.typed)
        r = c.post("/finance/save", data={**page, "reason_code": "MARKET", "note": "test: the grid before saving equals the plan after"})
        assert r.status_code == 302
        new_files = sorted(set(M.FINANCE.files()) - landing_before)
        assert len(new_files) == 1, new_files
        assert FL.working_copy(FINANCE_USER, V, M.FINANCE) is None
        rows = q("select account_code, material_code, period, cases, price, net_sales, volume_edit_id, price_edit_id from plan.finance_plan where version_id = ?", V)
        model = {(V, x["account_code"], x["material_code"], x["period"]): (x["cases"], x["price"], x["net_sales"]) for x in rows}
        assert set(model) == set(shown), (len(model), len(shown))
        worst = {"cases": 0.0, "price": 0.0, "net_sales": 0.0}
        for k, (sc, sp, sn) in shown.items():
            mc, mp, mn = model[k]
            for name, a, b in (("cases", sc, mc), ("price", sp, mp), ("net_sales", sn, mn)):
                if a is None or b is None:
                    assert a is None and b is None, (k, name, a, b)
                    continue
                worst[name] = max(worst[name], abs(a - b))
        assert worst["cases"] < 0.005 and worst["net_sales"] < 0.005 and worst["price"] < 0.00005, worst
        reading = q("select standing, count(*) n from plan.finance_edit_reading where save_id = (select max(save_id) from plan.finance_edit where entered_by = ? and note like 'test:%') group by 1", FINANCE_USER)
        print(f"saved          {n_typed} figures, one file ({new_files[0].name}); after the scoped run every one of {len(model):,} cells equals the grid "
              f"(largest difference: {worst['cases']:.2e} cases, {worst['net_sales']:.2e} net sales); standing {[(x['standing'], x['n']) for x in reading]}")
        assert {x["standing"] for x in reading} <= {"held", "overwritten"}
        # the largest slice — all customers × all materials — with a run behind it, per edit
        timings.clear()
        for i in range(5):
            post("ALL", "volume", round(at("ALL", "ALL", "volume") + 1000))
        c.post("/finance/discard", data=page)
        print(f"per edit, All customers × All materials: {', '.join(f'{t * 1000:.0f}' for t in timings)} ms")
    finally:
        for f in set(M.FINANCE.files()) - landing_before:
            f.unlink()
        for f in set(chassis.CONFIG.receipts.glob("*.json")) - receipts_before:
            if "finance" in f.name or "run_" in f.name:
                f.unlink()
        session.become(FINANCE_USER)
        with app.test_request_context():
            FL.discard(FINANCE_USER, V)
            log = M.Runner(M.FINANCE_RUN).run()
        assert "✗" not in log, log[-800:]
        print("cleaned up: the test's file and receipts removed, Finance's part of the plan run again")


if __name__ == "__main__":
    main()
