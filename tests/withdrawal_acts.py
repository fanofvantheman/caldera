"""Withdrawal after a save, one act across the grids, and the change history — checked through the routes.

    uv run python -m tests.withdrawal_acts            # from build/, with the warehouse built; takes two scoped runs

1. Finance's plan made again with nothing left out equals the plan as the run left it, cell for cell — the consequence
   page is calculated by the run's own arithmetic.
2. A Finance figure that wrote over an earlier one: the confirmation shows what will change; without a reason, or by a
   person without the verb, it is refused; withdrawn, the scoped run's plan equals what the confirmation said, the figure
   reads withdrawn and the earlier one stands again where it had been overwritten.
3. The opex schedule: one act withdrawn (a typed month) — the confirmation names the month, and after the run the month
   is driver × rate again, as said; the act stays on record, withdrawn, with the withdrawal beside it.
4. A layer entry: the confirmation shows its contribution leaving the demand plan; placed, it is a withdrawal row in the
   landing, in force after the next run (the file is removed, no run taken).
5. The change history page lists the acts with their standing and offers withdraw… to a holder only.

Everything it writes is removed afterwards and Finance's and the schedule's parts of the plan are run again.
"""
from __future__ import annotations

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
from face import finance_live as FL                   # noqa: E402
from face import schedule as S                        # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
FINANCE, OTHER, PLANNER = "finance.manager@caldera", "gm@caldera", "planner.westbrook@caldera"


def main() -> None:
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    landings = (M.FINANCE, S.LANDING, M.ENTRIES)
    before = {L: set(L.files()) for L in landings}
    receipts_before = set(chassis.CONFIG.receipts.glob("*.json"))
    with app.test_request_context():
        V = M.reads.default_version()
    ran = False
    try:
        # 1 · nothing left out: the plan made again equals the plan as the run left it
        with app.test_request_context():
            assert FL.without(V, "—nothing—") == [], "Finance's plan made again by the run's arithmetic equals the plan on file"
        n_cells = q("select count(*) n from plan.finance_plan where version_id = ?", V)[0]["n"]
        print(f"consequence    Finance's plan made again with nothing withdrawn: all {n_cells:,} cells as the run left them")

        # 2 · a Finance figure that wrote over an earlier one
        hit = q("""select overwritten_by, edit_id from plan.finance_edit_reading where version_id = ? and standing = 'overwritten' and overwritten_by is not null
                   and overwritten_by in (select edit_id from plan.finance_edit where state = 'in_force') order by entered_on desc limit 1""", V)
        assert hit, "a figure overwritten by a later one in force"
        later, earlier = hit[0]["overwritten_by"], hit[0]["edit_id"]
        with app.test_request_context():
            predicted = {(r["account_code"], r["material_code"], r["period"]): r for r in FL.without(V, later)}
        assert predicted, "withdrawing the later figure changes the plan"
        session.become(FINANCE)
        page = c.get(f"/withdrawal?grid=finance&id={later}&version={V}").data.decode()
        assert "What changes" in page and f"{len(predicted):,} cells" in page and "Withdraw the figure" in page, page[-1500:]
        r = c.post("/withdrawal", data={"grid": "finance", "id": later, "version": V, "reason": ""}, follow_redirects=True)
        assert "withdrawal refused" in r.data.decode() and "a withdrawal says why" in r.data.decode()
        session.become(OTHER)
        page = c.get(f"/withdrawal?grid=finance&id={later}&version={V}").data.decode()
        assert "Not withdrawn" in page and "does not hold" in page and "overlay.finance.enter" not in page
        print(f"refused        {later}: without a reason, and by {OTHER} (no verb) — the confirmation says so before anything is placed")
        session.become(FINANCE)
        r = c.post("/withdrawal", data={"grid": "finance", "id": later, "version": V, "reason": "test: the earlier figure stands again"})
        assert r.status_code == 302 and session.last["placed"], session.last
        ran = True
        plan = {(x["account_code"], x["material_code"], x["period"]): x for x in q("select * from plan.finance_plan where version_id = ?", V)}
        worst = max(abs((plan[k]["net_sales"] or 0) - (p["net_sales_after"] or 0)) for k, p in predicted.items() if k in plan)
        assert worst < 0.005, worst
        st = {x["edit_id"]: x["standing"] for x in q("select edit_id, standing from plan.finance_edit_reading where edit_id in (?, ?)", later, earlier)}
        assert st[later] == "withdrawn" and st[earlier] != "overwritten", st
        rec = q("select act, standing, names from plan.change_record where record = 'Finance''s plan' and (act_id = ? or names = ?)", later, later)
        assert {(x["act"], x["standing"]) for x in rec} == {("figure", "withdrawn"), ("withdrawal", "stands")}, rec
        print(f"withdrawn      {later}: after the scoped run every one of {len(predicted)} changed cells is what the confirmation said (largest difference {worst:.2e}); "
              f"the earlier {earlier} now {st[earlier]}")

        # 3 · the opex schedule: one act withdrawn
        act = q("select * from plan.schedule_edit where version_id = ? and action = 'month' and withdrawn_by_act is null order by entered_on desc limit 1", V)[0]
        line, p = (act["entity_code"], act["cost_centre_code"], act["account_code"]), act["period"]
        with app.test_request_context():
            b = S.base(V)
            after = S.compute(b["inp"], S.in_force(b["on_file"] + [{"action": "withdraw", "withdraws": act["edit_id"]}]), b["rules"])[(*line, p)]
        assert after["state"] == "calculated"
        page = c.get(f"/withdrawal?grid=schedule&id={act['edit_id']}&version={V}").data.decode()
        assert p in page and "months of the schedule" in page, page[-1500:]
        r = c.post("/withdrawal", data={"grid": "schedule", "id": act["edit_id"], "version": V, "reason": "test: back to driver × rate"})
        assert r.status_code == 302 and session.last["placed"], session.last
        cell = q("select * from plan.opex_schedule where version_id = ? and entity_code = ? and cost_centre_code = ? and account_code = ? and period = ?", V, *line, p)[0]
        assert cell["state"] == "calculated" and abs(cell["amount"] - after["amount"]) < 0.005, (cell, after)
        rec = {x["act"]: x["standing"] for x in q("select act, standing from plan.change_record where record = 'opex schedule' and (act_id = ? or names = ?)", act["edit_id"], act["edit_id"])}
        assert rec == {"month": "withdrawn", "withdraw": "stands"}, rec
        print(f"schedule       {act['edit_id']} ({line[2]} at {line[1]}, {p}) withdrawn: the month is driver × rate again, {cell['amount']:,.0f} as the confirmation said")

        # 4 · a layer entry: the confirmation, then the withdrawal row (in force after the next run)
        e = q("select entry_id, layer_no, entered_by from plan.layer_entry where version_id = ? and not withdrawn and layer_no = 2 order by entry_id limit 1", V)[0]
        session.become(e["entered_by"])
        page = c.get(f"/withdrawal?grid=demand&id={e['entry_id']}&version={V}").data.decode()
        assert "leaves the demand plan" in page and "after the next run" in page, page[-1500:]
        r = c.post("/withdrawal", data={"grid": "demand", "id": e["entry_id"], "version": V, "reason": "test: placed, never run"})
        if session.last["placed"]:
            new = set(M.ENTRIES.files()) - before[M.ENTRIES]
            assert len(new) == 1 and e["entry_id"] in next(iter(new)).read_text()
            print(f"demand plan    {e['entry_id']} by {e['entered_by']}: the confirmation shows its contribution leaving; the withdrawal is one row in the landing, in force after the next run")
        else:
            print(f"demand plan    {e['entry_id']}: {e['entered_by']} does not hold the layer's withdraw verb — refused: {session.last['checks']}")

        # 5 · the change history page
        session.become(FINANCE)
        page = c.get(f"/versions/history?version={V}").data.decode()
        assert "Change history" in page and "withdrawn" in page and "withdraw…" in page and later in page
        page = c.get(f"/versions/history?version={V}&record=opex+schedule").data.decode()
        assert act["edit_id"] in page
        session.become(OTHER)
        page = c.get(f"/versions/history?version={V}").data.decode()
        assert "Change history" in page and "withdraw…</a>" not in page
        print(f"history        {V}: every act with its standing; withdraw… offered to {FINANCE}, not to {OTHER}")
    finally:
        for L in landings:
            for f in set(L.files()) - before[L]:
                f.unlink()
        for f in set(chassis.CONFIG.receipts.glob("*.json")) - receipts_before:
            f.unlink()
        if ran:
            with app.test_request_context():
                log = M.Runner(M.FINANCE_RUN).run() + M.Runner(S.RUN).run()
            assert "✗" not in log, log[-800:]
        print("cleaned up: the test's files and receipts removed, Finance's and the schedule's parts of the plan run again")


if __name__ == "__main__":
    main()
