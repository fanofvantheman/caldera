"""Naming a version from a base, and promoting it — checked through the routes.

    uv run python -m tests.version_fork              # from build/, with the warehouse built; takes four runs

Refused: by a person without the verb, without a reason, with a code already taken, and actual to a period after the last
closed one. Then the holder names a what-if from the latest view: after the run the new version is a copy — the demand
plan, the plan valued, Finance's plan and the opex schedule equal the base's cell for cell; every copied act keeps its
author and time and names the act it came from; the forecasting run and the promotions system's files are the base's,
read, not copied (no new row of either); the base's own figures have not moved; the latest view has not moved either.
Promoting the what-if makes it the latest view (the version a page opens on) and promoting the base again takes it back.
Then a version is named from the business plan actual to a later period: the receipt counts what was copied into what is
now actual, those entries read nothing, and the periods after are the business plan's. Everything it writes is removed
and the run taken again, so the plan is left as it was.
"""
from __future__ import annotations

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

# a version's figures, its own key taken out — and a copied act's own suffix, so a copy's line reads as its original's — so
# two versions can be laid against each other cell for cell: (key columns, figure columns)
FIGURES = {
    "demand plan": ("select material_code, ship_to_code, week_id, cases from plan.unconstrained_demand where version_id = ?", 3),
    "plan valued": ("select layer_no, regexp_replace(line_source, '@[^@]*$', '') ls, effect_type, material_code, ship_to_code, week_id, net_sales, gross_at_list "
                    "from plan.demand_financialised where version_id = ?", 6),
    "revenue bridge": ("select layer_no, period, cases, net_sales from plan.revenue_bridge where version_id = ?", 2),
    "Finance's plan": ("select account_code, material_code, period, cases, net_sales from plan.finance_plan where version_id = ?", 3),
    "opex schedule": ("select entity_code, cost_centre_code, account_code, period, amount from plan.opex_schedule where version_id = ?", 4),
    "promotions": ("select event_id, net_incremental_net_sales, net_return from plan.promo_event_effect where version_id = ?", 1),
}


def figures(v: str) -> dict[str, dict]:
    out = {}
    for k, (sql, n) in FIGURES.items():
        out[k] = {}
        for r in q(sql, v):
            x = list(r.values())
            out[k][tuple(x[:n])] = tuple(x[n:])
    return out


def same(a: dict, b: dict) -> str | None:
    """None when every grid has the same cells with the same figures — to a billionth of the figure (at least a
    millionth): a parallel sum adds in no fixed order, so two runs of the same plan differ in the last bits; else what
    differs."""
    for k in FIGURES:
        if a[k].keys() != b[k].keys():
            return f"{k}: {len(a[k].keys() ^ b[k].keys())} cells on one and not the other"
        worst = max((abs((x or 0) - (y or 0)) / max(1e3, abs(x or 0)) for c in a[k] for x, y in zip(a[k][c], b[k][c])), default=0)
        if worst > 1e-9:
            return f"{k}: a figure differs by {worst:.2e} of itself"
    return None


def landing_files() -> set:
    return set((BUILD / "data" / "landing").rglob("*.csv"))


def main() -> None:
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    landing_before, receipts_before = landing_files(), set(chassis.CONFIG.receipts.glob("*.json"))
    with app.test_request_context():
        LV = M.reads.default_version()
        lv = M.reads.version(LV)
    BP = lv["reference_version"]
    last_closed = q("select max(period) p from dims.dim_period where period_state = 'CLOSED'")[0]["p"]
    after_closed = q("select min(period) p from dims.dim_period where period > ?", last_closed)[0]["p"]
    W, B2 = f"{LV}-A", f"{BP}-A"
    ran = False

    def name(base, code, reason="test: a what-if", who=HOLDER, from_period=None):
        session.become(who)
        c.post("/versions/name", data={"base_version": base, "version_id": code, "reason": reason, "from_period": from_period or ""})
        return session.last

    def promote(v, who=HOLDER, reason="test: the what-if is the plan"):
        session.become(who)
        c.post("/versions/promote", data={"version_id": v, "reason": reason})
        return session.last

    try:
        assert not name(LV, W, who=OTHER)["placed"]
        assert not name(LV, W, reason="")["placed"]
        assert not name(LV, LV)["placed"] and any("already a version" in x["says"] for x in session.last["checks"] if not x["ok"])
        assert not name(LV, W, from_period=after_closed)["placed"] and any("never after the last closed" in x["says"] for x in session.last["checks"] if not x["ok"])
        assert landing_files() == landing_before
        print(f"refused         by {OTHER}, without a reason, as {LV} (taken), actual to {after_closed} (after the last closed); nothing placed")
        page = c.get("/versions").data.decode()
        assert 'action="/versions/name"' in page and f"{LV}-A" in page, "the naming form, with its suggested code"

        base_before = figures(LV)
        series_n = q("select count(*) n from bronze.fcst_series")[0]["n"]; sender_n = q("select count(*) n from bronze.tpm_event")[0]["n"]
        t = time.perf_counter()
        r = name(LV, W)
        assert r["placed"], r
        ran = True
        copied = next(x["says"] for x in r["checks"] if x["check"] == "what is copied")
        read = next(x["says"] for x in r["checks"] if x["check"] == "what is read, not copied")
        with app.test_request_context():
            w = M.reads.version(W)
            assert M.reads.default_version() == LV, "naming does not move the latest view"
        assert w and w["status"] == "open" and w["base_version"] == LV and w["from_period"] == lv["from_period"] and w["plan_through"] == lv["plan_through"], w
        page = c.get("/versions").data.decode()
        assert f"from {LV}" in page and 'action="/versions/promote"' in page and "the latest view" in page
        for addr in (f"/events?version={W}", f"/calendar?version={W}", f"/versions/history?version={W}"):
            assert c.get(addr).status_code == 200, addr
        assert c.get(f"/events?version={W}").status_code == 200
        print(f"named           {W} from {LV} in {time.perf_counter() - t:.0f} s — copied: {copied}; read, not copied: {read}")

        fork = figures(W)
        assert same(fork, base_before) is None, same(fork, base_before)
        assert same(figures(LV), base_before) is None, "the base's figures have not moved"
        print(f"a copy          {W} equals {LV} cell for cell: " + ", ".join(f"{k} {len(fork[k])}" for k in FIGURES) + f"; {LV} unchanged")

        # every copy names the act it came from and keeps who made it and when
        for sql in ["select e.copied_from, e.entered_by, e.entered_on, o.entered_by ob, o.entered_on oo from plan.layer_entry e join plan.layer_entry o on o.entry_id = e.copied_from where e.version_id = ?",
                    "select e.copied_from, e.entered_by, e.entered_on, o.entered_by ob, o.entered_on oo from plan.finance_edit e join plan.finance_edit o on o.edit_id = e.copied_from where e.version_id = ?",
                    "select e.copied_from, e.entered_by, e.entered_on, o.entered_by ob, o.entered_on oo from plan.schedule_edit e join plan.schedule_edit o on o.edit_id = e.copied_from where e.version_id = ?"]:
            rows = q(sql, W)
            assert rows and all(x["entered_by"] == x["ob"] and x["entered_on"] == x["oo"] for x in rows), sql
        n_stands = q("select count(*) n from plan.change_record where version_id = ? and record = 'demand plan' and act = 'entry' and standing in ('stands', 'overwritten')", LV)[0]["n"]
        assert q("select count(*) n from plan.layer_entry where version_id = ?", W)[0]["n"] == n_stands
        hist = q("select count(*) n from plan.change_record where version_id = ? and what like '%copied from%'", W)[0]["n"]
        # arrivals read, never copied
        runs = {(x["account_code"], x["run_id"]) for x in q("select account_code, run_id from plan.version_run where version_id = ?", LV)}
        assert runs and runs == {(x["account_code"], x["run_id"]) for x in q("select account_code, run_id from plan.version_run where version_id = ?", W)}
        assert q("select count(*) n from bronze.fcst_series")[0]["n"] == series_n and q("select count(*) n from bronze.tpm_event")[0]["n"] == sender_n
        assert {x["event_id"] for x in q("select event_id from plan.promo_event where version_id = ?", W)} == {x["event_id"] for x in q("select event_id from plan.promo_event where version_id = ?", LV)}
        print(f"lineage         every copied entry, figure and schedule act keeps its author and time and names its original ({hist} on the change history); "
              f"{len(runs)} forecasting runs and the promotions files read by both, no row of either copied; each event keeps its id on both")

        r = promote(W, who=OTHER)
        assert not r["placed"]
        r = promote(W)
        assert r["placed"], r
        with app.test_request_context():
            assert M.reads.default_version() == W and M.reads.version(W)["is_latest_view"] and not M.reads.version(LV)["is_latest_view"]
        assert same(figures(LV), base_before) is None, "a promotion moves nothing but which version is the latest view"
        assert not promote(W)["placed"] and any("already" in x["says"] for x in session.last["checks"] if not x["ok"])
        r = promote(LV, reason="test: back to the base")
        assert r["placed"], r
        with app.test_request_context():
            assert M.reads.default_version() == LV
        st = q("select standing from plan.change_record where record = 'versions' and act = 'promote' order by acted_at desc, act_id desc")
        assert [x["standing"] for x in st][:2] == ["stands", "overwritten"], st
        print(f"promoted        {W} became the latest view (pages open on it), whole, nothing moved; refused by {OTHER} and when already the latest; {LV} promoted back")

        bp_before = figures(BP)
        r = name(BP, B2, reason="test: the budget, from the last close", from_period=last_closed)
        assert r["placed"], r
        flag = next((x for x in r["checks"] if x.get("flag")), None)
        assert flag and "refused there" in flag["says"], r["checks"]
        b2 = q("select * from dims.ctl_version where version_id = ?", B2)[0]
        assert b2["from_period"] == last_closed and b2["horizon_start"] > last_closed
        gone = q("select count(*) n from plan.change_record where version_id = ? and record = 'demand plan' and standing = 'refused'", B2)[0]["n"]
        inside = q("select count(*) n from plan.unconstrained_demand u join dims.dim_week w using (week_id) where u.version_id = ? and w.period <= ?", B2, last_closed)[0]["n"]
        differ = q("""with a as (select material_code, ship_to_code, week_id, cases from plan.unconstrained_demand u join dims.dim_week w using (week_id) where u.version_id = ? and w.period > ?),
                           b as (select material_code, ship_to_code, week_id, cases from plan.unconstrained_demand u join dims.dim_week w using (week_id) where u.version_id = ? and w.period > ?)
                      select count(*) n from a full join b using (material_code, ship_to_code, week_id) where abs(coalesce(a.cases, 0) - coalesce(b.cases, 0)) > 1e-6""",
                   B2, last_closed, BP, last_closed)[0]["n"]
        assert gone and inside == 0 and differ == 0 and same(figures(BP), bp_before) is None, (gone, inside, differ)
        print(f"a new cycle     {B2} from {BP}, actual to {last_closed}: the receipt said {flag['says']}; {gone} copied entries refused on the change history, "
              f"nothing read in the actual periods, the periods after equal {BP}'s; {BP} unchanged")
    finally:
        session.become(HOLDER)
        for f in landing_files() - landing_before:
            f.unlink()
        for f in set(chassis.CONFIG.receipts.glob("*.json")) - receipts_before:
            f.unlink()
        if ran:
            with app.test_request_context():
                log = M.Runner(None).run()
            assert "✗" not in log, log[-800:]
            assert not q("select 1 from dims.ctl_version where version_id in (?, ?)", W, B2)
            assert same(figures(LV), base_before) is None
        print(f"cleaned up: the acts, copies and receipts removed, the run taken again — {W} and {B2} gone, {LV} as it was and the latest view")


if __name__ == "__main__":
    main()
