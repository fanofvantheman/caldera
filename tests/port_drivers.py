"""The drivers of demand port, and Finance's figures and the schedule's locks — a Plan into the next (the business plan into
the latest view), through the Port page, with no run: what is placed is taken into the registers and read from there.
Everything it places is removed again and the registers taken in again.

    uv run python -m tests.port_drivers        # from build/, with the warehouse built

1. The declared list has two kinds: the override points and the drivers (a promotion typed here, a launch, a supersession
   link, an amended assumption); Finance's figures and the schedule's locks port.
2. What is offered: each driver and override placed on the business plan in a period the latest view still plans; not a
   promotion wholly before its from point, not a judgement entry on another layer; the same key with different terms is
   a clash (an assumption, a Finance figure, the business plan's own launches against the latest view's), and a launch
   is keyed on its cell, so the two Plans' launches meet as clashes rather than doubling.
3. Who ports: a person without a driver's right is refused, and nothing is placed.
4. The port: each row written into the latest view's register as typed, naming what it was ported from — a promotion
   under its own event, a Finance figure as the figure typed at its node with a save of its own and no cells, a lock as
   the lock; a clash kept writes nothing, a clash taken on a launch withdraws the latest view's own entry; a port act
   on the Plan. Finance's grid replays the ported figure by the latest view's own shape, so the node reads the figure.
5. A ported driver waiting marks its stage; manual recalculation leaves the rest behind.
6. A run takes them in: the latest view's promotion, link, launch (its own entry withdrawn), amendment, Finance figures
   and lock stand in the models; then everything is removed and the plan run again (two runs).
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import subprocess
import sys
import time
from pathlib import Path

BUILD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BUILD))
if os.environ.get("FACE_ROOT"):
    sys.path.insert(0, os.environ["FACE_ROOT"])

import chassis                                        # noqa: E402
from chassis import app as chassis_app                # noqa: E402
from chassis.landing import LogLanding                # noqa: E402
from chassis.warehouse import q                       # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")

from face import SHELL, reads, roles, session         # noqa: E402
from face import __main__ as M                        # noqa: E402
from face import finance_live as FL                   # noqa: E402
from face import overrides as O                       # noqa: E402

BP, LV = "B202701", "F202705"
RUN = [["uv", "run", "python", "-m", "ingest.pipeline"], ["uv", "run", "sqlmesh", "plan", "prod", "--restate-model", "*", "--auto-apply", "--no-prompts"]]


def run() -> None:
    for cmd in RUN:
        r = subprocess.run(cmd, cwd=BUILD, capture_output=True, text=True)
        assert r.returncode == 0, (cmd, r.stdout[-2000:], r.stderr[-2000:])
REGISTERS = ["reg_promo_event", "layer_entry", "reg_supersession", "reg_assumption_amend", "reg_finance_overlay", "reg_schedule_edit", "reg_version_act"]


def ingest() -> None:
    subprocess.run(["uv", "run", "python", "-m", "ingest.pipeline", "--only", *REGISTERS[:-1]], cwd=BUILD, check=True, capture_output=True)


def land(register: str) -> LogLanding:
    return LogLanding("plan", register, O._columns(register))


def main() -> None:
    pts = {p["point"]: p for p in O.points()}
    assert {p["kind"] for p in pts.values()} == {"override", "driver"}
    assert {k for k, p in pts.items() if p["kind"] == "driver"} == {"promotion", "launch", "supersession", "assumption"} and all(p["ports"] for p in pts.values())
    print("declared        override points and drivers, every one porting — Finance's figures and the schedule's locks among them")

    started = time.time()
    before = {r: set(land(r).files()) for r in REGISTERS}
    receipts_before = set((BUILD / "data/receipts").glob("*"))
    wk = q("select week_id, week_start from dims.dim_week where period = '2027P09' order by 1 limit 1")[0]
    who_promo, who_launch = reads.holders("register.promo_calendar.maintain")[0], reads.holders("layer.7.enter")[0]
    who_fin = reads.holders("overlay.finance.enter")[0]
    assert roles.may(who_fin, "register.assumptions.maintain") and roles.may(who_fin, "schedule.line.enter"), who_fin
    now = dt.datetime.now().isoformat(timespec="seconds")
    try:
        # what the business plan holds, placed as typed
        land("reg_promo_event").place([
            {"event_id": "EV-T-001", "version_id": BP, "account_code": "MER", "promo_group_code": "PG_REDGUM", "window_start": str(wk["week_start"]),
             "window_end": str(wk["week_start"] + dt.timedelta(days=13)), "mechanic": "price_cut", "tpr_per_case": 2.0, "scan_funding_per_case": 0, "fixed_fee": 5000,
             "media_fee": 0, "envelope_drawdown": 0, "status": "agreed", "owner": who_promo, "baseline_version": BP, "note": "a test event", "entered_on": now},
            {"event_id": "EV-T-002", "version_id": BP, "account_code": "MER", "promo_group_code": "PG_REDGUM", "window_start": "2026-09-02", "window_end": "2026-09-15",
             "mechanic": "price_cut", "tpr_per_case": 2.0, "status": "agreed", "owner": who_promo, "baseline_version": BP, "note": "before the from point", "entered_on": now}], who_promo)
        land("layer_entry").place([{"entry_id": "LE-T-J", "action": "enter", "version_id": BP, "layer_no": 2, "entered_by": "head.demand@caldera", "entered_on": now,
                                    "reason_code": "MARKET", "effect_type": "primary", "scope_material": "CUP_PEAR-CUP_4x120", "scope_customer": "MER",
                                    "period_from": "2027P09", "period_to": "2027P09", "value_kind": "cases", "value": 500, "spread_rule": "history_shape", "note": "a judgement"}], "head.demand@caldera")
        land("reg_supersession").place([{"act_id": "LNK-T-A", "link_id": "LNK-T", "action": "set", "version_id": BP, "kind": "replace", "from_material": "CUP_PEACH-CUP_4x120",
                                         "to_material": "CUP_PEAR-CUP_4x120", "share": 1.0, "switch": "week", "switch_week": wk["week_id"], "reason": "a test link",
                                         "entered_by": who_launch, "entered_at": now}], who_launch)
        land("reg_assumption_amend").place([{"amend_id": "AA-T-1", "version_id": BP, "assumption_code": "ENERGY_IDX", "valid_from": "2027P07", "value": 111.0, "note": "clash",
                                             "entered_by": who_fin, "entered_on": now},
                                            {"amend_id": "AA-T-2", "version_id": BP, "assumption_code": "ENERGY_IDX", "valid_from": "2027P11", "value": 112.0, "note": "new",
                                             "entered_by": who_fin, "entered_on": now}], who_fin)
        land("reg_finance_overlay").place([{"edit_id": "FE-T-1", "action": "enter", "save_id": "FS-T", "version_id": BP, "scope_customer": "MER", "scope_material": "CUP_PEAR-CUP_4x120",
                                            "period": "2027P08", "measure": "volume", "value": 900.0, "reason_code": "CUSTOMER", "entered_by": who_fin, "entered_on": now, "note": "clash"},
                                           {"edit_id": "FE-T-2", "action": "enter", "save_id": "FS-T", "version_id": BP, "scope_customer": "MER", "scope_material": "CUP_PEAR-CUP_4x120",
                                            "period": "2027P10", "measure": "volume", "value": 950.0, "reason_code": "CUSTOMER", "entered_by": who_fin, "entered_on": now, "note": "new"}], who_fin)
        land("reg_schedule_edit").place([{"edit_id": "SE-T-1", "save_id": "SS-T", "version_id": BP, "entity_code": "CF", "cost_centre_code": "CC_EXEC", "account_code": "6700",
                                          "action": "lock", "period": "2027P09", "value": 5000.0, "calc_at_entry": 4800.0, "reason_code": "METHOD", "note": "held",
                                          "entered_by": who_fin, "entered_on": now}], who_fin)
        ingest()

        # 2 · what is offered
        vs = {v["version_id"]: v for v in q("select * from dims.ctl_version")}
        ok, _, kind = O.pair(vs[BP], vs[LV])
        assert ok and kind == "next"
        offered = O.offer(vs[BP], vs[LV], kind)
        by = {(r["point"], r["act_id"]): r for r in offered}
        assert ("promotion", "EV-T-001") in by and ("promotion", "EV-T-002") not in by and ("launch", "LE-T-J") not in by
        assert by[("promotion", "EV-T-001")]["status"] == "port" and by[("supersession", "LNK-T-A")]["status"] == "port"
        assert by[("assumption", "AA-T-1")]["status"] == "clash" and by[("assumption", "AA-T-2")]["status"] == "port"
        assert by[("finance", "FE-T-1")]["status"] == "clash" and by[("finance", "FE-T-2")]["status"] == "port" and by[("schedule_lock", "SE-T-1")]["status"] == "port"
        launches = [r for r in offered if r["point"] == "launch"]
        clash_l = [r for r in launches if r["status"] == "clash"]
        assert clash_l and all(r["held"]["act_id"] for r in clash_l)
        print(f"offered         {len(offered)}: the promotion in a planned period and not the one before the from point, the link, two amendments (one a clash), two Finance "
              f"figures (one a clash), the lock; no judgement entry; {len(clash_l)} of the business plan's {len(launches)} launches meet the latest view's on their cell as clashes")

        app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
        c = app.test_client()
        page = c.get(f"/port?from={BP}&to={LV}").data.decode()
        assert "A promotion typed here" in page and "driver" in page and "EV-T-001" in page

        # 3 · who ports
        mid = {r: set(land(r).files()) for r in REGISTERS}
        session.become("supply.planner@caldera")
        c.post("/port", data={"from": BP, "to": LV, "take": ["promotion|EV-T-001"], "reason": "test"})
        assert all(set(land(r).files()) == mid[r] for r in REGISTERS), "ported without the right"
        print("who             a promotion refused to the supply planner, nothing placed")

        # 4 · the port, twice: the drivers of demand, then Finance's
        take_l = clash_l[0]
        session.become(who_launch)                      # the innovation layer's holder: the link and a launch, its clash taken
        c.post("/port", data={"from": BP, "to": LV, "take": ["supersession|LNK-T-A", take_l["id"]], f"choose:{take_l['id']}": "take", "reason": "test drivers"})
        session.become(who_promo)                       # the calendar's keeper: the promotion
        c.post("/port", data={"from": BP, "to": LV, "take": ["promotion|EV-T-001"], "reason": "test drivers"})
        session.become(who_fin)
        c.post("/port", data={"from": BP, "to": LV, "take": ["assumption|AA-T-1", "assumption|AA-T-2", "finance|FE-T-1", "finance|FE-T-2", "schedule_lock|SE-T-1"],
                              "choose:assumption|AA-T-1": "keep", "choose:finance|FE-T-1": "take", "reason": "test finance"})
        new = {r: [row for f in sorted(set(land(r).files()) - mid[r]) for row in csv.DictReader(open(f, newline=""))] for r in REGISTERS}
        ev = [x for x in new["reg_promo_event"]]
        assert len(ev) == 1 and ev[0]["event_id"] == "EV-T-001" and ev[0]["version_id"] == LV and ev[0]["ported_from"] == "EV-T-001" and ev[0]["tpr_per_case"] in ("2.0", "2")
        ln = new["layer_entry"]
        assert len(ln) == 2 and {x["action"] for x in ln} == {"enter", "withdraw"} and next(x for x in ln if x["action"] == "withdraw")["withdraws"] == take_l["held"]["act_id"]
        assert next(x for x in ln if x["action"] == "enter")["value"] in (str(take_l["figures"]["value"]), repr(take_l["figures"]["value"]))
        sl = new["reg_supersession"]
        assert len(sl) == 1 and sl[0]["link_id"] == "LNK-T" and sl[0]["act_id"] != "LNK-T-A" and sl[0]["version_id"] == LV
        aa = new["reg_assumption_amend"]
        assert len(aa) == 1 and aa[0]["valid_from"] == "2027P11" and aa[0]["ported_from"] == "AA-T-2", aa
        fe = new["reg_finance_overlay"]
        assert len(fe) == 2 and all(x["action"] == "enter" and x["version_id"] == LV and x["save_id"].startswith("FS-") and x["save_id"] != "FS-T" for x in fe)
        assert {x["ported_from"] for x in fe} == {"FE-T-1", "FE-T-2"} and not any(x.get("typed") for x in fe), "a Finance figure ports without its cells"
        se = new["reg_schedule_edit"]
        assert len(se) == 1 and se[0]["action"] == "lock" and se[0]["value"] in ("5000.0", "5000") and se[0]["version_id"] == LV
        acts = [x for x in new["reg_version_act"] if x["act"] == "port"]
        assert len(acts) >= 2 and all(x["version_id"] == LV for x in acts)
        with app.test_request_context():
            g = FL.base(LV, M.FINANCE)[1]
            at8 = FL.node_value(g, LV, "MER", "CUP_PEAR-CUP_4x120", "2027P08", "volume")
            at10 = FL.node_value(g, LV, "MER", "CUP_PEAR-CUP_4x120", "2027P10", "volume")
        assert abs(at8 - 900) < 1e-6 and abs(at10 - 950) < 1e-6, (at8, at10)
        print("ported          the promotion under its own event, the link under a new act, a launch taken over the latest view's own (its entry withdrawn), one amendment "
              f"(the clash kept), two Finance figures as typed at their node with a save of their own — the grid reads {at8:,.0f} and {at10:,.0f} by the latest view's shape — the lock; port acts on the Plan")

        # 5 · behind
        b = O.behind(LV)
        assert b.get("demand") == "overrides waiting" and b.get("finance") in ("overrides waiting", "behind") and b.get("statements") == "behind", b
        print(f"behind          demand reads overrides waiting, every stage after it behind (recalculation {O.mode()})")

        # 6 · a run takes them in
        run()
        assert q("select count(*) n from plan.promo_typed_event where version_id = ? and event_id = 'EV-T-001'", LV)[0]["n"] == 1
        assert q("select count(*) n from plan.supersession_link where version_id = ? and link_id = 'LNK-T'", LV)[0]["n"] == 1
        held_state = q("select * from plan.layer_entry where entry_id = ?", take_l["held"]["act_id"])
        assert held_state and held_state[0]["withdrawn"], held_state
        ported_l = next(x for x in ln if x["action"] == "enter")["entry_id"]
        assert q("select count(*) n from plan.layer_entry where entry_id = ?", ported_l)[0]["n"] == 1
        amended = q("select value, amend_id from plan.assumption_in_force where version_id = ? and assumption_code = 'ENERGY_IDX' and period = '2027P11'", LV)[0]
        assert amended["value"] == 112.0 and amended["amend_id"] == aa[0]["amend_id"], amended
        fstate = {r["ported"]: r["state"] for r in q("select b.ported_from ported, e.state from plan.finance_edit e join bronze.reg_finance_overlay b using (edit_id) where e.version_id = ? and b.ported_from in ('FE-T-1', 'FE-T-2')", LV)}
        assert fstate == {"FE-T-1": "in_force", "FE-T-2": "in_force"}, fstate
        at = {r["period"]: r["cases"] for r in q("""select period, sum(cases) cases from plan.finance_plan where version_id = ? and account_code = 'MER'
                                                    and material_code = 'CUP_PEAR-CUP_4x120' and period in ('2027P08', '2027P10') group by 1""", LV)}
        assert abs(at["2027P08"] - 900) < 1e-6 and abs(at["2027P10"] - 950) < 1e-6, at
        lock = q("select * from plan.opex_schedule where version_id = ? and entity_code = 'CF' and cost_centre_code = 'CC_EXEC' and account_code = '6700' and period = '2027P09'", LV)
        assert lock and abs(sum(r["amount"] for r in lock) - 5000) < 1e-6, lock
        print("run             the promotion, the link, the launch over the latest view's own (withdrawn), the amendment, both Finance figures (900 and 950 cases) and the lock (5,000) stand in the latest view")
    finally:
        for r in REGISTERS:
            for f in set(land(r).files()) - before[r]:
                f.unlink()
        for f in set((BUILD / "data/receipts").glob("*")) - receipts_before:
            if f.stat().st_mtime >= started - 1:
                f.unlink()
        run()
        print("cleaned up: every file placed and ported removed, the plan run again")


if __name__ == "__main__":
    main()
