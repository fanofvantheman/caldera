"""Standard by plant (DEC-20261115-04): the cost of a case of each material at its plant, in four components — material,
labour, variable overhead, fixed overhead — each read from the model that already holds it (plan.standard_cost), and
the fixed overhead the plan's cases do not absorb, a line of its own (plan.standard_absorption) — the fixed component set on
the business plan of the year and held on every plan of it, the amount not absorbed split into cost moved and volume moved
(DEC-20261115-06). Read only: the standard
is changed where each component is kept — the input prices, the routes and crews, the schedule, the capital plan.

Registered on the plan's blueprint by `register(...)`, called once from `face/__main__.py`."""
from __future__ import annotations

from collections import defaultdict

from chassis.warehouse import Busy, q

PAGE = """<h1>Standard by plant<small>{{ version }} · {{ period }} · {{ where }} — the cost of a case in four components, each read from the model that holds it</small></h1>
<div class="cards">{% for p in plants %}<div class="card stat"><b>{{ '{:,.2f}'.format(p.avg) if p.avg is not none else '—' }}</b><span>{{ p.plant_name }} · cost of a case, weighted by {{ period }}'s cases · fixed overhead {{ '{:,.2f}'.format(p.fixed_per_case) if p.fixed_per_case is not none else '—' }} a case, {{ 'set on ' ~ p.denominator_version if p.fixed_held else version ~ "'s own" }}</span></div>{% endfor %}</div>
{% if not complete %}<p class="hint">{{ version }} has no overhead on its schedule, so only the material and labour components are read; cost of goods is not valued on it.</p>{% endif %}
<h2>Fixed overhead per case<span class="count">set once on the business plan of each year and held on every plan of that year; material, labour and variable overhead are each plan's own</span></h2>
<table><thead><tr><th>Plant</th><th>Year</th><th class="n">Per case</th><th>Set on</th><th class="n">Fixed overhead</th><th class="n">Cases</th></tr></thead><tbody>
{% for r in rates %}<tr><td>{{ r.plant_name }}</td><td>FY{{ r.fiscal_year }}</td><td class="n"><b>{{ money(r.fixed_overhead) }}</b></td><td class="small">{% if r.fixed_held %}{{ r.denominator_version }} — the business plan for the year{% if r.denominator_version != version %}; {{ version }} reads the difference below{% endif %}{% else %}{{ version }}'s own — no business plan for FY{{ r.fiscal_year }}: its fixed overhead over its schedule's {{ n_sched }} periods ÷ its cases at the plant over the same periods{% endif %}</td><td class="n">{{ '{:,.0f}'.format(r.fixed_pool or 0) }}</td><td class="n">{{ '{:,.0f}'.format(r.denominator or 0) }}</td></tr>{% endfor %}</tbody></table>
<table><thead><tr><th>Material</th><th>Plant</th><th class="n">Material</th><th class="n">Labour</th><th class="n">Variable overhead</th><th class="n">Fixed overhead</th><th class="n">Standard</th><th class="n">Cases {{ period }}</th></tr></thead><tbody>
{% for r in rows %}<tr class="{{ 'grp' if r.node }}"><td>{% if r.node %}<b>{{ r.label }}</b>{% else %}{{ r.label }} <span class="small muted">{{ r.code }}</span>{% endif %}</td><td class="small">{{ r.plant_code or '' }}</td>
<td class="n">{{ money(r.material_cost) }}</td><td class="n">{{ money(r.labour_cost) }}{% if r.crew_hours %}<span class="src">{{ '%.4f'|format(r.crew_hours) }} h × {{ '%.2f'|format(r.loaded_rate) }}</span>{% endif %}</td><td class="n">{{ money(r.variable_overhead) }}</td><td class="n">{{ money(r.fixed_overhead) }}</td><td class="n"><b>{{ money(r.std_cost) }}</b></td><td class="n">{{ '{:,.0f}'.format(r.cases or 0) }}</td></tr>
{% else %}<tr><td colspan="8" class="muted">No material planned here in {{ period }}.</td></tr>{% endfor %}</tbody></table>
<p class="hint">Per case. <b>Material</b>: the bill of materials at the plant × each input's price in force (its price × its index in the assumptions ÷ 100; imported inputs landed) — the energy in the bill is the schedule's, so it is in variable overhead, not here. <b>Labour</b>: the route's crew ÷ its cases an hour × the loaded hourly rate of the plant's production halls in the period (wages and on-costs over paid hours, from the labour model). <b>Variable overhead</b>: the variable cost pools at the plant — process energy, production consumables, variable handling — each its lines' rates per case made. <b>Fixed overhead</b>: the fixed cost pools at the plant over the schedule's planned periods — indirect labour (every position but the crews), maintenance, depreciation and leases, site energy and occupancy, quality — the rate set on the business plan of the period's year — its fixed overhead for the year ÷ its cases at the plant for the year — held on every plan of that year; a year with no business plan takes the plan's own. Which cost centre × account is in which pool is <a href="{{ url_for('plan.cost_pool_map') }}">the map</a>. Above a material, a node's figure is its cost ÷ its cases.</p>
<h2>Fixed overhead not absorbed<span class="count">each plant's fixed overhead in the period against what the standard absorbs on the plan's cases — a line of its own, never in the unit cost</span></h2>
<table><thead><tr><th>Plant</th>{% for p in abs_periods %}<th class="n">{{ p[2:4] }}·{{ p[5:] }}</th>{% endfor %}<th class="n">Total</th></tr></thead><tbody>
{% for a in absorption %}<tr><td>{{ a.plant_name }}<div class="small muted">incurred · absorbed · not absorbed{% if a.split %}<br>of which cost moved · volume moved{% endif %}</div></td>{% for p in abs_periods %}{% set x = a.by.get(p) %}<td class="n small">{% if x %}{{ money(x.fixed_overhead_incurred) }}<br>{{ money(x.absorbed) }}<br><b>{{ money(x.under_absorbed) }}</b>{% if a.split %}<br>{{ money(x.cost_moved) }}<br>{{ money(x.volume_moved) }}{% endif %}{% endif %}</td>{% endfor %}<td class="n"><b>{{ money(a.total) }}</b>{% if a.split %}<br><br><br>{{ money(a.cost) }}<br>{{ money(a.volume) }}{% endif %}</td></tr>{% endfor %}</tbody></table>
<p class="hint">Positive: fixed cost the period's cases do not carry at the standard. Where the rate is the business plan's, the amount is two things: <b>cost moved</b> — this plan's fixed overhead in the period less the business plan's in the same period — and <b>volume moved</b> — the business plan's fixed overhead less what the rate absorbs on this plan's cases (the business plan's own months carry its phasing: a light month absorbs less). They add to the amount not absorbed. A period with no split takes the plan's own rate. The standard holds through the year; the forecast reads the difference here.</p>"""
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
                              "fixed_per_case": rs[0]["fixed_overhead"], "denominator": rs[0]["denominator"], "denominator_version": rs[0]["denominator_version"],
                              "fixed_held": rs[0]["fixed_held"]})
            rates = q("""select distinct s.plant_code, p.fiscal_year, s.fixed_overhead, s.fixed_pool, s.denominator, s.denominator_version, s.fixed_held
                         from plan.standard_cost s join dims.dim_period p using (period) where s.version_id = ? order by 1, 2""", version)
            rates = [{**r, "plant_name": plants.get(r["plant_code"], r["plant_code"])} for r in rates if loc == "ALL" or r["plant_code"] == loc]
            n_sched = q("select count(distinct period) n from plan.opex_schedule where version_id = ?", version)[0]["n"]
            ab = q("select * from plan.standard_absorption where version_id = ? order by plant_code, period", version)
            abs_periods = sorted({a["period"] for a in ab})
            absorption: dict = {}
            for a in ab:
                if loc != "ALL" and a["plant_code"] != loc:
                    continue
                x = absorption.setdefault(a["plant_code"], {"plant_name": plants.get(a["plant_code"], a["plant_code"]), "by": {}, "total": 0.0,
                                                            "split": False, "cost": 0.0, "volume": 0.0})
                x["by"][a["period"]] = a; x["total"] += a["under_absorbed"] or 0
                x["split"] |= bool(a["fixed_held"]); x["cost"] += a["cost_moved"] or 0; x["volume"] += a["volume_moved"] or 0
            where = " · ".join(x for x in [plants.get(loc, "both plants") if loc != "ALL" else "both plants", names.get(mat) or (mat if mat != "ALL" else "")] if x)
            return page(MACRO + PAGE, title="Standard by plant", active="standard", width="none", version=version, period=period, where=where, rows=shown, plants=cards,
                        complete=any(r["complete"] for r in rows), absorption=list(absorption.values()), abs_periods=abs_periods, rates=rates, n_sched=n_sched)
        except Busy as e:
            return busy("Standard by plant", e)
