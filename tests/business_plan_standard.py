"""The standard set at the business plan (DEC-20261115-06) — read only, against the warehouse and through the routes.

    uv run python -m tests.business_plan_standard        # from build/, with the warehouse built; writes nothing

1. The business plan carries its own cost side over its year: a schedule over its twelve periods, its lines the first
   latest view's as declared on the day it was named (drivers; no month typed, adjusted or locked, no rate typed after),
   the labour model over its year, its capital plan charges on the schedule.
2. Its fixed overhead per case by plant is its fixed overhead for the year ÷ its cases at the plant for the year — made
   again here from what it does not absorb, which sums to nil over its year.
3. Every plan of that year holds the rate: the latest view's periods in the year take it; its periods past it take its
   own fixed overhead over its schedule's periods ÷ its own cases over the same periods.
4. Material, labour and variable overhead stay each plan's own.
5. The amount not absorbed splits into cost moved (the plan's incurred less the business plan's) and volume moved (the
   business plan's incurred less the rate × the plan's cases), which add to it; nothing split where the rate is the plan's own.
6. Finance's cost of goods is valued on the business plan: volume × its standard on every cell.
7. The pages: Standard by plant says where each year's rate was set; the business plan's schedule, Headcount and capital
   plan open read only, and a figure typed on its schedule is refused.
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
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
from face import schedule as S                        # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
LIVE = {"Content-Type": "application/json", "X-Live": "1"}


def close(a, b, tol=1e-6) -> bool:
    return abs((a or 0) - (b or 0)) <= tol * max(1.0, abs(b or 0))


def main() -> None:
    BP = q("select * from dims.ctl_version where version_kind = 'business_plan' and base_version is null order by named_on limit 1")[0]
    LV = q("""select * from dims.ctl_version where version_kind = 'latest_view' and fiscal_year = ? order by named_on, version_id limit 1""", BP["fiscal_year"])[0]
    B, V, FY = BP["version_id"], LV["version_id"], int(BP["fiscal_year"])
    fy_of = {r["period"]: int(r["fiscal_year"]) for r in q("select period, fiscal_year from dims.dim_period")}
    year = sorted(p for p, y in fy_of.items() if y == FY)

    # 1 · the business plan's own cost side
    sch = q("select * from plan.opex_schedule where version_id = ?", B)
    assert sorted({r["period"] for r in sch}) == year, "the business plan's schedule is not its year"
    first = {(a["entity_code"], a["cost_centre_code"], a["account_code"]): a for a in
             q("""select * from plan.schedule_edit where version_id = ? and action = 'driver' and entered_on::date <= ? order by entered_on, edit_id""", V, LV["named_on"])}
    drv = {(r["entity_code"], r["cost_centre_code"], r["account_code"]): r["driver"] for r in sch}
    carried = [k for k, a in first.items() if k in drv and drv[k] not in ("labour_model", "capex_model")]
    assert carried and all(drv[k] == first[k]["driver"] for k in carried), "a line not carried as first declared"
    assert not [r for r in sch if r["state"] in ("adjusted", "locked") or r["rate_typed"]], "a month or a rate of this cycle on the business plan"
    later = q("select * from plan.schedule_edit where version_id = ? and action = 'rate' and entered_on::date > ?", V, LV["named_on"])
    for a in later:
        k = (a["entity_code"], a["cost_centre_code"], a["account_code"])
        assert not any(r["rate_typed"] for r in sch if (r["entity_code"], r["cost_centre_code"], r["account_code"]) == k)
    lab = q("select count(distinct period) n, sum(wages) w from plan.labour_line where version_id = ?", B)[0]
    cap = q("select count(*) n from plan.opex_schedule where version_id = ? and driver = 'capex_model' and amount <> 0", B)[0]["n"]
    assert lab["n"] == 12 and lab["w"] > 0 and cap > 0, (lab, cap)
    print(f"cost side       {B}: schedule over {year[0]}–{year[-1]}, {len(carried)} lines carried from {V} as declared on {LV['named_on']} "
          f"({len(later)} rate typed after it not carried; no month typed); labour over 12 periods; {cap} capital plan charges")

    # 2 · its rate: fixed overhead for the year ÷ cases for the year, absorbing nil over the year
    std = q("select s.*, p.fiscal_year fy from plan.planned_unit_cost s join dims.dim_period p using (period) where version_id in (?, ?)", B, V)
    ab = q("select * from plan.standard_absorption where version_id in (?, ?)", B, V)
    rate = {}
    for plant in ("ECH", "LOX"):
        mine = [a for a in ab if a["version_id"] == B and a["plant_code"] == plant]
        inc, cases = sum(a["fixed_overhead_incurred"] for a in mine), sum(a["cases"] for a in mine)
        den = q("""select sum(d.cases) c from plan.demand_financialised d join dims.ref_route r using (material_code)
                   where r.is_primary and r.plant_code = ? and d.version_id = ?""", plant, B)[0]["c"]
        rate[plant] = inc / den
        rs = {r["fixed_overhead"] for r in std if r["version_id"] == B and r["plant_code"] == plant}
        assert len(rs) == 1 and close(rs.pop(), rate[plant]) and close(cases, den), (plant, rate[plant])
        assert abs(sum(a["under_absorbed"] for a in mine)) < 1e-3 and all(abs(a["cost_moved"]) < 1e-9 for a in mine)
        assert all(r["complete"] and r["fixed_held"] and r["denominator_version"] == B for r in std if r["version_id"] == B)
        print(f"rate            {plant}: {inc:,.0f} fixed over {den:,.0f} cases of {B} = {rate[plant]:.4f} a case; not absorbed over its year nil")

    # 3 · held on every plan of the year; the plan's own past it
    for plant in ("ECH", "LOX"):
        inside = [r for r in std if r["version_id"] == V and r["plant_code"] == plant and r["fy"] == FY]
        past = [r for r in std if r["version_id"] == V and r["plant_code"] == plant and r["fy"] != FY]
        assert inside and all(close(r["fixed_overhead"], rate[plant]) and r["fixed_held"] and r["denominator_version"] == B for r in inside)
        mine = [a for a in ab if a["version_id"] == V and a["plant_code"] == plant]
        own = sum(a["fixed_overhead_incurred"] for a in mine) / sum(a["cases"] for a in mine)
        assert past and all(close(r["fixed_overhead"], own) and not r["fixed_held"] and r["denominator_version"] == V for r in past), (plant, own)
        print(f"held            {plant}: {V}'s {len({r['period'] for r in inside})} periods of FY{FY} at {rate[plant]:.4f}; "
              f"its {len({r['period'] for r in past})} periods past it at its own {own:.4f}")

    # 4 · material, labour and variable overhead each plan's own
    sched = defaultdict(set)
    plant_of = {(r["entity_code"], r["cost_centre_code"]): r["plant_code"] for r in q("select * from plan.ref_cost_centre_plant")}
    for r in q("select * from plan.opex_schedule where version_id in (?, ?)", B, V):
        p = plant_of.get((r["entity_code"], r["cost_centre_code"]))
        if p and r["driver"] == f"cases_made_{p.lower()}":
            sched[(r["version_id"], p)].add((r["entity_code"], r["cost_centre_code"], r["account_code"], r["rate"]))
    for r in std:
        assert close(r["variable_overhead"], sum(x[3] for x in sched[(r["version_id"], r["plant_code"])])), r
    p0 = year[-1]
    both = {(r["version_id"], r["material_code"]): r for r in std if r["period"] == p0}
    diff = sum(1 for (v, m), r in both.items() if v == V and (B, m) in both and not close(r["labour_cost"], both[(B, m)]["labour_cost"]) or
               v == V and (B, m) in both and not close(r["variable_overhead"], both[(B, m)]["variable_overhead"]))
    print(f"own components  variable overhead on each plan is its own schedule's rates; in {p0} {diff} materials' labour or variable overhead differ between {V} and {B}")

    # 5 · cost moved and volume moved
    for a in ab:
        if a["version_id"] != V:
            continue
        if a["fixed_held"]:
            b = next(x for x in ab if x["version_id"] == B and x["plant_code"] == a["plant_code"] and x["period"] == a["period"])
            assert close(a["cost_moved"], a["fixed_overhead_incurred"] - b["fixed_overhead_incurred"], 1e-9)
            assert close(a["volume_moved"], b["fixed_overhead_incurred"] - a["absorbed"], 1e-9)
            assert close(a["cost_moved"] + a["volume_moved"], a["under_absorbed"], 1e-9)
        else:
            assert a["cost_moved"] is None and a["volume_moved"] is None
    held = [a for a in ab if a["version_id"] == V and a["fixed_held"]]
    print(f"split           {V}: {len(held)} plant-periods split — cost moved {sum(a['cost_moved'] for a in held):,.0f}, "
          f"volume moved {sum(a['volume_moved'] for a in held):,.0f}; the rest at its own rate, not split")

    # 6 · cost of goods valued on the business plan
    bad = q("""select count(*) n from plan.finance_plan f join plan.planned_unit_cost s using (version_id, material_code, period)
               where f.version_id = ? and (abs(f.unit_cost - s.unit_cost) > 1e-9 or abs(f.cogs - f.cases * s.unit_cost) > 1e-6)""", B)[0]["n"]
    n = q("select count(*) n, sum(cogs) c from plan.finance_plan where version_id = ? and cogs is not null", B)[0]
    assert bad == 0 and n["n"] > 0, (bad, n)
    print(f"cost of goods   {B}: valued on {n['n']:,} cells, {n['c']:,.0f} — volume × its standard on every one")

    # 7 · the pages
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    session.become("finance.manager@caldera")
    h = c.get(f"/standard?version={V}").data.decode()
    assert f"{B} — the business plan for the year" in h and f"no business plan for FY{FY + 1}" in h and "cost moved" in h, "the page does not say where each rate was set"
    h = c.get(f"/standard?version={B}").data.decode()
    assert f"{B} — the business plan for the year" in h and "not valued" not in h
    h = c.get(f"/schedule?version={B}&cc=CC_E_PROD").data.decode()
    assert "read only" in h and 'class="cell"' not in h and 'class="lock"' not in h, "the business plan's schedule takes input"
    page = {"version": B, "fy": 0, "cc": "CC_L_PROD", "entity": ""}
    r = json.loads(c.post("/schedule/cell", data=json.dumps({"page": page, "cell": f"m|{S.line_id(('RBF', 'CC_L_PROD', '6200'))}|{year[3]}", "value": "1"}),
                          headers=LIVE).data)
    assert "nothing is typed on it" in json.dumps(r), r
    assert S.working_copy("finance.manager@caldera", B) is None or not S.working_copy("finance.manager@caldera", B).acts
    h = c.get(f"/headcount/role?version={B}").data.decode()
    assert "Headcount by role" in h and B in h
    h = c.get(f"/capex?version={B}").data.decode()
    assert "Projects and depreciation" in h and 'action="/capex/enter"' not in h, "the business plan's capital plan takes a project"
    rv = c.get(f"/revenue?version={B}&measure=cogs").data.decode()
    assert "Waits for" not in rv
    print(f"pages           Standard by plant says where each year's rate was set; {B}'s schedule, Headcount and capital plan read only; a figure typed refused")


if __name__ == "__main__":
    main()
