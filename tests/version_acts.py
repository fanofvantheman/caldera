"""Closing and reopening a version — checked through the routes, end to end, for a holder and a non-holder of the verb.

    uv run python -m tests.version_acts          # from build/, with the warehouse built; takes two scoped runs (~10 s each)

1. A person without `version.freeze` cannot close a version: the act is refused with a receipt and nothing is placed.
2. The version another is read against is not reopened, by anyone.
3. The holder closes the latest view: the act is placed and released by the version's own scoped run, and the version
   reads closed everywhere the face reads it.
4. On the closed version every entry is refused where it was refused for a frozen one: Finance's grid, the opex schedule,
   a layer entry, an assumption — and the version stays readable (its schedule and Finance's plan are still there).
5. Reopening asks for a reason; with one, the version is open again.
Everything it writes (the acts' files, the receipts) is removed afterwards and the version's state is run again, so the
plan is left as it was found.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BUILD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BUILD))

import chassis                                        # noqa: E402
from chassis import app as chassis_app                # noqa: E402
from chassis.warehouse import q                       # noqa: E402

from face import SHELL, roles, session                # noqa: E402
from face import __main__ as M                        # noqa: E402
from face import versions as VP                       # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
HOLDER, OTHER = "finance.manager@caldera", "plant.manager@caldera"
LIVE = {"Content-Type": "application/json", "X-Live": "1"}


def check(ok: bool, says: str) -> None:
    print(("✓ " if ok else "✗ ") + says)
    assert ok, says


def main() -> None:
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    files_before, receipts_before = set(VP.LANDING.files()), set(chassis.CONFIG.receipts.rglob("*.json"))
    with app.test_request_context():
        assert roles.may(HOLDER, VP.VERB) and not roles.may(OTHER, VP.VERB)
        LV = M.reads.default_version(); lv = M.reads.version(LV); REF = lv["reference_version"]
        P = M.reads.open_periods(LV)[0]
    state = lambda v: q("select state from plan.version_state where version_id = ?", v)[0]["state"]
    try:
        # 1. a non-holder cannot close
        session.become(OTHER)
        c.post("/versions/close", data={"version_id": LV, "reason": "test"})
        check(not session.last["placed"] and set(VP.LANDING.files()) == files_before and state(LV) == "open",
              f"{OTHER} (without the right) cannot close {LV}: refused, nothing placed")
        check("version.freeze" not in json.dumps(session.last), "the refusal says the right in words, not its code")
        # 2. the reference is not reopened
        session.become(HOLDER)
        c.post("/versions/reopen", data={"version_id": REF, "reason": "test"})
        check(not session.last["placed"] and any("read against" in x["says"] for x in session.last["checks"] if not x["ok"]),
              f"{REF} is not reopened — {LV} is read against it")
        # 3. the holder closes the latest view
        c.post("/versions/close", data={"version_id": LV, "reason": "test: cycle closed"})
        check(session.last["placed"] and state(LV) == "closed", f"{HOLDER} closes {LV}: placed, released, and the state reads closed")
        with app.test_request_context():
            check(M.reads.version(LV)["status"] == "closed" and LV not in [v["version_id"] for v in M.reads.open_versions()],
                  f"the face reads {LV} as closed and no longer offers it to enter on")
        # 4. refused everywhere, still readable
        page = {"version": LV, "fy": int(lv["fiscal_year"]), "customer": "ALL", "material": "ALL"}
        r = c.post("/finance/cell", data=json.dumps({"page": page, "node": "ALL", "period": P, "measure": "volume", "value": "1"}), headers=LIVE)
        check("is closed" in r.get_json().get("fin-status", ""), "Finance's grid refuses a figure on the closed version")
        sch = c.get(f"/schedule?version={LV}&fy=2028").data.decode()
        line = re.search(r'name="m\|([^|"]+)\|', sch)
        check(line is None, "the opex schedule offers no month to type on the closed version")
        some = q("select entity_code || '~' || cost_centre_code || '~' || account_code l, min(period) p from plan.opex_schedule where version_id = ? and state = 'calculated' group by 1 limit 1", LV)[0]
        r = c.post("/schedule/cell", data=json.dumps({"page": {"version": LV, "fy": 2028}, "cell": f"m|{some['l']}|{some['p']}", "value": "1"}), headers=LIVE)
        check("is closed" in r.get_json().get("sch-status", ""), "the opex schedule refuses a month posted on the closed version")
        c.post("/new", data={"layer_no": "2", "version_id": LV, "reason_code": "PROMO", "effect_type": "primary", "scope_material": "ALL", "scope_customer": "ALL",
                             "period_from": P, "period_to": P, "value_kind": "cases", "value": "10", "spread_rule": "baseline_shape", "note": "test"})
        check(not session.last["placed"] and any(x["check"] == "version open" and not x["ok"] for x in session.last["checks"]), "a layer entry on the closed version is refused")
        c.post("/assumptions/amend", data={"version": LV, "assumption_code": "CPI", "valid_from": P, "value": "0.04", "note": "test"})
        check(not session.last["placed"], "an assumption on the closed version is refused")
        n_sched = q("select count(*) n from plan.opex_schedule where version_id = ?", LV)[0]["n"]
        n_fin = q("select count(*) n from plan.finance_plan where version_id = ?", LV)[0]["n"]
        check(n_sched > 0 and n_fin > 0 and c.get(f"/revenue?version={LV}").status_code == 200, f"{LV} stays readable: {n_sched:,} schedule cells, {n_fin:,} of Finance's")
        # 5. reopening asks why
        c.post("/versions/reopen", data={"version_id": LV, "reason": ""})
        check(not session.last["placed"] and state(LV) == "closed", "reopening without a reason is refused")
        c.post("/versions/reopen", data={"version_id": LV, "reason": "test: a late change to the cycle"})
        check(session.last["placed"] and state(LV) == "open", f"{LV} reopened with a reason")
    finally:
        for f in set(VP.LANDING.files()) - files_before:
            f.unlink()
        for f in set(chassis.CONFIG.receipts.rglob("*.json")) - receipts_before:
            f.unlink()
        session.become(HOLDER)
        with app.test_request_context():
            M._run_plan(HOLDER, "versions")
        for f in set(chassis.CONFIG.receipts.rglob("*.json")) - receipts_before:
            f.unlink()
        print("cleaned up: the test's acts and receipts removed, the version's state run again — " + str(state(LV)))


if __name__ == "__main__":
    main()
