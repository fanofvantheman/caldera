"""The standard and the planned unit cost against it — read only, through the warehouse and the routes.

    uv run python -m tests.standard_variance        # from build/, with the warehouse built; writes nothing

1. The standard is the business plan's own roll-up over its year: each input's standard price is its cost over the year ÷
   its quantity on that plan's cases; the standard material is Σ usage × price; labour hours × rate; the fixed rate the
   one held on every plan of the year. A year with no business plan has none.
2. On every cell the lines sum to the planned unit cost less the standard; the business plan nets to nil over its year.
3. Finance's grid carries the standard and each line per case and in money: each money = volume × its figure; cost of
   goods = cost at standard + the money against it on every cell with a standard.
4. Fixed spending and volume by pool add to the amount not absorbed's cost moved and volume moved.
5. The pages: Cost per case (planned, standard, against for the total and each component), Against standard (the lines,
   the tiles, by pool), Standard by plant (the standard, where it was set, the planned beside it).
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

from calc.finance import AGAINST, STANDARD            # noqa: E402
from face import SHELL, roles, session                # noqa: E402
from face import __main__ as M                        # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
FINANCE = "finance.manager@caldera"
LV, BP = "LV-2027P04", "BP-FY2027"


def close(a, b, tol=1e-6) -> bool:
    return (a is None and b is None) or (a is not None and b is not None and abs(a - b) <= tol * max(1.0, abs(b)))


def main() -> None:
    # 1 · the standard is the business plan's roll-up over its year
    years = {r["fiscal_year"] for r in q("select distinct fiscal_year from plan.standard_cost")}
    assert years == {2027}, years
    assert {r["set_on"] for r in q("select distinct set_on from plan.standard_cost")} == {BP}
    sample = q("select * from plan.standard_cost where fiscal_year = 2027 order by bp_cases desc limit 12")
    for s in sample:
        m, pl = s["material_code"], s["plant_code"]
        inputs = q("""select i.input_code, sum(i.per_case * d.c) as amount, sum(i.quantity * d.c) as qty from plan.planned_material_input i
                      join (select material_code, period, sum(cases) c from plan.demand_financialised where version_id = ? group by all) d using (material_code, period)
                      join dims.dim_period p on p.period = i.period
                      where i.version_id = ? and i.material_code = ? and p.fiscal_year = 2027 and d.c > 0 group by 1""", BP, BP, m)
        std = {r["input_code"]: r for r in q("select * from plan.standard_input where material_code = ? and plant_code = ? and fiscal_year = 2027", m, pl)}
        assert set(std) == {r["input_code"] for r in inputs}, m
        for r in inputs:
            assert close(std[r["input_code"]]["std_price"], r["amount"] / r["qty"]), (m, r["input_code"])
        assert close(s["std_material"], sum(x["std_quantity"] * x["std_price"] for x in std.values()))
        assert close(s["std_labour"], s["std_hours"] * s["std_rate"])
        held = q("select distinct fixed_overhead f from plan.planned_unit_cost u join dims.dim_period p using (period) where version_id = ? and material_code = ? and p.fiscal_year = 2027", LV, m)
        assert len(held) == 1 and close(held[0]["f"], s["std_fixed"]), (m, held)
        assert close(s["std_cost"], s["std_material"] + s["std_labour"] + s["std_variable"] + s["std_fixed"])
    fy28 = q("select count(*) n from plan.cost_variance v where fiscal_year = 2028")[0]["n"]
    assert fy28 == 0, "a year with no business plan read against a standard"
    print(f"standard        set on {BP} for FY2027 only; {len(sample)} materials made again from the business plan's own inputs, hours, rates and fixed rate")

    # 2 · the lines sum to planned − standard; the business plan nets to nil over its year
    bad = q("""select count(*) n from plan.cost_variance where abs(var_total - (coalesce(mat_price, 0) + coalesce(mat_usage, 0) + lab_rate + lab_eff + var_oh + fixed_oh)) > 1e-9
               or abs(var_total - (unit_cost - std_cost)) > 1e-9 or abs(var_material - (coalesce(mat_price, 0) + coalesce(mat_usage, 0))) > 1e-9
               or abs(var_labour - (lab_rate + lab_eff)) > 1e-9""")[0]["n"]
    n = q("select count(*) n from plan.cost_variance")[0]["n"]
    assert bad == 0 and n > 0, f"{bad} of {n} cells whose lines do not sum"
    assert q("select count(*) n from plan.cost_variance where abs(fixed_oh) > 1e-9")[0]["n"] == 0, "the fixed rate is held: no fixed variance per case"
    net = q("""select v.material_code, sum(v.var_total * d.c) money, sum(abs(v.var_total) * d.c) gross from plan.cost_variance v
               join (select material_code, period, sum(cases) c from plan.demand_financialised where version_id = ? group by all) d using (material_code, period)
               where v.version_id = ? group by 1""", BP, BP)
    worst = max(abs(r["money"]) for r in net)
    assert worst < 1.0, f"the business plan does not net to nil against its own standard: {worst}"
    print(f"lines           on all {n} cells price + usage + rate + efficiency + variable + fixed = planned − standard; {BP} nets to nil over its year on every material (largest {worst:.4f})")

    # 3 · Finance's grid carries them
    cells = q(f"select * from plan.finance_plan where version_id in (?, ?) and vs_total is not null", LV, BP)
    assert cells
    for c in cells:
        for pc, amt in {**STANDARD, **AGAINST}.items():
            assert close(c[amt], (c["cases"] or 0) * c[pc] if c[pc] is not None else None, 1e-9), (pc, c)
        assert close(c["cogs"], c["cogs_std"] + c["vsm_total"], 1e-9), c
    lv = q("select sum(vsm_total) m, sum(cogs) c, sum(cogs_std) s from plan.finance_plan where version_id = ? and vs_total is not null", LV)[0]
    print(f"grid            {len(cells)} cells with a standard: each line's money = volume × it; cost of goods = at standard + against on every one "
          f"({LV} FY2027: {lv['c']:,.0f} = {lv['s']:,.0f} + {lv['m']:,.0f})")

    # 4 · fixed spending and volume by pool
    ab = {(r["version_id"], r["plant_code"], r["period"]): r for r in q("select * from plan.standard_absorption where fixed_held")}
    fv = q("select version_id, plant_code, period, sum(spending) s, sum(volume) v from plan.fixed_variance group by all")
    assert fv and all(close(r["s"], ab[(r["version_id"], r["plant_code"], r["period"])]["cost_moved"], 1e-6) and
                      close(r["v"], ab[(r["version_id"], r["plant_code"], r["period"])]["volume_moved"], 1e-6) for r in fv)
    print(f"fixed           spending and volume by pool add to the amount not absorbed's cost moved and volume moved on {len(fv)} plant-periods")

    # 5 · the pages
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    session.become(FINANCE)
    html = c.get(f"/revenue?measure=unit_cost&version={LV}").data.decode()
    for unit in ("standard / case", "± total / case", "standard material / case", "± material / case", "± fixed / case"):
        assert unit in html, unit
    assert ">Against standard</a>" in html or "Against standard" in html.split("</aside>")[1]
    ag = c.get(f"/revenue?measure=against&version={LV}").data.decode()
    assert "Against standard" in ag and "material price / case" in ag and "labour efficiency / case" in ag and "By pool" in ag and "Spending" in ag
    assert " A</td>" in ag or " A<" in ag, "nothing marked adverse"
    st = c.get(f"/standard?version={LV}").data.decode()
    assert f"the standard set on {BP}" in st and "usage × price" in st
    st28 = c.get(f"/standard?version={LV}&fy=2028").data.decode()
    assert "no standard" in st28
    print("pages           Cost per case: planned, standard and against for the total and each component; Against standard: the lines, the tiles, by pool; "
          "Standard by plant: the standard and where it was set, none for FY2028")


if __name__ == "__main__":
    main()
