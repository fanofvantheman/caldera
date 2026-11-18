"""Stages and supersession — through the routes and two whole runs; everything it places is removed and the plan run again.

    uv run python -m tests.stages_supersession        # from build/, with the warehouse built; takes three runs

Stages (DEC-20261118-04):
1. The seed: the latest view's first four stages handed over at onboarding, taking no figures; the rest open; the business
   plan, closed, reads every stage handed over; inventory reads the demand plan as it stands.
2. Handing over demand valuation takes the demand plan's cases (a snapshot keyed by the act); refused to a person without
   the stage's right. After a run, inventory reads the snapshot; a demand entry placed after the handover moves the demand
   plan and not what inventory reads; inventory, handed over before, reads behind.
Supersession (DEC-20261118-01):
3. A Replace with a gain at run-out and a Temporary on weeks at one account, placed through Launches → Supersession
   (refused without the launch right): after the run the predecessor's baseline from the switch is off it and on the
   successor at its share, the uplift in the innovation layer, the run-out switch the week the stock on hand is sold down,
   and the Temporary only inside its weeks and at its account.
"""
from __future__ import annotations

import datetime as dt
import os
import subprocess
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
from face import stages as ST                         # noqa: E402
from face import supersession as SU                   # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
LV = "F202705"
FINANCE, PORTFOLIO, PLANNER = "finance.manager@caldera", "portfolio.marketing@caldera", "planner.westbrook@caldera"
RUN = [["uv", "run", "python", "-m", "ingest.pipeline"], ["uv", "run", "sqlmesh", "plan", "prod", "--restate-model", "*", "--auto-apply", "--no-prompts"]]


def run() -> None:
    for cmd in RUN:
        r = subprocess.run(cmd, cwd=BUILD, capture_output=True, text=True)
        assert r.returncode == 0 and "Error" not in r.stdout[-2000:], (cmd, r.stdout[-1500:], r.stderr[-1500:])


def landing_files() -> set:
    return set(chassis.CONFIG.landing.rglob("*.csv"))


def main() -> None:
    state = {r["stage"]: r["state"] for r in q("select stage, state from plan.stage_state where version_id = ?", LV)}
    assert [state[s] for s in ("demand", "valuation", "inventory", "production")] == ["handed over"] * 4 and state["materials"] == "open", state
    assert {r["state"] for r in q("select state from plan.stage_state where version_id = 'B202701'")} == {"handed over"}
    assert {r["read_as"] for r in q("select distinct read_as from plan.demand_handed_over where version_id = ?", LV)} == {"as it stands"}
    print("seed            F202705: demand, valuation, inventory and production handed over at onboarding, taking no figures; the rest open; "
          "B202701 closed, every stage handed over; inventory reads the demand plan as it stands")

    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    before = landing_files()
    try:
        # 2 · a handover takes the figures; refused without the right
        session.become(PLANNER)
        c.post(f"/stages/act?version={LV}", data={"stage": "valuation", "action": "hand_over"})
        assert landing_files() == before, "a handover by someone without the stage's right"
        session.become(FINANCE)
        h = c.get(f"/stages?version={LV}").data.decode()
        assert "Demand valuation" in h and "Hand over" in h and "not settled" in h
        c.post(f"/stages/act?version={LV}", data={"stage": "valuation", "action": "hand_over", "reason": "net sales agreed"})
        new = landing_files() - before
        acts = [p for p in new if "reg_stage_act" in str(p)]
        snaps = [p for p in new if "reg_stage_snap_demand" in str(p)]
        n_live = q("select count(*) n from (select n.node_code, d.material_code, d.week_id from plan.unconstrained_demand d join dims.ref_serving_node n using (ship_to_code) where d.version_id = ? group by all)", LV)[0]["n"]
        assert len(acts) == 1 and len(snaps) == 1 and sum(1 for _ in snaps[0].open()) - 1 == n_live, (len(acts), len(snaps))
        dem_before = q("select sum(cases) s from plan.unconstrained_demand where version_id = ? and account_code = 'WES'", LV)[0]["s"]
        flow_before = q("select sum(demand) s from plan.inventory_flow where version_id = ? and node_kind <> 'plant'", LV)[0]["s"]
        # a demand entry after the handover: +20% on Westbrook's snack cups over four periods
        e = dict(q("select * exclude (_dlt_load_id, _dlt_id, source_file, file_row_number) from bronze.layer_entry where entry_id = 'LE-06437'")[0])
        M.ENTRIES.place([{**e, "entry_id": "LE-TEST-STAGES", "value": 0.20, "entered_on": dt.date.today().isoformat(), "note": "test: after the handover", "copied_from": ""}], PLANNER)
        # 3 · supersession links
        session.become(FINANCE)
        c.post(f"/launches/supersession/set?version={LV}", data={"kind": "replace", "from_materials": "LITE_PEAR-CAN_410", "to_materials": "PEAR_HV-CAN_410", "reason": "test"})
        assert not [p for p in landing_files() - before if "reg_supersession" in str(p)], "a link by someone without the launch right"
        session.become(PORTFOLIO)
        assert "Make a link" in c.get(f"/launches/supersession?version={LV}").data.decode()
        c.post(f"/launches/supersession/set?version={LV}", data={"kind": "replace_gain", "from_materials": "LITE_PEAR-CAN_410", "to_materials": "PEAR_HV-CAN_410",
                                                                   "uplift_pct": "5", "uplift_reason": "the standard pack sells better", "reason": "lite range rationalised"})
        c.post(f"/launches/supersession/set?version={LV}", data={"kind": "temporary", "from_materials": "SAUCE_VEG-JAR_500", "to_materials": "SAUCE_OLIVE-JAR_500",
                                                                   "switch": "date", "switch_week": "2027W30", "end_week": "2027W38", "accounts": "WES", "reason": "promotional stand-in"})
        assert len([p for p in landing_files() - before if "reg_supersession" in str(p)]) == 2
        run()

        state = {r["stage"]: r for r in q("select * from plan.stage_state where version_id = ?", LV)}
        assert state["valuation"]["state"] == "handed over" and state["valuation"]["snapshot"] and state["inventory"]["state"] == "behind", {k: v["state"] for k, v in state.items()}
        assert {r["read_as"] for r in q("select distinct read_as from plan.demand_handed_over where version_id = ?", LV)} == {"handed over"}
        dem_after = q("select sum(cases) s from plan.unconstrained_demand where version_id = ? and account_code = 'WES'", LV)[0]["s"]
        flow_after = q("select sum(demand) s from plan.inventory_flow where version_id = ? and node_kind <> 'plant'", LV)[0]["s"]
        # the snapshot was taken before the links and the entry: what inventory reads has not moved
        assert dem_after != dem_before and abs(flow_after - flow_before) < 1e-6, (dem_before, dem_after, flow_before, flow_after)
        print(f"stages          valuation handed over by Finance (refused to a planner), taking {n_live:,} rows; after the run inventory reads them — the demand plan moved "
              f"{dem_after - dem_before:+,.0f} cases at Westbrook (an entry and two links placed after) and inventory's demand did not ({flow_after:,.0f}); inventory reads behind")

        sw = {r["link_id"]: r for r in q("select s.*, l.kind from plan.supersession_switch s join plan.supersession_link l using (version_id, link_id) where s.version_id = ?", LV)}
        rep = next(r for r in sw.values() if r["kind"] == "replace_gain")
        tmp = next(r for r in sw.values() if r["kind"] == "temporary")
        assert rep["switch"] == "run_out" and rep["run_out_week"] and rep["stock_at_start"] > 0 and tmp["switch_week"] == "2027W30"
        lines = q("select link_id, part, layer_no, material_code, min(week_id) w0, max(week_id) w1, sum(cases) c, string_agg(distinct account_code, ',') accts from plan.supersession_line where version_id = ? group by all", LV)
        by = {(l["link_id"], l["part"]): l for l in lines}
        off, on, up = by[(rep["link_id"], "off")], by[(rep["link_id"], "on")], by[(rep["link_id"], "uplift")]
        base = q("select sum(cases) c from plan.layer1_lines where version_id = ? and material_code = 'LITE_PEAR-CAN_410' and week_id >= ?", LV, rep["switch_week"])[0]["c"]
        assert abs(off["c"] + base) < 1e-6 and abs(on["c"] - base) < 1e-6 and abs(up["c"] - 0.05 * base) < 1e-6 and up["layer_no"] == 7 and off["w0"] >= rep["switch_week"]
        stack = q("""select sum(cases) c from plan.demand_stack where version_id = ? and material_code = 'LITE_PEAR-CAN_410' and layer_no = 1 and week_id >= ?""", LV, rep["switch_week"])[0]["c"]
        assert abs(stack or 0) < 1e-6, stack
        t_off = by[(tmp["link_id"], "off")]
        assert t_off["w0"] >= "2027W30" and t_off["w1"] <= "2027W38" and t_off["accts"] == "WES"
        h = c.get(f"/launches/supersession?version={LV}").data.decode()
        assert "Replace with a gain" in h and "Temporary" in h and "run-out" in h
        print(f"supersession    Replace with a gain LITE_PEAR → PEAR_HV switches at run-out, {rep['run_out_week']} ({rep['stock_at_start']:,.0f} cases on hand sold down): "
              f"{base:,.0f} cases of baseline off the predecessor and on the successor, +{up['c']:,.0f} uplift in innovation; the Temporary SAUCE_VEG → SAUCE_OLIVE "
              f"only at WES between {t_off['w0']} and {t_off['w1']}; refused without the launch right")

        # reopen takes the figures again; a withdrawal names the link
        session.become(FINANCE)
        mark = landing_files()
        c.post(f"/stages/act?version={LV}", data={"stage": "valuation", "action": "reopen", "reason": "a late price change"})
        assert any("reg_stage_snap_demand" in str(p) for p in landing_files() - mark) and any("reg_stage_act" in str(p) for p in landing_files() - mark)
        session.become(PORTFOLIO)
        c.post(f"/launches/supersession/withdraw?version={LV}", data={"link_id": tmp["link_id"], "reason": "not running"})
        assert any("reg_supersession" in str(p) for p in landing_files() - mark)
        print("reopen          a reopen takes the figures again (what was handed over stays read while the stage is worked); a link withdrawn as an act")
    finally:
        for p in landing_files() - before:
            p.unlink()
        run()
        assert {r["read_as"] for r in q("select distinct read_as from plan.demand_handed_over where version_id = ?", LV)} == {"as it stands"}
        assert q("select count(*) n from plan.supersession_line")[0]["n"] == 0
        print("cleaned up      every file the test placed removed and the plan run again — inventory reads as it stands, no link")


if __name__ == "__main__":
    main()
