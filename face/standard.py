"""Standard by plant (DEC-20261115-04): the cost of a case of each material at its plant, in four components — material,
labour, variable overhead, fixed overhead — each read from the model that already holds it (plan.standard_cost), and
the fixed overhead the plan's cases do not absorb, a line of its own (plan.standard_absorption). Read only: the standard
is changed where each component is kept — the input prices, the routes and crews, the schedule, the capital plan.

Registered on the plan's blueprint by `register(...)`, called once from `face/__main__.py`."""
from __future__ import annotations

from collections import defaultdict

from chassis.warehouse import Busy, q

PAGE = """<h1>Standard by plant<small>{{ version }} · {{ period }} · {{ where }} — the cost of a case in four components, each read from the model that holds it</small></h1>
<div class="cards">{% for p in plants %}<div class="card stat"><b>{{ '{:,.2f}'.format(p.avg) if p.avg is not none else '—' }}</b><span>{{ p.plant_name }} · cost of a case, weighted by {{ period }}'s cases · fixed overhead {{ '{:,.2f}'.format(p.fixed_per_case) if p.fixed_per_case is not none else '—' }} a case on {{ '{:,.0f}'.format(p.denominator or 0) }} cases ({{ p.denominator_version or '—' }})</span></div>{% endfor %}</div>
{% if not complete %}<p class="hint">{{ version }} has no overhead on its schedule — a closed version carries no opex schedule — so only the material and labour components are read; cost of goods is not valued on it.</p>{% endif %}
<table><thead><tr><th>Material</th><th>Plant</th><th class="n">Material</th><th class="n">Labour</th><th class="n">Variable overhead</th><th class="n">Fixed overhead</th><th class="n">Standard</th><th class="n">Cases {{ period }}</th></tr></thead><tbody>
{% for r in rows %}<tr class="{{ 'grp' if r.node }}"><td>{% if r.node %}<b>{{ r.label }}</b>{% else %}{{ r.label }} <span class="small muted">{{ r.code }}</span>{% endif %}</td><td class="small">{{ r.plant_code or '' }}</td>
<td class="n">{{ money(r.material_cost) }}</td><td class="n">{{ money(r.labour_cost) }}{% if r.crew_hours %}<span class="src">{{ '%.4f'|format(r.crew_hours) }} h × {{ '%.2f'|format(r.loaded_rate) }}</span>{% endif %}</td><td class="n">{{ money(r.variable_overhead) }}</td><td class="n">{{ money(r.fixed_overhead) }}</td><td class="n"><b>{{ money(r.std_cost) }}</b></td><td class="n">{{ '{:,.0f}'.format(r.cases or 0) }}</td></tr>
{% else %}<tr><td colspan="8" class="muted">No material planned here in {{ period }}.</td></tr>{% endfor %}</tbody></table>
<p class="hint">Per case. <b>Material</b>: the bill of materials at the plant × each input's price in force (its price × its index in the assumptions ÷ 100; imported inputs landed) — the energy in the bill is the schedule's, so it is in variable overhead, not here. <b>Labour</b>: the route's crew ÷ its cases an hour × the loaded hourly rate of the plant's production halls in the period (wages and on-costs over paid hours, from the labour model). <b>Variable overhead</b>: the plant's factory cost centres' schedule lines driven by cases made there, at each line's rate. <b>Fixed overhead</b>: those cost centres' other lines over the schedule's planned periods — every position but the crews, depreciation and production leases from the capital plan, the rest — over the denominator declared on the version, the business plan's cases at the plant for its year. Above a material, a node's figure is its cost ÷ its cases.</p>
<h2>Fixed overhead not absorbed<span class="count">each plant's fixed overhead in the period against what the standard absorbs on the plan's cases — a line of its own, never in the unit cost</span></h2>
<table><thead><tr><th>Plant</th>{% for p in abs_periods %}<th class="n">{{ p[2:4] }}·{{ p[5:] }}</th>{% endfor %}<th class="n">Total</th></tr></thead><tbody>
{% for a in absorption %}<tr><td>{{ a.plant_name }}<div class="small muted">incurred · absorbed · not absorbed</div></td>{% for p in abs_periods %}{% set x = a.by.get(p) %}<td class="n small">{% if x %}{{ money(x.fixed_overhead_incurred) }}<br>{{ money(x.absorbed) }}<br><b>{{ money(x.under_absorbed) }}</b>{% endif %}</td>{% endfor %}<td class="n"><b>{{ money(a.total) }}</b></td></tr>{% endfor %}</tbody></table>
<p class="hint">Positive: fixed cost the period's cases do not carry at the standard — a low-volume period, or a plant whose volume is below the year it is absorbed on. The standard holds through the year; the forecast reads the difference here.</p>"""
MACRO = """{% macro money(x) %}{{ '' if x is none else '{:,.2f}'.format(x) }}{% endmacro %}"""


def register(bp, page, who_fn, ctx_fn, busy) -> None:
    from . import reads

    @bp.get("/standard")
    def standard():
        try:
            c = ctx_fn()
            version = c.get("version") or reads.default_version()
            loc = c.get("location") or "ALL"
            mat = c.get("material") or "ALL"
            vp = reads.version_periods(version)
            period = (vp["plan"] or [""])[0]
            rows = q("select * from plan.standard_cost where version_id = ? and period = ?", version, period)
            cases = {r["material_code"]: r["c"] for r in q("select material_code, sum(cases) c from plan.demand_financialised where version_id = ? and period = ? group by 1", version, period)}
            under = {r["d"] for r in q("select descendant_code d from dims.dim_material_hierarchy where ancestor_code = ? and descendant_level = 'material'", mat)} if mat != "ALL" else None
            names = {r["material_code"]: r["material_name"] for r in q("select material_code, material_name from dims.dim_material")}
            plants = {r["node_code"]: r["node_name"] for r in q("select node_code, node_name from dims.dim_node")}
            mine = [r for r in rows if (loc == "ALL" or r["plant_code"] == loc) and (under is None or r["material_code"] in under)]
            for r in mine:
                r.update(code=r["material_code"], label=names.get(r["material_code"], r["material_code"]), cases=cases.get(r["material_code"], 0), node=False)
            mine.sort(key=lambda r: (r["plant_code"], -(r["cases"] or 0)))
            def node(label: str, rs: list[dict]) -> dict:
                n = sum(r["cases"] or 0 for r in rs)
                f = lambda k: (sum((r[k] or 0) * (r["cases"] or 0) for r in rs) / n) if n else None
                return {"node": True, "label": label, "plant_code": "", **{k: f(k) for k in ("material_cost", "labour_cost", "variable_overhead", "fixed_overhead", "std_cost")},
                        "cases": n, "crew_hours": None}
            shown = ([node(names.get(mat) or mat if mat != "ALL" else "All materials", mine)] if mine else []) + mine[:120]
            by_plant = defaultdict(list)
            for r in rows:
                by_plant[r["plant_code"]].append({**r, "cases": cases.get(r["material_code"], 0)})
            cards = []
            for p, rs in sorted(by_plant.items()):
                if loc != "ALL" and p != loc:
                    continue
                n = sum(r["cases"] for r in rs)
                cards.append({"plant_name": plants.get(p, p), "avg": (sum((r["std_cost"] or 0) * r["cases"] for r in rs) / n) if n else None,
                              "fixed_per_case": rs[0]["fixed_overhead"], "denominator": rs[0]["denominator"], "denominator_version": rs[0]["denominator_version"]})
            ab = q("select * from plan.standard_absorption where version_id = ? order by plant_code, period", version)
            abs_periods = sorted({a["period"] for a in ab})
            absorption: dict = {}
            for a in ab:
                if loc != "ALL" and a["plant_code"] != loc:
                    continue
                x = absorption.setdefault(a["plant_code"], {"plant_name": plants.get(a["plant_code"], a["plant_code"]), "by": {}, "total": 0.0})
                x["by"][a["period"]] = a; x["total"] += a["under_absorbed"] or 0
            where = " · ".join(x for x in [plants.get(loc, "both plants") if loc != "ALL" else "both plants", names.get(mat) or (mat if mat != "ALL" else "")] if x)
            return page(MACRO + PAGE, title="Standard by plant", active="standard", width="none", version=version, period=period, where=where, rows=shown, plants=cards,
                        complete=any(r["complete"] for r in rows), absorption=list(absorption.values()), abs_periods=abs_periods)
        except Busy as e:
            return busy("Standard by plant", e)
