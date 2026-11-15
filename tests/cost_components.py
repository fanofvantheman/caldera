"""The standard's four components on Finance's grid (DEC-20261115-04 point 4) — read only, against the warehouse, an
in-memory copy of the grid and the routes.

    uv run python -m tests.cost_components        # from build/, with the warehouse built; writes nothing

1. Every cell of Finance's plan with a standard carries the four per case from the standard by plant, and each one's
   cost — volume × it; the four per case sum to the standard and the four costs to cost of goods.
2. The register holds each per case as a ratio of its cost to volume, so a node reads cost ÷ volume — checked at every
   category — and the four read at a node still sum to the standard there.
3. In the business plan's year the fixed component is the rate held from it.
4. A volume typed moves the four costs with cost of goods (a copy of the grid, nothing saved).
5. The Cost of goods tab shows the four and their sum per case; the Margin tab is valued.
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

from calc.finance import COMPONENTS, aggregate, rules_from   # noqa: E402
from face import SHELL, roles, session                # noqa: E402
from face import __main__ as M                        # noqa: E402
from face import finance_live as FL                   # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
STD = {"std_material": "material_cost", "std_labour": "labour_cost", "std_variable": "variable_overhead", "std_fixed": "fixed_overhead"}


def close(a, b, tol=1e-6) -> bool:
    return a is not None and b is not None and abs(a - b) <= tol * max(1.0, abs(b))


def main() -> None:
    V = q("select version_id from dims.ctl_version where version_kind = 'latest_view' and status = 'open' order by version_id limit 1")[0]["version_id"]
    BP = q("select version_id, fiscal_year from dims.ctl_version where version_kind = 'business_plan' and base_version is null order by named_on limit 1")[0]

    # 1 · on every cell
    std = {(r["version_id"], r["material_code"], r["period"]): r for r in q("select * from plan.standard_cost where complete")}
    cells = q("select * from plan.finance_plan where std_cost is not null")
    for c in cells:
        s = std[(c["version_id"], c["material_code"], c["period"])]
        assert all(close(c[k], s[v], 1e-9) for k, v in STD.items()), c
        assert all(close(c[a], c["cases"] * c[k], 1e-9) for k, a in COMPONENTS.items()), c
        assert close(sum(c[k] for k in COMPONENTS), c["std_cost"], 1e-9) and close(sum(c[a] for a in COMPONENTS.values()), c["cogs"], 1e-9), c
    bare = q("select count(*) n from plan.finance_plan where std_cost is null and (std_material is not null or cogs_material is not null)")[0]["n"]
    assert bare == 0
    by_v = defaultdict(int)
    for c in cells:
        by_v[c["version_id"]] += 1
    print(f"cells           {', '.join(f'{v} {n:,}' for v, n in sorted(by_v.items()))}: the four per case are the standard's, each cost volume × it; "
          "they sum to the standard and to cost of goods")

    # 2 · the register: ratios of cost to volume, read at every category
    rules = rules_from(q("select * from plan.ref_grid_measure"), "finance")
    for k, a in COMPONENTS.items():
        assert rules[k]["rollup"] == "ratio" and rules[k]["rollup_num"] == a and rules[k]["rollup_den"] == "volume" and rules[a]["rollup"] == "sum", k
    cats = q("select ancestor_code, descendant_code from dims.dim_material_hierarchy where ancestor_level = 'category' and descendant_level = 'material'")
    under = defaultdict(set)
    for r in cats:
        under[r["ancestor_code"]].add(r["descendant_code"])
    mine = [c for c in cells if c["version_id"] == V]
    shown = []
    for cat, ms in sorted(under.items()):
        cs = [c for c in mine if c["material_code"] in ms]
        if not cs:
            continue
        vol = sum(c["cases"] for c in cs)
        per = {k: aggregate(cs, k, rules) for k in COMPONENTS}
        assert all(close(per[k], sum(c[a] for c in cs) / vol) for k, a in COMPONENTS.items()), cat
        assert close(sum(per.values()), aggregate(cs, "std_cost", rules)), cat
        shown.append(cat)
    allv = {k: aggregate(mine, k, rules) for k in COMPONENTS}
    print(f"register        each per case a ratio of its cost to volume; at {len(shown)} categories and the total the four read cost ÷ volume and sum to the standard "
          f"({V}: material {allv['std_material']:.2f}, labour {allv['std_labour']:.2f}, variable {allv['std_variable']:.2f}, fixed {allv['std_fixed']:.2f} "
          f"= {sum(allv.values()):.2f} a case)")

    # 3 · the fixed component in the business plan's year is the rate held from it
    held = q("""select count(*) n from plan.finance_plan f join plan.standard_cost s using (version_id, material_code, period) join dims.dim_period p using (period)
                where f.version_id = ? and p.fiscal_year = ? and s.fixed_held and s.denominator_version = ? and abs(f.std_fixed - s.fixed_overhead) < 1e-12""",
             V, BP["fiscal_year"], BP["version_id"])[0]["n"]
    inyear = q("""select count(*) n from plan.finance_plan f join dims.dim_period p using (period) where f.version_id = ? and p.fiscal_year = ? and f.std_cost is not null""",
               V, BP["fiscal_year"])[0]["n"]
    assert held == inyear > 0, (held, inyear)
    print(f"held            {V}: all {held:,} cells in FY{BP['fiscal_year']} carry the fixed overhead per case held from {BP['version_id']}")

    # 4 · a volume typed moves the four costs (an in-memory copy; nothing saved)
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    with app.test_request_context():
        g = FL.base(V, M.FINANCE)[1].copy()
        c0 = max((c for c in g.cells.values() if c["version_id"] == V and c["std_cost"] is not None and c["source"] == "fed"), key=lambda c: c["cases"] or 0)
        key = (c0["version_id"], c0["account_code"], c0["material_code"], c0["period"])
        g.put(key, "volume", round(c0["cases"] * 1.5), "T-1")                # a volume at the grain, as Finance types it
        c1 = g.cells[key]
        assert close(c1["cases"], round(c0["cases"] * 1.5))
        assert all(close(c1[a], c1["cases"] * c1[k], 1e-9) for k, a in COMPONENTS.items()) and close(sum(c1[a] for a in COMPONENTS.values()), c1["cogs"], 1e-9)
    print(f"typed           {key[1]} × {key[2]} × {key[3]}: volume {c0['cases']:,.0f} → {c1['cases']:,.0f}; material cost {c0['cogs_material']:,.0f} → "
          f"{c1['cogs_material']:,.0f}, fixed {c0['cogs_fixed']:,.0f} → {c1['cogs_fixed']:,.0f}; the four still sum to cost of goods")

    # 5 · the tabs
    c = app.test_client()
    session.become("finance.manager@caldera")
    h = c.get(f"/revenue?version={V}&measure=cogs").data.decode()
    body = h.split("<main", 1)[-1]
    at = [body.find(w) for w in ("Material per case", "Labour per case", "Variable overhead per case", "Fixed overhead per case", "Standard cost", "Cost of goods")]
    assert all(i > 0 for i in at) and at[:5] == sorted(at[:5]), at
    m = c.get(f"/revenue?version={V}&measure=margin").data.decode()
    assert "Margin" in m and "Waits for" not in m
    b = c.get(f"/revenue?version={BP['version_id']}&measure=cogs").data.decode()
    assert "Fixed overhead per case" in b and "Waits for" not in b
    print("tabs            Cost of goods shows material, labour, variable and fixed overhead per case, then the standard and cost of goods; Margin valued; "
          f"the same on {BP['version_id']}")


if __name__ == "__main__":
    main()
