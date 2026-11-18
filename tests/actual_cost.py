"""A component typed over its drivers, the reconciliation of reported cost of goods, and an actual period's cost as
reported — through the warehouse and the routes; the acts it places are removed again.

    uv run python -m tests.actual_cost        # from build/, with the warehouse built

1. Typed over the drivers: the seeded typed component replaces its driver-based figure, is marked, keeps the driven figure
   beside it, and its variance is read whole (no price and usage); every untyped component is its drivers'. The Typed tab
   lists it; a figure typed by Finance is placed as one act, refused to a person without Finance's entry right and in an
   actual period; a withdrawal is placed as an act naming it (files removed).
2. The reconciliation: on every plant × period of every plan, at standard + each variance = as reported; a plan period's as
   reported is cases × the planned unit cost + the fixed overhead not absorbed; the Cost of goods tab draws it.
3. An actual period: the ledger's factory cost read through the pools equals, at each plant and period, the pools' actual;
   a pool's variance is actual − absorbed and a fixed pool's spending + volume is its variance; direct labour carries none;
   the materials' apportioned cost × their cases sums to the plant's actual to the dollar; a year with no standard reads
   its actual and no variance; the Cost per case tab shows the actual periods, marked apportioned.
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
from face import typed_cost as TC                     # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
LV = "F202705"
FINANCE, BUYER = "finance.manager@caldera", "supply.planner@caldera"


def close(a, b, tol=1e-6) -> bool:
    return (a is None and b is None) or (a is not None and b is not None and abs(a - b) <= tol * max(1.0, abs(b)))


def main() -> None:
    # 1 · typed over the drivers
    acts = q("select * from plan.unit_cost_act")
    assert acts, "no typed component standing"
    for a in acts:
        col = {"material": "material", "labour": "labour", "variable_overhead": "variable", "fixed_overhead": "fixed"}[a["component"]]
        u = q("select * from plan.planned_unit_cost where version_id = ? and material_code = ? and period = ?", a["version_id"], a["material_code"], a["period"])[0]
        cur = {"material": "material_cost", "labour": "labour_cost", "variable": "variable_overhead", "fixed": "fixed_overhead"}[col]
        assert u[f"typed_{col}"] and close(u[cur], a["per_case"]) and u[f"{col}_driven"] is not None and not close(u[f"{col}_driven"], a["per_case"])
        assert close(u["unit_cost"], (u["material_cost"] or 0) + (u["labour_cost"] or 0) + (u["variable_overhead"] or 0) + (u["fixed_overhead"] or 0))
        v = q("select * from plan.cost_variance where version_id = ? and material_code = ? and period = ?", a["version_id"], a["material_code"], a["period"])
        if v and a["component"] == "material":
            assert v[0]["mat_price"] is None and v[0]["mat_usage"] is None and close(v[0]["var_material"], u["material_cost"] - v[0]["std_material"])
    untyped = q("""select count(*) n from plan.planned_unit_cost where (not typed_material and material_cost is distinct from material_driven)
                   or (not typed_labour and labour_cost is distinct from labour_driven)""")[0]["n"]
    assert untyped == 0
    a0 = acts[0]
    print(f"typed           {len(acts)} standing — {a0['material_code']} {a0['component']} in {a0['period']} at {a0['per_case']:.4f} a case over its drivers; "
          "marked, the driven figure kept beside it, its variance read whole")

    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    session.become(FINANCE)
    html = c.get(f"/standard/typed?version={LV}").data.decode()
    assert a0["material_code"] in html and 'action="/standard/typed/type' in html and "Withdraw" in html
    before = set(TC.ACTS.files())
    c.post(f"/standard/typed/type?version={LV}", data={"material_code": a0["material_code"], "period": "2027P02", "component": "labour", "per_case": "0.9", "reason": "test"})
    assert set(TC.ACTS.files()) == before, "an actual period took a typed figure"
    session.become(BUYER)
    c.post(f"/standard/typed/type?version={LV}", data={"material_code": a0["material_code"], "period": "2027P09", "component": "labour", "per_case": "0.9", "reason": "test"})
    assert set(TC.ACTS.files()) == before, "a person without Finance's entry right typed a figure"
    session.become(FINANCE)
    c.post(f"/standard/typed/type?version={LV}", data={"material_code": a0["material_code"], "period": "2027P09", "component": "labour", "per_case": "0.9", "reason": "route not timed"})
    c.post(f"/standard/typed/withdraw?version={LV}", data={"act_id": a0["act_id"], "reason": "the bill is released"})
    new = set(TC.ACTS.files()) - before
    try:
        text = "".join(p.read_text() for p in new)
        assert len(new) == 2 and re.search(r",set,,F202705,CUP_ADULT-CUP_2x170,LOX,2027P09,labour,0\.9,route not timed,", text), text
        assert re.search(rf",withdraw,{a0['act_id']},F202705,", text), text
    finally:
        for p in new:
            p.unlink()
    print("typed page      the Typed tab lists it; refused in an actual period and without Finance's entry right; placed by Finance and withdrawn as acts (removed again)")

    # 2 · the reconciliation
    rec = q("select * from plan.cogs_reconciliation")
    assert rec and all(close(r["lines_sum"], r["as_reported"], 1e-9) for r in rec), "at standard + each variance is not as reported"
    plan_rows = q("""with c as (select version_id, material_code, period, sum(cases) c from plan.demand_financialised group by all),
                     u as (select u.version_id, u.plant_code, u.period, sum(c.c * u.unit_cost) at_planned from plan.planned_unit_cost u
                           join c using (version_id, material_code, period) where u.complete group by all)
                     select r.as_reported, u.at_planned, a.under_absorbed from plan.cogs_reconciliation r
                     join u using (version_id, plant_code, period)
                     left join plan.standard_absorption a using (version_id, plant_code, period) where r.basis = 'plan'""")
    assert plan_rows and all(close(r["as_reported"], r["at_planned"] + (r["under_absorbed"] or 0), 1e-9) for r in plan_rows)
    fy = q("""select sum(at_standard) s, sum(as_reported) rep, sum(as_reported) - sum(at_standard) - coalesce(sum(no_standard), 0) var from plan.cogs_reconciliation
              where version_id = ? and fiscal_year = 2027 and basis = 'plan'""", LV)[0]
    session.become(FINANCE)
    h = c.get(f"/revenue?version={LV}&measure=cogs").data.decode()
    assert "At standard, each variance, as reported" in h and "As reported" in h and "Fixed volume" in h
    print(f"reconciliation  {len(rec)} plant × periods: at standard + each variance = as reported; a plan period's is cases × the planned unit cost + not absorbed "
          f"({LV} FY2027 plan periods: {fy['s']:,.0f} at standard, {fy['var']:+,.0f} variances, {fy['rep']:,.0f} as reported); drawn on the Cost of goods tab")

    # 3 · an actual period
    ledger = {(r["plant_code"], r["period"]): r["a"] for r in q("""select c.plant_code, a.period, sum(a.amount) a from plan.cost_actual a
                  join plan.cost_pool_cell c on c.entity_code = a.entity_code and c.cost_centre_code = a.cost_centre_code and c.account_code = a.account_code
                  where a.state = 'mapped' and c.component is not null and c.plant_code is not null group by all""")}
    pools = q("select * from plan.actual_cost_pool")
    by: dict = {}
    for p in pools:
        by[(p["plant_code"], p["period"])] = by.get((p["plant_code"], p["period"]), 0.0) + p["actual"]
        if p["has_standard"]:
            assert close(p["variance"], p["actual"] - p["absorbed"], 1e-9)
            if p["component"] == "fixed_overhead":
                assert close(p["spending"] + p["volume"], p["variance"], 1e-9)
            if p["pool_code"] == "DIRECT_LABOUR":
                assert abs(p["variance"]) < 1e-6
        else:
            assert p["variance"] is None
    assert ledger and all(close(by.get(k), v, 1e-9) for k, v in ledger.items()), "the pools' actual is not the ledger's"
    mats = {(r["plant_code"], r["period"]): r["c"] for r in q("select plant_code, period, sum(unit_cost * cases) c from plan.actual_unit_cost group by all")}
    with_std = {(p["plant_code"], p["period"]) for p in pools if p["has_standard"]}
    assert with_std and all(abs(mats[k] - by[k]) < 0.01 for k in with_std), "the materials' apportioned cost does not sum to the plant's"
    no_std = [p for p in pools if p["fiscal_year"] < 2027]
    assert no_std and all(not p["has_standard"] for p in no_std)
    mat = q("select sum(actual) a, sum(absorbed) s from plan.actual_cost_pool where component = 'material' and fiscal_year = 2027")[0]
    h = c.get(f"/revenue?version={LV}&measure=unit_cost").data.decode()
    top = re.search(r'<tbody id="fin-r-ALL">(.*?)</tbody>', h, re.S).group(1)
    actual_cells = re.findall(r'<td class="n actual[^"]*"[^>]*>([^<]*)', top.split("</tr>")[0])
    assert actual_cells and all(x.strip() for x in actual_cells) and "apportioned" in top
    print(f"actual          {len(ledger)} plant × periods: the pools' actual is the ledger's; variance = actual − absorbed, fixed = spending + volume, direct labour none; "
          f"the materials' apportioned cost sums to the plant's on {len(with_std)} with a standard (FY2027 material {mat['a']:,.0f} against {mat['s']:,.0f} absorbed); "
          f"FY2026 and before actual, no variance; the Cost per case tab shows the {len(actual_cells)} actual periods, apportioned")


if __name__ == "__main__":
    main()
