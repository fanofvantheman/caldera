"""The strategic plan's first page (DEC-20261113-01): volume and net revenue by category × channel × year over the plan's
five years — the latest view rolled up where it reaches, grown by category beyond — and the capacities the plan declares,
by year, each with its tiers, the load against it and the first break. Only what Caldera can compute is shown as a
number; a capacity with no data behind it says what is loaded and what is missing.

Read here; nothing is typed yet — the growth rates are a register by category and year, and typing them on this page is
the next step. Registered on the plan's blueprint by `register(...)`, called from `face/__main__.py`."""
from __future__ import annotations

from chassis.warehouse import Busy, q

PAGE = """<h1>Five-year plan<small>{{ sp.plan_name }} · {{ sp.plan_id }} · the latest view {{ sp.latest_view }} rolled up where it reaches, grown by category beyond; the few capacities that would force a decision, by year</small></h1>
<p class="hint">Year one is the business plan's year, read here as the latest view reads it — its closed periods as shipped. A year counts as inside when its closed periods and the latest view's periods make all of it — {{ inside|join(', ') }}; {{ beyond|join(' and ') }} {{ 'is' if beyond|length == 1 else 'are' }} grown from FY{{ last_inside }} by the rates below, with the channel mix and the net price per case held. Nothing here is re-entered: change the latest view and this page follows on the next run.</p>
<h2>Volume and net revenue<span class="count">category × channel × year · cases and net sales</span></h2>
<div class="finwrap"><table class="sp"><thead><tr><th>Category</th><th>Channel</th>{% for y in years %}<th class="n {{ 'beyond' if y.beyond }}">FY{{ y.fy }}<div class="small muted">{{ y.says }}</div></th>{% endfor %}</tr></thead><tbody>
{% for c in cats %}{% for r in c.rows %}<tr class="{{ 'first' if loop.first }}">{% if loop.first %}<td rowspan="{{ c.rows|length + 1 }}" class="node"><b>{{ c.name }}</b></td>{% endif %}<td class="small">{{ r.channel }}</td>
{% for y in years %}{% set x = r.by.get(y.fy) %}<td class="n {{ 'beyond' if y.beyond }}">{% if x %}{{ x.cases|n }}<span class="src">{{ x.net_sales|aud }}</span>{% endif %}</td>{% endfor %}</tr>{% endfor %}
<tr class="total"><td class="small">{{ c.name }}</td>{% for y in years %}{% set x = c.tot.get(y.fy) %}<td class="n {{ 'beyond' if y.beyond }}">{% if x %}{{ x.cases|n }}<span class="src">{{ x.net_sales|aud }}</span>{% endif %}</td>{% endfor %}</tr>{% endfor %}
<tr class="total"><td colspan="2"><b>Caldera</b></td>{% for y in years %}{% set x = total.get(y.fy) %}<td class="n {{ 'beyond' if y.beyond }}"><b>{{ x.cases|n }}</b><span class="src">{{ x.net_sales|aud }}</span></td>{% endfor %}</tr></tbody></table></div>
<h2>Growth beyond the latest view<span class="count">by category and year — Finance's far-horizon rates</span></h2>
<table><thead><tr><th>Category</th>{% for y in beyond_years %}<th class="n">FY{{ y }}</th>{% endfor %}</tr></thead><tbody>
{% for g in growth %}<tr><td>{{ g.name }}</td>{% for y in beyond_years %}<td class="n">{{ g.by.get(y)|pct1s }}</td>{% endfor %}</tr>{% endfor %}</tbody></table>
<p class="hint">The rates are a register, kept by Finance as part of the modelling; typing them on this page is not built yet.</p>
<h2>The capacities<span class="count">the five the plan declares — the rest are not modelled</span></h2>
{% for k in kinds %}<h3>{{ k.label }} <span class="small muted">· {{ k.unit }} · tiers: {{ k.tiers }}</span></h3>
{% if k.computed == 'computed' %}<table class="sp"><thead><tr><th>{{ 'Plant' if k.kind == 'production' else '' }}</th><th></th>{% for y in years %}<th class="n {{ 'beyond' if y.beyond }}">FY{{ y.fy }}</th>{% endfor %}<th>First break</th></tr></thead><tbody>
{% for n in k.nodes %}<tr class="first"><td rowspan="4" class="node"><b>{{ n.name }}</b><div class="small muted">as registered: {{ n.tier0_is }}</div></td><td class="small muted">tier 0 · as registered</td>{% for y in years %}{% set x = n.by.get(y.fy) %}<td class="n {{ 'beyond' if y.beyond }}"{% if x and x.availability_held %} title="past the machine register: its last year held"{% endif %}>{{ x.available_tier0|n if x }}{% if x and x.availability_held %}*{% endif %}</td>{% endfor %}
<td rowspan="4" class="small">{% if n.first_break %}<b>FY{{ n.first_break }}</b> — {{ n.breaks_says }}{% else %}none by FY{{ years[-1].fy }} — the highest year is FY{{ n.peak_fy }} at {{ n.peak|pct1 }} of tier 0{% endif %}</td></tr>
<tr><td class="small muted">tier 1 · one more shift</td>{% for y in years %}{% set x = n.by.get(y.fy) %}<td class="n {{ 'beyond' if y.beyond }}">{{ x.available_tier1|n if x }}</td>{% endfor %}</tr>
<tr><td class="small muted">load</td>{% for y in years %}{% set x = n.by.get(y.fy) %}<td class="n {{ 'beyond' if y.beyond }}" title="{{ x.load_from if x }}">{{ x.load|n if x }}</td>{% endfor %}</tr>
<tr><td class="small muted">load ÷ tier 0</td>{% for y in years %}{% set x = n.by.get(y.fy) %}<td class="n {{ 'beyond' if y.beyond }} {{ 'over' if x and x.util and x.util > 1 }}">{{ x.util|pct1 if x }}</td>{% endfor %}</tr>{% endfor %}</tbody></table>
<p class="hint">{{ k.says }} A year's hours spread the fruit campaign over the year: a line that is full in the campaign weeks can read well under its tier here — the weekly reading belongs to the supply plan's capacity page, not yet built. * past the register, its last year held.</p>
{% elif k.computed == 'load only' %}<table class="sp"><thead><tr><th></th>{% for y in years %}<th class="n {{ 'beyond' if y.beyond }}">FY{{ y.fy }}</th>{% endfor %}</tr></thead><tbody>
<tr><td class="small muted">available</td>{% for y in years %}<td class="n muted">—</td>{% endfor %}</tr>
{% for n in k.nodes %}<tr><td class="small muted">load · receivables at terms</td>{% for y in years %}{% set x = n.by.get(y.fy) %}<td class="n {{ 'beyond' if y.beyond }}" title="{{ x.load_from if x }}">{{ x.load|aud if x }}</td>{% endfor %}</tr>{% endfor %}</tbody></table>
<p class="hint">{{ k.says }}</p>
{% else %}<p class="hint notbuilt"><b>No data behind this capacity.</b> {{ k.says }} Nothing is shown rather than a number nobody could check.</p>{% endif %}{% endfor %}
<style>.finwrap{overflow-x:auto}table.sp td.n,table.sp th.n{white-space:nowrap;vertical-align:top}table.sp .src{display:block;font-size:.72rem;color:var(--muted)}table.sp td.node{vertical-align:top;min-width:10rem}
table.sp tr.first td{border-top:1px solid var(--rule)}table.sp .beyond{background:color-mix(in srgb,var(--muted) 6%,transparent)}table.sp td.over{font-weight:700}.notbuilt{border-left:2px solid var(--rule);padding-left:.6rem}</style>"""

PLANTS = {"ECH": "Echuca plant", "LOX": "Loxton plant"}


def register(bp, page, busy) -> None:

    @bp.get("/strategic")
    def strategic():
        try:
            sp = (q("select * from plan.strategic_plan limit 1") or [{}])[0]
            vol = q("select v.*, m.category_name from plan.strategic_volume v join (select distinct category_code, category_name from dims.dim_material) m using (category_code) order by m.category_name, v.channel, v.fiscal_year")
            fys = sorted({r["fiscal_year"] for r in vol})
            grown = {r["fiscal_year"] for r in vol if r["source"].startswith("grown")}
            last_inside = max((y for y in fys if y not in grown), default=None)
            years = [{"fy": y, "beyond": y in grown, "says": "grown" if y in grown else ("shipped + latest view" if any(r["fiscal_year"] == y and r["source"].startswith("shipped") for r in vol) else "latest view")} for y in fys]
            cats: dict = {}; total: dict = {}
            for r in vol:
                c = cats.setdefault(r["category_code"], {"name": r["category_name"], "rows": {}, "tot": {}})
                c["rows"].setdefault(r["channel"], {"channel": r["channel"], "by": {}})["by"][r["fiscal_year"]] = r
                for d in (c["tot"].setdefault(r["fiscal_year"], {"cases": 0.0, "net_sales": 0.0}), total.setdefault(r["fiscal_year"], {"cases": 0.0, "net_sales": 0.0})):
                    d["cases"] += r["cases"] or 0; d["net_sales"] += r["net_sales"] or 0
            cats_l = [{**c, "rows": list(c["rows"].values())} for c in cats.values()]
            growth: dict = {}
            names = {r["category_code"]: r["category_name"] for r in vol}
            for g in q("select category_code, fiscal_year, growth_pct from plan.strategic_growth order by category_code, fiscal_year"):
                growth.setdefault(g["category_code"], {"name": names.get(g["category_code"], g["category_code"]), "by": {}})["by"][int(g["fiscal_year"])] = g["growth_pct"]
            cap = q("select * from plan.strategic_capacity order by kind, node, fiscal_year")
            kinds = []
            for k in q("select * from plan.ref_strategic_capacity order by ord"):
                nodes: dict = {}
                for r in (x for x in cap if x["kind"] == k["kind"]):
                    n = nodes.setdefault(r["node"], {"name": PLANTS.get(r["node"], r["node"]), "tier0_is": r["tier0_is"], "by": {}})
                    util = r["load"] / r["available_tier0"] if r["load"] is not None and r["available_tier0"] else None
                    n["by"][r["fiscal_year"]] = {**r, "util": util}
                for n in nodes.values():
                    over = [(y, x) for y, x in sorted(n["by"].items()) if x["util"] and x["util"] > 1]
                    n["first_break"] = over[0][0] if over else None
                    if over:
                        y, x = over[0]
                        n["breaks_says"] = ("tier 1 (one more shift) removes it" if x["available_tier1"] and x["load"] <= x["available_tier1"]
                                            else "beyond tier 1 — a further line, not declared") + "; no lead time is declared, so no year to commit it by"
                    util = [(y, x["util"]) for y, x in n["by"].items() if x["util"] is not None]
                    n["peak_fy"], n["peak"] = max(util, key=lambda t: t[1]) if util else (None, None)
                kinds.append({**k, "nodes": list(nodes.values())})
            return page(PAGE, title="Five-year plan", active="strategic", width="none", sp=sp, years=years, cats=cats_l, total=total,
                        inside=[f"FY{y}" for y in fys if y not in grown], beyond=[f"FY{y}" for y in sorted(grown)], last_inside=last_inside,
                        growth=list(growth.values()), beyond_years=sorted(grown), kinds=kinds)
        except Busy as e:
            return busy("Five-year plan", e)
