"""The standard's four components on Finance's grid (DEC-20261115-04 point 4) — read only, against the warehouse, an
in-memory copy of the grid and the routes.

    uv run python -m tests.cost_components        # from build/, with the warehouse built; writes nothing

1. Every cell of Finance's plan with a standard carries the four per case from the standard by plant, and each one's
   cost — volume × it; the four per case sum to the standard and the four costs to cost of goods.
2. The register holds each per case as a ratio of its cost to volume, so a node reads cost ÷ volume — checked at every
   category — and the four read at a node still sum to the standard there.
3. In the business plan's year the fixed component is the rate held from it.
4. A volume typed moves the four costs with cost of goods (a copy of the grid, nothing saved).
5. The entry opens on Cost per case (DEC-20261116-01): the node in context carries the cost of a case and its four
   components, each row beneath one line — the component chosen beside the grid; the tiles are per case, each component
   opening the model that holds it; the year is the plan periods' cost per case weighted by their cases, the actual
   periods empty; the reading of money is not offered there. Cost of goods shows cases, cost per case and cost of goods,
   with the same year figure; Margin is valued.
"""
from __future__ import annotations

import os
import re
import sys
from collections import defaultdict
from pathlib import Path

BUILD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BUILD))
if os.environ.get("FACE_ROOT"):
    sys.path.insert(0, os.environ["FACE_ROOT"])

import chassis                                        # noqa: E402
from flask import url_for                             # noqa: E402
from chassis import app as chassis_app                # noqa: E402
from chassis.warehouse import q                       # noqa: E402

from calc.finance import COMPONENTS, aggregate, rules_from   # noqa: E402
from face import SHELL, roles, session                # noqa: E402
from face import __main__ as M                        # noqa: E402
from face import finance_live as FL                   # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
STD = {"uc_material": "material_cost", "uc_labour": "labour_cost", "uc_variable": "variable_overhead", "uc_fixed": "fixed_overhead"}


def close(a, b, tol=1e-6) -> bool:
    return a is not None and b is not None and abs(a - b) <= tol * max(1.0, abs(b))


def main() -> None:
    V = q("select version_id from dims.ctl_version where version_kind = 'latest_view' and status = 'open' order by version_id limit 1")[0]["version_id"]
    BP = q("select version_id, fiscal_year from dims.ctl_version where version_kind = 'business_plan' and base_version is null order by named_on limit 1")[0]

    # 1 · on every cell
    std = {(r["version_id"], r["material_code"], r["period"]): r for r in q("select * from plan.planned_unit_cost where complete")}
    cells = q("select * from plan.finance_plan where unit_cost is not null")
    for c in cells:
        s = std[(c["version_id"], c["material_code"], c["period"])]
        assert all(close(c[k], s[v], 1e-9) for k, v in STD.items()), c
        assert all(close(c[a], c["cases"] * c[k], 1e-9) for k, a in COMPONENTS.items()), c
        assert close(sum(c[k] for k in COMPONENTS), c["unit_cost"], 1e-9) and close(sum(c[a] for a in COMPONENTS.values()), c["cogs"], 1e-9), c
    bare = q("select count(*) n from plan.finance_plan where unit_cost is null and (uc_material is not null or cogs_material is not null)")[0]["n"]
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
        assert close(sum(per.values()), aggregate(cs, "unit_cost", rules)), cat
        shown.append(cat)
    allv = {k: aggregate(mine, k, rules) for k in COMPONENTS}
    print(f"register        each per case a ratio of its cost to volume; at {len(shown)} categories and the total the four read cost ÷ volume and sum to the standard "
          f"({V}: material {allv['uc_material']:.2f}, labour {allv['uc_labour']:.2f}, variable {allv['uc_variable']:.2f}, fixed {allv['uc_fixed']:.2f} "
          f"= {sum(allv.values()):.2f} a case)")

    # 3 · the fixed component in the business plan's year is the rate held from it
    held = q("""select count(*) n from plan.finance_plan f join plan.planned_unit_cost s using (version_id, material_code, period) join dims.dim_period p using (period)
                where f.version_id = ? and p.fiscal_year = ? and s.fixed_held and s.denominator_version = ? and abs(f.uc_fixed - s.fixed_overhead) < 1e-12""",
             V, BP["fiscal_year"], BP["version_id"])[0]["n"]
    inyear = q("""select count(*) n from plan.finance_plan f join dims.dim_period p using (period) where f.version_id = ? and p.fiscal_year = ? and f.unit_cost is not null""",
               V, BP["fiscal_year"])[0]["n"]
    assert held == inyear > 0, (held, inyear)
    print(f"held            {V}: all {held:,} cells in FY{BP['fiscal_year']} carry the fixed overhead per case held from {BP['version_id']}")

    # 4 · a volume typed moves the four costs (an in-memory copy; nothing saved)
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    with app.test_request_context():
        g = FL.base(V, M.FINANCE)[1].copy()
        c0 = max((c for c in g.cells.values() if c["version_id"] == V and c["unit_cost"] is not None and c["source"] == "fed"), key=lambda c: c["cases"] or 0)
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
    rules = FL.rules()
    side = c.get(f"/revenue?version={V}").data.decode().split("</aside>")[0]
    entry = re.search(r'<a href="([^"]*)"[^>]*>Cost of goods</a>', side).group(1).replace("&amp;", "&")
    h = c.get(entry).data.decode()
    tabs = re.findall(r'<nav class="tabs">(.*?)</nav>', h, re.S)[0]
    assert re.findall(r'>([^<]+)</a>', tabs) == ["Cost per case", "Cost of goods", "Margin", "Against standard"] and re.findall(r'class="active">([^<]+)', tabs) == ["Cost per case"], tabs
    body = h.split("<main", 1)[-1]
    top = re.search(r'<tbody id="fin-r-ALL">(.*?)</tbody>', body, re.S).group(1)
    assert re.findall(r'<td class="small muted">([^<]+)</td>', top) == [rules[m]["unit"] for m in M.FIN_TABS["unit_cost"]], top[:300]
    beneath = re.findall(r'<tbody id="fin-r-(?!ALL)[^"]+">(.*?)</tbody>', body, re.S)
    assert beneath and all(re.findall(r'<td class="small muted">([^<]+)</td>', b) == ["cost / case"] for b in beneath)
    assert "Finance plan" not in body.split('class="finwrap"')[0].split('class="toolbar"')[1] and "the rows beneath show" in body
    for ep in ("plan.standard", "plan.assumptions", "plan.headcount_role", "plan.entitlements", "plan.schedule"):
        with app.test_request_context():
            assert f'href="{url_for(ep)}' in body.split('id="fin-tiles"')[1].split('class="toolbar"')[0], ep
    lab = c.get(f"/revenue?version={V}&measure=unit_cost&part=uc_labour").data.decode().split("<main", 1)[-1]
    rows_lab = re.findall(r'<tbody id="fin-r-(?!ALL)[^"]+">(.*?)</tbody>', lab, re.S)
    assert rows_lab and all(re.findall(r'<td class="small muted">([^<]+)</td>', b) == ["labour / case"] for b in rows_lab)
    # the year reads across (DEC-20261117-01 point 7): actual and plan periods' cost per case weighted by their cases — an
    # actual period's the ledger's through the pools, apportioned to the material
    with app.test_request_context():
        g = FL.base(V, M.FINANCE)[1]
        vp = M.reads.version_periods(V)
        plan_in_fy = [p["period"] for p in vp["periods"] if not p["actual"] and p["fiscal_year"] == vp["fy"]]
        act_in_fy = [p["period"] for p in vp["periods"] if p["actual"] and p["fiscal_year"] == vp["fy"]]
        costed = [g.cells[k] for p in plan_in_fy for k in g.by_period.get((V, p), ()) if g.cells[k]["unit_cost"] is not None]
        ac = M.reads.actual_costs(act_in_fy)
        act = [(r["cases"], ac[(r["material_code"], r["period"])]["unit_cost"]) for r in M.reads.finance_actuals(act_in_fy) if (r["material_code"], r["period"]) in ac]
        want = (sum(x["cogs"] for x in costed) + sum(n * u for n, u in act)) / (sum(x["cases"] for x in costed) + sum(n for n, _ in act))
    cells = re.findall(r'<td class="n ([^"]*)"[^>]*>([^<]*)', top.split("</tr>")[0])
    year = next(v for k, v in cells if "tot" in k)
    assert vp["actual"] and act and all(v != "" for k, v in cells if "actual" in k) and year == f"{want:,.2f}", (year, want)
    tile = re.search(r'Cost of a case · FY\d+[^<]*</span><b>([^<]+)</b>', body).group(1)
    assert tile == year, (tile, year)
    print(f"cost per case   opens first; {len(beneath)} rows beneath, one line each (labour when chosen); tiles per case, each component opening its model; "
          f"the year {year} = actual and plan periods weighted by cases, the {len(act_in_fy)} actual periods of FY{vp['fy']} apportioned from the ledger; no reading of money offered")
    h = c.get(f"/revenue?version={V}&measure=cogs").data.decode()
    top = re.search(r'<tbody id="fin-r-ALL">(.*?)</tbody>', h, re.S).group(1)
    assert re.findall(r'<td class="small muted">([^<]+)</td>', top) == [rules[m]["unit"] for m in ("volume", "unit_cost", "cogs")], top[:300]
    assert "Finance plan" in h and "Cost of a case" in h
    m = c.get(f"/revenue?version={V}&measure=margin").data.decode()
    assert "Margin" in m and "Waits for" not in m and "Cost of a case" in m
    b = c.get(f"/revenue?version={BP['version_id']}&measure=unit_cost").data.decode()
    assert "fixed overhead / case" in b and "Waits for" not in b
    print("tabs            Cost of goods shows cases, cost per case and cost of goods; Margin valued; both carry the per-case tiles; "
          f"Cost per case the same on {BP['version_id']}")


if __name__ == "__main__":
    main()
