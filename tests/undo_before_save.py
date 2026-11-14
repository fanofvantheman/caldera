"""Undo and redo before a save — Finance's grid and the opex schedule, checked through the routes.

    uv run python -m tests.undo_before_save            # from build/, with the warehouse built; writes nothing

Finance's grid: a leaf figure, then a figure at its category that writes over it, then Undo — the leaf's figure is back
where the category had overwritten it; Undo again and the copy is the plan as saved, cell for cell; Redo twice and it is
exactly what was typed; a new figure after an Undo drops what was undone. A material started (its volume and its price)
is one step. The schedule: a month, a rate and a confirmed reset of a line, each one step, undone and redone in turn.
Nothing is saved: every check is on the working copy, which is discarded at the end, and no file reaches the landing.
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
    landing_before = set(M.FINANCE.files()) | set(S.LANDING.files())
    receipts_before = set(chassis.CONFIG.receipts.glob("*.json"))
    with app.test_request_context():
        V = M.reads.default_version()
        fy = int(M.reads.version(V)["fiscal_year"])
        P = M.reads.version_periods(V)["plan"][0]
    page = {"version": V, "fy": fy, "customer": "ALL", "material": "ALL"}

    def post(node, measure, value, fc="ALL", fm="ALL"):
        r = c.post("/finance/cell", data=json.dumps({"page": {**page, "customer": fc, "material": fm}, "node": node, "period": P, "measure": measure,
                                                     "value": str(value)}), headers=LIVE)
        assert r.status_code == 200, r.status_code

    def copy():
        with app.test_request_context():
            return FL.working_copy(FINANCE, V, M.FINANCE)

    def grid():
        wc = copy()
        return wc.grid if wc else FL.base(V, M.FINANCE)[1]

    def at(fc, node, measure="volume"):
        return FL.node_value(grid(), V, fc, node, P, measure)

    def cells_of(g, keys):
        return {k: (g.cells[k]["cases"], g.cells[k]["price"], g.cells[k]["net_sales"]) for k in keys}

    def same(a, b):
        return all(all((x is None and y is None) or (x is not None and y is not None and abs(x - y) < 1e-9) for x, y in zip(a[k], b[k])) for k in a)

    try:
        session.become(FINANCE)
        c.post("/finance/discard", data=page)
        with app.test_request_context():
            base = FL.base(V, M.FINANCE)[1]
            cat = max((n for n in M.reads.material_tree_under("ALL") if (FL.node_value(base, V, "ALL", n, P, "volume") or 0) > 0),
                      key=lambda n: FL.node_value(base, V, "ALL", n, P, "volume"))
            keys = base.scope(V, "ALL", cat, P)
            leaf = max((k for k in keys if base.cells[k]["source"] == "fed"), key=lambda k: base.cells[k]["cases"])
        acct, mat = leaf[1], leaf[2]
        saved = cells_of(base, keys)

        # 1 · a leaf figure, then its category over it
        leaf_v = round(at(acct, mat) + 700)
        post(mat, "volume", leaf_v, fc=acct, fm=cat)
        after_leaf = cells_of(grid(), keys)
        cat_v = round(at("ALL", cat) * 1.2)
        post(cat, "volume", cat_v)
        after_cat = cells_of(grid(), keys)
        assert abs(at("ALL", cat) - cat_v) < 1e-6 and abs(at(acct, mat) - leaf_v) > 1, "the category wrote over the leaf"
        assert len(copy().typed) == 1, "the leaf figure, written over everywhere, is not one to save"

        # 2 · Undo: the category's figure out — the leaf's figure is back where the category had overwritten it
        r = c.post("/finance/undo", data=page)
        assert r.status_code == 302
        assert abs(at(acct, mat) - leaf_v) < 1e-6 and same(cells_of(grid(), keys), after_leaf)
        assert [t.material for t in copy().typed] == [mat], "the leaf figure stands again and is the one to save"
        print(f"undo           {cat} × {P} out: {acct} × {mat} back at {leaf_v:,} cases, every cell beneath the category as after the leaf was typed")

        # 3 · Undo again: the plan as saved, cell for cell; nothing to undo after that
        c.post("/finance/undo", data=page)
        assert same(cells_of(grid(), keys), saved) and not copy().typed and not copy().touched.get("volume")
        html = c.get("/revenue?" + "&".join(f"{k}={v}" for k, v in page.items())).data.decode()
        assert "finance/redo" in html and "finance/undo" not in html and "typed and not saved" not in html
        r = c.post("/finance/undo", data=page, follow_redirects=True)
        assert "nothing typed to undo" in r.data.decode()
        print(f"undo           and again: all {len(keys):,} cells beneath {cat} are the plan as saved; the page offers Redo and no Undo")

        # 4 · Redo twice: exactly what was typed
        c.post("/finance/redo", data=page)
        assert same(cells_of(grid(), keys), after_leaf)
        c.post("/finance/redo", data=page)
        assert same(cells_of(grid(), keys), after_cat) and abs(at("ALL", cat) - cat_v) < 1e-6
        print(f"redo           twice: the leaf, then {cat} at {cat_v:,} — every cell as typed")

        # 5 · a new figure after an Undo drops what was undone
        c.post("/finance/undo", data=page)
        post(mat, "price", round(at(acct, mat, "price") + 0.25, 2), fc=acct, fm=cat)
        assert not copy().history.can_redo()
        r = c.post("/finance/redo", data=page, follow_redirects=True)
        assert "nothing undone to redo" in r.data.decode()
        print("new figure     after an Undo: nothing left to redo")

        # 6 · a material started is one step: its volume and its price go together
        with app.test_request_context():
            todo = [m for m in M.reads.account_materials(acct) if not base.scope(V, acct, m["code"], P)]
        if todo:
            n_before = len(copy().history.done)
            c.post("/finance/start", data={**page, "customer": acct, "add_material": todo[0]["code"], "add_period": P, "add_volume": "120", "add_price": "30"})
            assert len(copy().history.done) == n_before + 1 and len(copy().history.done[-1]) == 2
            c.post("/finance/undo", data=page)
            assert not grid().scope(V, acct, todo[0]["code"], P) or at(acct, todo[0]["code"]) in (None, 0)
            print(f"start          {todo[0]['code']} at {acct}: one step of two figures, undone together")
        c.post("/finance/discard", data=page)

        # 7 · the schedule: a month, a rate, a reset — each one step
        with app.test_request_context():
            sb = S.base(V)
        SP = sb["inp"].periods
        spage = {"version": V, "fy": fy, "cc": "CAL", "entity": ""}
        travel, elec = ("CF", "CC_SALES", "6950"), ("RBF", "CC_L_PROD", "6200")

        def scell(line, p):
            with app.test_request_context():
                return S.cells_for(FINANCE, V)[0][(*line, p)]

        def spost(cell, value):
            r = c.post("/schedule/cell", data=json.dumps({"page": spage, "cell": cell, "value": str(value)}), headers=LIVE)
            assert r.status_code == 200

        c.post("/schedule/discard", data=spage)
        m0, e0 = scell(travel, SP[1]), scell(elec, SP[2])
        spost(f"m|{S.line_id(travel)}|{SP[1]}", round(m0["amount"] + 9000))
        spost(f"r|{S.line_id(elec)}", 0.31)
        c.post("/schedule/reset", data={**spage, "line": S.line_id(travel), "period": [SP[1]]})
        assert scell(travel, SP[1])["state"] == "calculated"
        c.post("/schedule/undo", data=spage)                       # the reset out: the typed month is back
        assert scell(travel, SP[1])["state"] == "typed" and abs(scell(travel, SP[1])["amount"] - round(m0["amount"] + 9000)) < 1e-9
        c.post("/schedule/undo", data=spage)                       # the rate out
        assert abs(scell(elec, SP[2])["amount"] - e0["amount"]) < 1e-6 and scell(elec, SP[2])["rate"] == e0["rate"], (scell(elec, SP[2]), e0)
        html = c.get("/schedule?" + "&".join(f"{k}={v}" for k, v in spage.items())).data.decode()
        assert "schedule/undo" in html and "schedule/redo" in html
        c.post("/schedule/undo", data=spage)                       # the month out: as saved
        assert scell(travel, SP[1])["state"] == m0["state"] and abs(scell(travel, SP[1])["amount"] - m0["amount"]) < 1e-9
        c.post("/schedule/redo", data=spage); c.post("/schedule/redo", data=spage)
        assert scell(elec, SP[2])["rate"] == 0.31 and scell(travel, SP[1])["state"] == "typed"
        print(f"schedule       a month, a rate and a reset undone in turn to the schedule as saved; two redone — the month typed, the rate 0.31")
        c.post("/schedule/discard", data=spage)
        assert set(M.FINANCE.files()) | set(S.LANDING.files()) == landing_before, "nothing reaches the landing"
    finally:
        FL.discard(FINANCE, V)
        S.COPIES.drop(FINANCE, ("schedule", V))
        for f in set(chassis.CONFIG.receipts.glob("*.json")) - receipts_before:
            f.unlink()
    print("nothing saved; the working copies discarded")


if __name__ == "__main__":
    main()
