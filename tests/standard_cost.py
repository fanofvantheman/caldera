"""The standard: a cost per case in four components, each read from the model that holds it (DEC-20261115-04) — read
only, against the warehouse and through the routes.

    uv run python -m tests.standard_cost        # from build/, with the warehouse built; writes nothing

Each component of a sample of materials is made again here from its own source and must equal plan.standard_cost:
material from the bill of materials and the input prices (the energy in the bill left to variable overhead), labour from
the route's crew and the production halls' loaded rate, variable overhead from the plant's cases-made schedule lines,
fixed overhead from the plant's other lines less the crews over the business plan's cases. The four sum to the standard;
Finance's cost of goods is volume × it wherever all four are read; the fixed overhead not absorbed is its own line, and
incurred less absorbed is it. The page answers, and at a location shows only that plant.
"""
from __future__ import annotations

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

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")


def close(a, b, tol=1e-6) -> bool:
    return abs((a or 0) - (b or 0)) <= tol * max(1.0, abs(b or 0))


def main() -> None:
    V = q("select version_id from dims.ctl_version where version_kind = 'latest_view' and status = 'open' order by version_id limit 1")[0]["version_id"]
    BP = q("select version_id, fiscal_year from dims.ctl_version where version_kind = 'business_plan'")[0]
    rows = q("select * from plan.standard_cost where version_id = ? and complete", V)
    assert rows, "no complete standard on the latest view"
    p0 = min(r["period"] for r in rows)
    sample = sorted((r for r in rows if r["period"] == p0), key=lambda r: r["material_code"])[::25]
    route = {r["material_code"]: r for r in q("select * from dims.ref_route where is_primary")}
    crew = {r["line_code"]: r["crew"] for r in q("select * from dims.ref_line_crew")}
    price = {r["material_code"]: r for r in q("select * from dims.reg_input_price")}
    kind = {r["material_code"]: r["material_type"] for r in q("select material_code, material_type from dims.dim_input_material")}
    idx = {(r["assumption_code"], r["period"]): r["value"] for r in q("select * from plan.assumption_in_force where version_id = ?", V)}
    cc_plant = {(r["entity_code"], r["cost_centre_code"]): r for r in q("select * from plan.ref_cost_centre_plant")}
    sched = q("select * from plan.opex_schedule where version_id = ?", V)
    weeks = {r["period"]: r["weeks_in_period"] for r in q("select period, weeks_in_period from dims.dim_period")}
    for s in sample:
        m, plant = s["material_code"], route[s["material_code"]]["plant_code"]
        # material: the bill × prices in force, the utility left out
        bom = q("select * from dims.ref_bom where parent_material = ? and plant_code = ?", m, plant)
        mat = sum(b["quantity_per_case"] * price[b["component_material"]]["price"] * idx.get((price[b["component_material"]]["index_code"], s["period"]), 100) / 100
                  for b in bom if kind.get(b["component_material"]) != "utility" and b["component_material"] in price)
        assert close(s["material_cost"], mat), (m, s["material_cost"], mat)
        # labour: crew ÷ cases an hour × the production halls' loaded rate
        ll = [r for r in q("select * from plan.labour_line where version_id = ? and period = ? and model = 'role'", V, s["period"])
              if (cc_plant.get((r["entity_code"], r["cost_centre_code"])) or {}).get("role") == "production" and cc_plant[(r["entity_code"], r["cost_centre_code"])]["plant_code"] == plant]
        rate = sum(r["wages"] + r["on_costs"] for r in ll) / sum(r["fte"] * 38 * weeks[s["period"]] for r in ll)
        lab = crew[route[m]["line_code"]] / route[m]["rate_cases_per_hour"] * rate
        assert close(s["labour_cost"], lab), (m, s["labour_cost"], lab)
        # variable overhead: the plant's cases-made lines, each line's rate once
        lines = {(x["entity_code"], x["cost_centre_code"], x["account_code"]): x["rate"] for x in sched
                 if (x["entity_code"], x["cost_centre_code"]) in cc_plant and cc_plant[(x["entity_code"], x["cost_centre_code"])]["plant_code"] == plant
                 and x["driver"] == f"cases_made_{plant.lower()}"}
        assert close(s["variable_overhead"], sum(lines.values())), (m, s["variable_overhead"], sum(lines.values()))
        assert close(s["std_cost"], s["material_cost"] + s["labour_cost"] + s["variable_overhead"] + s["fixed_overhead"])
    assert not q("""select 1 from plan.standard_cost s join dims.ref_bom b on b.parent_material = s.material_code
                    join dims.dim_input_material i on i.material_code = b.component_material and i.material_type = 'utility' limit 0""")
    print(f"components      {len(sample)} materials made again from their sources in {p0}: material, labour, variable overhead each equal; the four sum to the standard")

    # fixed overhead: the plant's other lines less the crews, over the business plan's cases at the plant for its year
    for plant in ("ECH", "LOX"):
        f = q("select distinct fixed_pool, denominator, denominator_version, fixed_overhead from plan.standard_cost where version_id = ? and plant_code = ?", V, plant)
        assert len(f) == 1 and f[0]["denominator_version"] == BP["version_id"], f
        den = q("""select sum(d.cases) c from plan.demand_financialised d join dims.ref_route r using (material_code) join dims.dim_period p on p.period = d.period
                   where r.is_primary and r.plant_code = ? and d.version_id = ? and p.fiscal_year = ?""", plant, BP["version_id"], BP["fiscal_year"])[0]["c"]
        assert close(f[0]["denominator"], den) and close(f[0]["fixed_overhead"], f[0]["fixed_pool"] / den)
        ab = q("select * from plan.standard_absorption where version_id = ? and plant_code = ?", V, plant)
        assert ab and all(close(a["under_absorbed"], a["fixed_overhead_incurred"] - (a["absorbed"] or 0), 1e-9) for a in ab)
        print(f"fixed overhead  {plant}: {f[0]['fixed_pool']:,.0f} over {den:,.0f} cases of {BP['version_id']} = {f[0]['fixed_overhead']:.4f} a case; "
              f"not absorbed over the year {sum(a['under_absorbed'] for a in ab):,.0f}")

    # Finance's cost of goods is volume × the standard, wherever all four are read
    bad = q("""select count(*) n from plan.finance_plan f join plan.standard_cost s on s.version_id = f.version_id and s.material_code = f.material_code
               and s.period = f.period and s.complete where abs(coalesce(f.std_cost, -1) - s.std_cost) > 1e-9 or abs(f.cogs - f.cases * s.std_cost) > 1e-6""")[0]["n"]
    n = q("select count(*) n from plan.finance_plan where version_id = ? and cogs is not null", V)[0]["n"]
    assert bad == 0 and n > 0, (bad, n)
    none_bp = q("select count(*) n from plan.finance_plan where version_id = ? and cogs is not null", BP["version_id"])[0]["n"]
    assert none_bp == 0, "a cost of goods valued on a version with no overhead on its schedule"
    print(f"Finance's grid  cost of goods = volume × the standard on all {n:,} cells of {V} that have one; none on {BP['version_id']}, whose standard is incomplete")

    # the page
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    session.become("finance.manager@caldera")
    html = c.get(f"/standard?version={V}&location=ECH").data.decode()
    assert "Standard by plant" in html and "Loxton" not in html.split("<main", 1)[1].split("Fixed overhead not absorbed")[0], "a plant outside the location"
    cogs = c.get(f"/revenue?version={V}&measure=cogs").data.decode()
    assert "Waits for" not in cogs
    print("page            Standard by plant at Echuca shows Echuca only; the Cost of goods tab is valued")


if __name__ == "__main__":
    main()
