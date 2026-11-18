"""Storage (DEC-20261117-03), under Integrated business planning → Supply: pallet positions taken against capacity by node
× storage class × period — finished goods from the inventory plan, key raw materials from the material stock — read at the
period's peak, with the working limit below the own tier and the overflow tier at its rate; the first period a class
goes over its own tier and what the overflow costs. Cost does not rise with utilisation: the cost of running out of room is
the overflow tier's rate, a step.

A **stress test** is a reading on this page, not a plan: a shock — sales a percentage below or above plan, or a campaign
intake above plan — from a period for a number of periods, with production held as planned for a number of periods
before it follows demand again; the page recalculates stock and utilisation with the plan's own functions
(`calc.inventory`, `calc.purchases`) and shows the two side by side. Nothing is saved and no Plan is made.

Registered on the plan's blueprint by `register(...)`, called once from `face/__main__.py`."""
from __future__ import annotations

from collections import defaultdict

from chassis.warehouse import Busy, q
from flask import request

from calc import inventory as I
from calc import purchases as P

SHOCKS = {"sales": "sales against plan", "intake": "campaign intake above plan"}

PAGE = """<h1>Storage<small>{{ version }} · pallet positions against capacity by node and class, at each period's peak</small></h1>
<p class="hint">Finished goods are the inventory plan's projected stock at each node; key raw materials the material stock at the plant that holds them. Each is read at the period's peak — a campaign business peaks after intake, and a period end never shows it — over the node's own positions; the line beneath each own tier is the working limit, full enough to hurt; past the own tier, the overflow tier at its rate. A class with nothing declared is shown empty.</p>
<div class="cards">{% for c in cards %}<div class="card stat"><span>{{ c.label }}</span><b>{{ c.show }}</b><div class="small muted">{{ c.says }}</div></div>{% endfor %}</div>
<form class="entry" method="get" action="{{ url_for('plan.storage') }}"><b class="small">Stress test — a reading, nothing saved</b>
<label>shock<select name="shock">{% for k, v in shocks.items() %}<option value="{{ k }}" {{ 'selected' if k == st.shock }}>{{ v }}</option>{% endfor %}</select></label>
<label>by %<input name="pct" type="number" step="any" value="{{ st.pct if st.pct is not none else '' }}" placeholder="−10"></label>
<label>from<select name="from">{% for p in periods %}<option {{ 'selected' if p == st.from }}>{{ p }}</option>{% endfor %}</select></label>
<label>for periods<input name="n" type="number" min="1" value="{{ st.n or 3 }}"></label>
<label>production held for<input name="hold" type="number" min="0" value="{{ st.hold if st.hold is not none else 1 }}"> periods</label>
<div class="actions"><button class="act">Read it</button>{% if st.on %} <a href="{{ url_for('plan.storage') }}">clear</a>{% endif %}</div></form>
{% for n in nodes %}<h2>{{ n.name }}</h2><div style="overflow-x:auto"><table class="stock"><thead><tr><th>Class</th><th></th>{% for p in periods %}<th class="n">{{ p[2:4] }}·{{ p[5:] }}</th>{% endfor %}</tr></thead><tbody>
{% for c in n.classes %}<tr class="first"><td rowspan="{{ 4 if st.on else 3 }}"><b>{{ c.storage_class }}</b><div class="small muted">{% if c.own %}{{ '{:,.0f}'.format(c.own) }} own · limit {{ '{:.0%}'.format(c.limit) if c.limit else '—' }}{% if c.overflow %} · overflow {{ '{:,.0f}'.format(c.overflow) }} at {{ '{:.2f}'.format(c.rate) }}{% endif %}{% else %}no capacity declared{% endif %}</div></td>
<td class="small">pallets at peak</td>{% for p in periods %}{% set x = c.by.get(p) %}<td class="n">{{ '{:,.0f}'.format(x.peak_pallets) if x else '' }}</td>{% endfor %}</tr>
<tr><td class="small">Utilisation</td>{% for p in periods %}{% set x = c.by.get(p) %}<td class="n {{ 'over' if x and x.utilisation and x.utilisation > 1 }}{{ ' near' if x and x.utilisation and c.limit and x.utilisation > c.limit and x.utilisation <= 1 }}">{{ '{:.0%}'.format(x.utilisation) if x and x.utilisation is not none else '' }}</td>{% endfor %}</tr>
{% if st.on %}<tr><td class="small"><b>with the shock</b></td>{% for p in periods %}{% set y = c.shock.get(p) %}<td class="n {{ 'over' if y and y > 1 }}">{{ '{:.0%}'.format(y) if y is not none else '' }}</td>{% endfor %}</tr>{% endif %}
<tr><td class="small muted">overflow cost</td>{% for p in periods %}{% set x = c.by.get(p) %}<td class="n small muted">{{ '{:,.0f}'.format(x.overflow_cost) if x and x.overflow_cost else '' }}</td>{% endfor %}</tr>{% endfor %}
</tbody></table></div>{% endfor %}
<p class="hint">{{ first_over or 'No class goes over its own positions within the plan.' }} Pallets: finished goods at their cases a position (800 kg net); raw materials at their units a position. A stress test of sales holds production as planned for the periods you give, then lets it follow demand again; the raw materials are read as planned. A campaign intake shock buys that much more of each campaign material in its window. A shock worth keeping is a scenario — a Plan of its own, made the way Plans are.</p>
<style>table.stock td{white-space:nowrap}table.stock td.over{font-weight:700;color:var(--bad,#a33)}table.stock td.near{font-weight:600}table.stock tr.first td{border-top:1px solid var(--rule)}</style>"""


def _shocked_demand(inp: dict, pct: float, periods: set[str]) -> dict:
    return {k: v * (1 + pct / 100) if inp["period_of"].get(k[2]) in periods else v for k, v in inp["demand"].items()}


def stress(version: str, shock: str, pct: float, start: str, n: int, hold: int) -> tuple[list[dict], list[dict]]:
    """The inventory plan as it stands and with a sales shock: (base rows, shocked rows) at the period — the plan's own
    function on the plan's inputs, demand moved in the shocked periods, production held at the plan's for `hold` periods
    from the shock's start."""
    fetch = lambda sql: q(sql)
    inp = I.read_inputs(fetch, lambda t: t, version)
    f, base = I.compute(inp, version)
    periods = sorted({inp["period_of"][w] for w in inp["weeks"]})
    window = set(periods[periods.index(start):periods.index(start) + n]) if start in periods else set()
    held = set(periods[periods.index(start):periods.index(start) + hold]) if start in periods else set()
    if shock != "sales" or not window:
        return base, base
    h = {}
    for (m, p), rows in f["production"].items():
        for w, r in zip(inp["weeks"], rows):
            if inp["period_of"][w] in held:
                h[(m, p, w)] = r["receipt"]
    _, shocked = I.compute(inp, version, demand=_shocked_demand(inp, pct, window), hold=h)
    return base, shocked


def _intake(version: str, pct: float, start: str, n: int) -> list[dict]:
    """The material stock with each campaign material's purchases in the window that much higher — typed over, by the
    purchase plan's own function."""
    fetch = lambda sql: q(sql)
    rows = q("select * from plan.material_stock where version_id = ?", version)
    periods = sorted({r["period"] for r in rows})
    window = set(periods[periods.index(start):periods.index(start) + n]) if start in periods else set()
    acts = [a for a in q("select * from plan.purchase_act where version_id = ?", version)]
    for r in rows:
        if r["source"] == "campaign" and r["period"] in window and r["purchase_quantity"]:
            acts.append({"version_id": version, "input_code": r["input_code"], "plant_code": r["plant_code"], "period": r["period"],
                         "quantity": r["purchase_quantity"] * (1 + pct / 100), "price": None, "act_id": "stress"})
    return P.compute_all(fetch, lambda t: t, version, acts=acts)


def register(bp, page, who_fn, ctx_fn, busy, session, roles) -> None:
    from . import reads

    @bp.get("/supply/storage")
    def storage():
        try:
            c = ctx_fn(); version = c.get("version") or reads.default_version()
            load = q("select * from plan.storage_load where version_id = ? order by node_code, storage_class, period", version)
            periods = sorted({r["period"] for r in load})
            names = {r["node_code"]: (r["node_name"], r["node_kind"]) for r in q("select node_code, node_name, node_kind from dims.dim_node")}
            a = request.args
            try:
                pct = float(a.get("pct")) if a.get("pct") not in (None, "") else None
            except ValueError:
                pct = None
            st = {"shock": a.get("shock") if a.get("shock") in SHOCKS else "sales", "pct": pct, "from": a.get("from") if a.get("from") in periods else (periods[0] if periods else None),
                  "n": max(1, int(a.get("n") or 3)) if (a.get("n") or "3").isdigit() else 3, "hold": int(a.get("hold")) if (a.get("hold") or "").isdigit() else 1}
            st["on"] = pct is not None and bool(st["from"])
            shock: dict = defaultdict(dict)
            if st["on"]:
                attrs = {(r["item_kind"], r["item_code"]): r for r in q("select * from dims.ref_storage_attribute")}
                caps = {(x["node_code"], x["storage_class"]): x["own_pallets"] for x in load}
                peak: dict = defaultdict(float)
                if st["shock"] == "sales":
                    _, rows = stress(version, "sales", pct, st["from"], st["n"], st["hold"])
                    for r in rows:
                        at = attrs.get(("finished", r["material_code"]))
                        if at:
                            peak[(r["node_code"], at["storage_class"], r["period"])] += r["peak"] / at["units_per_pallet"]
                    for x in load:                       # raw materials read as planned
                        if x["input_pallets"]:
                            peak[(x["node_code"], x["storage_class"], x["period"])] += x["input_pallets"]
                else:
                    for x in load:
                        if x["finished_pallets"]:
                            peak[(x["node_code"], x["storage_class"], x["period"])] += x["finished_pallets"]
                    for r in _intake(version, pct, st["from"], st["n"]):
                        at = attrs.get(("input", r["input_code"]))
                        if at:
                            peak[(r["plant_code"], at["storage_class"], r["period"])] += (r["opening_quantity"] + r["purchase_quantity"]) / at["units_per_pallet"]
                for (node, cls, p), v in peak.items():
                    if caps.get((node, cls)):
                        shock[(node, cls)][p] = v / caps[(node, cls)]
            nodes = []
            for node in sorted({r["node_code"] for r in load}, key=lambda n: (names.get(n, ("", ""))[1] != "plant", n)):
                classes = []
                for cls in ("ambient", "chilled", "frozen"):
                    rs = [r for r in load if r["node_code"] == node and r["storage_class"] == cls]
                    if not rs:
                        continue
                    classes.append({"storage_class": cls, "own": rs[0]["own_pallets"], "limit": rs[0]["working_limit"], "overflow": rs[0]["overflow_pallets"],
                                    "rate": rs[0]["overflow_rate"], "by": {r["period"]: r for r in rs}, "shock": shock.get((node, cls), {})})
                nodes.append({"name": names.get(node, (node,))[0], "classes": classes})
            over = [r for r in load if r["own_pallets"] and r["peak_pallets"] > r["own_pallets"]]
            first = min(over, key=lambda r: r["period"]) if over else None
            cost = sum(r["overflow_cost"] or 0 for r in load)
            worst = max((r for r in load if r["utilisation"] is not None), key=lambda r: r["utilisation"], default=None)
            cards = [{"label": "Highest utilisation", "show": f"{worst['utilisation']:.0%}" if worst else "—",
                      "says": f"{worst['storage_class']} at {names.get(worst['node_code'], (worst['node_code'],))[0]} in {worst['period']}" if worst else ""},
                     {"label": "Overflow over the plan", "show": f"${cost:,.0f}", "says": "pallets over the own tier × the overflow rate × the weeks"},
                     {"label": "Periods over the own tier", "show": str(len(over)), "says": "node × class × period"}]
            return page(PAGE, title="Storage", active="storage", width="none", version=version, nodes=nodes, periods=periods, shocks=SHOCKS, st=st, cards=cards,
                        first_over=(f"The first period a class goes over its own positions: {first['storage_class']} at {names.get(first['node_code'], (first['node_code'],))[0]} in {first['period']}, "
                                    f"{first['over_own']:,.0f} pallets over at {first['overflow_rate'] or 0:.2f} a pallet a week." if first else None))
        except Busy as e:
            return busy("Storage", e)
