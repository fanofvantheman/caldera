"""The cost side's pages: the legal entities and their ledgers, the plan's cost centres over them, the actuals read through
the mapping, and the ledgers' queue (door GL on the one resolution model).

Registered on the plan's blueprint by `register(bp, page, who, ctx, busy)`, called once from `face/__main__.py`; the
routes' endpoints are `plan.<name>` like every other page. Nothing here writes except the queue's decisions, which go
through the shared door route (`plan.door_decide`)."""
from __future__ import annotations

from chassis import door
from chassis.warehouse import Busy, q
from flask import request, url_for

from . import doors

ENTITY_NOTE = ("Two legal entities, each on its own ledger with its own cost centres; the plan reads both at its own cost centres. "
               "Intercompany charges between them are left out — each entity's costs are its own spend with third parties.")


def rolling_year() -> list[str]:
    """The last twelve closed periods — the window a rate is calculated over and actuals are compared on."""
    return [r["period"] for r in q("select period from dims.dim_period where period_state = 'CLOSED' order by period desc limit 12")][::-1]


def entities() -> list[dict]:
    return q("select * from dims.dim_entity order by entity_code")


def planning_cost_centres() -> list[dict]:
    """The plan's cost centres in tree order — function, then its cost centres — with their kind."""
    rows = q("""select c.cost_centre_code code, c.cost_centre_name "name", c.parent_code parent, c.kind, c.provisional,
                       coalesce(p.cost_centre_name, '') parent_name
                from plan.planning_cost_centre c left join plan.planning_cost_centre p on p.cost_centre_code = c.parent_code
                order by c.cost_centre_code""")
    by_parent: dict = {}
    for r in rows:
        by_parent.setdefault(r["parent"], []).append(r)
    out = []
    def walk(parent, depth):
        for r in sorted(by_parent.get(parent, []), key=lambda r: (r["kind"] == "function", r["code"]) if depth > 1 else (0, r["code"])):
            out.append({**r, "depth": depth})
            walk(r["code"], depth + 1)
    walk(None, 0)
    return out


# ---- pages ----
TABS_NOTE = """<p class="hint">{{ entity_note }}</p>"""

CENTRES = """<h1>Cost centres<small>the plan's cost centres — one set over each entity's own — with the ledger cost centres mapped to each, and the last twelve closed periods' actuals ({{ year[0] }}–{{ year[-1] }})</small></h1>
""" + TABS_NOTE + """
{% if waiting %}<p class="hint"><b>{{ waiting }}</b> ledger cost centre{{ '' if waiting == 1 else 's' }} not mapped to any of ours — <a href="{{ url_for('plan.cost_mapping') }}">the mapping review</a>.</p>{% endif %}
<table class="cc"><thead><tr><th>Plan's cost centre</th><th>Kind</th>{% for e in entities %}<th>{{ e.entity_name }} — ledger cost centres</th><th class="n">{{ e.entity_code }} actuals</th>{% endfor %}<th class="n">Both</th></tr></thead><tbody>
{% for c in centres %}<tr class="{{ 'fn' if c.kind in ('company', 'function') else '' }}"><td style="padding-left:{{ 0.4 + c.depth * 1.1 }}rem">{% if c.kind in ('company', 'function') %}<b>{{ c.name }}</b>{% else %}{{ c.name }} <span class="small muted">{{ c.code }}</span>{% if c.provisional %} <span class="state">provisional</span>{% endif %}{% endif %}</td>
<td class="small">{{ c.kind if c.kind not in ('company', 'function') else '' }}</td>
{% for e in entities %}{% set m = mapped.get((c.code, e.entity_code), []) %}<td class="small">{% for l in m %}<code>{{ l.ledger_cost_centre }}</code> {{ l.ledger_name }}{% if not loop.last %}<br>{% endif %}{% endfor %}</td>
<td class="n">{{ amounts.get((c.code, e.entity_code))|aud }}</td>{% endfor %}<td class="n">{{ amounts.get((c.code, None))|aud }}</td></tr>{% endfor %}
<tr class="total"><td>Total in the plan</td><td></td>{% for e in entities %}<td></td><td class="n">{{ totals.get(e.entity_code)|aud }}</td>{% endfor %}<td class="n">{{ totals.get(None)|aud }}</td></tr>
{% for u in outside %}<tr class="off"><td colspan="2"><code>{{ u.ledger_cost_centre }}</code> {{ u.ledger_name }} <span class="state">{{ 'not mapped' if u.state == 'unmapped' else 'left out' }}</span></td>
{% for e in entities %}<td class="small">{{ e.entity_name if e.entity_code == u.entity_code else '' }}</td><td class="n">{{ u.amount|aud if e.entity_code == u.entity_code else '' }}</td>{% endfor %}<td class="n muted">outside</td></tr>{% endfor %}
</tbody></table>
<p class="hint">Many of an entity's cost centres may map to one of ours, never one to many: Riverbend's two sales centres (by state) are one, Sales and key accounts; its one production centre is Loxton production, because its ledger does not split the fruit and cup halls and the plan is no finer than the coarsest ledger can supply. The plan is entered, read and compared at its own cost centres; the ledger codes are shown beneath and never planned on.</p>
<style>table.cc tr.fn td{background:var(--soft)}table.cc td{vertical-align:top}</style>"""

ENTITIES = """<h1>Entities and ledgers<small>each legal entity, the ledger it keeps, and its own cost centres with where each lands in the plan</small></h1>
""" + TABS_NOTE + """
<div class="cards">{% for e in entities %}<div class="card"><b>{{ e.entity_name }}</b> <span class="small muted">{{ e.entity_code }}</span>
<div class="small">{{ e.ledger }} · in the plan from {{ e.joined_period }} ({{ e.joined_on }}) · payroll in {{ e.state }}</div><div class="small muted">{{ e.note }}</div>
<div class="small">{{ e.n }} ledger cost centres · {{ e.year|aud }} over the last twelve closed periods</div></div>{% endfor %}</div>
{% for e in entities %}<h2>{{ e.entity_name }} — the {{ e.ledger }}<span class="count">its cost centres as the ledger has them</span></h2>
<table><thead><tr><th>Ledger cost centre</th><th>Plan's cost centre</th><th>From</th><th>How</th><th class="n">Last twelve closed periods</th></tr></thead><tbody>
{% for l in ledgers if l.entity_code == e.entity_code %}<tr class="{{ '' if l.cost_centre_code else 'off' }}"><td><code>{{ l.ledger_cost_centre }}</code> {{ l.ledger_name }}</td>
<td>{% if l.cost_centre_code %}{{ l.cost_centre_name }} <span class="small muted">{{ l.cost_centre_code }}</span>{% elif l.how %}<span class="state">left out</span> <span class="small">{{ l.note or '' }}</span>{% else %}<span class="state">not mapped</span> <a class="small" href="{{ url_for('plan.cost_mapping') }}">decide</a>{% endif %}</td>
<td class="small">{{ l.valid_from or '' }}</td><td class="small">{{ {'loaded': 'as loaded', 'map_to': 'mapped on the review', 'open_new': 'opened on the review', 'leave_out': 'left out on the review'}.get(l.how, '') }}{% if l.mapped_by %} · {{ l.mapped_by }}{% endif %}</td>
<td class="n">{{ l.year|aud }}</td></tr>{% endfor %}</tbody></table>{% endfor %}
<p class="hint">One chart of accounts for both: Riverbend moved onto Caldera's accounts when it was bought and kept its own cost centres. The mapping is effective-dated, so a ledger that re-cuts its cost centres is read through the mapping in force at each period's start.</p>"""

ACTUALS = """<h1>Actuals<small>FY{{ fy }} · the ledgers' actuals by {{ "each ledger's own cost centre" if at == 'ledger' else "the plan's cost centre" }} × account · closed periods · {{ entity_label }}</small></h1>
<form class="toolbar" method="get">{{ context_fields() }}<label>year<select name="year" onchange="this.form.submit()">{% for y in years %}<option value="{{ y }}" {{ 'selected' if y == fy }}>FY{{ y }}</option>{% endfor %}</select></label><label>entity<select name="entity" onchange="this.form.submit()"><option value="">both</option>{% for e in entities %}<option value="{{ e.entity_code }}" {{ 'selected' if e.entity_code == entity }}>{{ e.entity_name }}</option>{% endfor %}</select></label>
<label>read at<select name="at" onchange="this.form.submit()"><option value="">the plan's cost centres</option><option value="ledger" {{ 'selected' if at == 'ledger' }}>each ledger's own</option></select></label></form>
""" + TABS_NOTE + """
{% if not periods %}<p class="muted">No closed period in FY{{ fy }}.</p>{% else %}
<div class="wide"><table class="plan"><thead><tr><th class="sticky">{{ 'Ledger cost centre' if at == 'ledger' else 'Cost centre' }} · account</th>{% if at != 'ledger' %}<th>Entity · ledger</th>{% else %}<th>Plan's cost centre</th>{% endif %}
{% for p in periods %}<th class="n">{{ p[2:4] }}·{{ p[5:] }}</th>{% endfor %}<th class="n">FY{{ fy }}{{ " to date" if periods|length < 12 }}</th></tr></thead><tbody>
{% for g in groups %}<tr class="l0"><td class="sticky"><b>{{ g.label }}</b></td><td class="small">{{ g.beneath }}</td>{% for p in periods %}<td class="n"><b>{{ g.by.get(p)|k }}</b></td>{% endfor %}<td class="n"><b>{{ g.total|k }}</b></td></tr>
{% for r in g.rows %}<tr><td class="sticky" style="padding-left:1.4rem">{{ r.account_code }} {{ r.account_name }}</td><td></td>{% for p in periods %}<td class="n">{{ r.by.get(p)|k }}</td>{% endfor %}<td class="n">{{ r.total|k }}</td></tr>{% endfor %}{% endfor %}
<tr class="total"><td class="sticky">Total in the plan</td><td></td>{% for p in periods %}<td class="n">{{ total.get(p)|k }}</td>{% endfor %}<td class="n">{{ total_all|k }}</td></tr>
{% for g in outside %}<tr class="off"><td class="sticky"><code>{{ g.code }}</code> {{ g.label }} <span class="state">{{ g.state }}</span></td><td class="small">{{ g.beneath }}</td>{% for p in periods %}<td class="n">{{ g.by.get(p)|k }}</td>{% endfor %}<td class="n">{{ g.total|k }}</td></tr>{% endfor %}
</tbody></table></div>{% endif %}
<p class="hint">Each actual is read through the mapping in force at its period's start. A ledger cost centre no mapping carries is shown apart, outside the plan's total, until it is decided on the mapping review — never dropped.</p>
<style>.wide{overflow-x:auto}table.plan{font-size:.82rem;width:max-content;min-width:100%}table.plan .sticky{position:sticky;left:0;background:var(--panel)}table.plan tr.l0 td{background:var(--soft)}</style>"""

MAPPING = """<h1>Mapping review<small>a ledger cost centre with no planning cost centre — map it to one of ours, open a planning cost centre for it, or leave it out with a reason; the decision stands for every later load</small></h1>
""" + TABS_NOTE + """
{% if pending %}<p class="hint">{{ pending }} act{{ '' if pending == 1 else 's' }} placed since the last run — this list shows {{ 'it' if pending == 1 else 'them' }} after the run.</p>{% endif %}
<h2 id="queue">Waiting for a decision<span class="count">{{ door_items|length }} ledger cost centre{{ '' if door_items|length == 1 else 's' }}</span></h2>
""" + door.QUEUE + """
<h2 id="force">Decided<span class="count">the latest decision per ledger cost centre</span></h2>
""" + door.DECIDED + """
{% if last %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else ('!' if c.flag else '✕') }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}"""


def register(bp, page, who_fn, ctx_fn, busy, session) -> None:
    """The cost pages on the plan's blueprint. `page(body, **ctx)` draws in the shell; `who_fn()` the person;
    `ctx_fn()` the context; `busy(title, e)` the page a run in progress gets."""

    @bp.get("/costs/centres")
    def cost_centres():
        try:
            year = rolling_year()
            ents = entities()
            amounts, totals = {}, {}
            for r in q(f"""select cost_centre_code cc, entity_code e, sum(amount) a from plan.cost_actual
                           where state = 'mapped' and period in ({','.join('?' * len(year))}) group by all""", *year):
                amounts[(r["cc"], r["e"])] = r["a"]
                amounts[(r["cc"], None)] = amounts.get((r["cc"], None), 0) + r["a"]
                totals[r["e"]] = totals.get(r["e"], 0) + r["a"]
                totals[None] = totals.get(None, 0) + r["a"]
            centres = planning_cost_centres()
            # roll the leaves up to their functions and the company
            parent = {c["code"]: c["parent"] for c in centres}
            for c in centres:
                if c["kind"] in ("company", "function"):
                    continue
                for e in [x["entity_code"] for x in ents] + [None]:
                    a = amounts.get((c["code"], e))
                    p = parent.get(c["code"])
                    while a and p:
                        amounts[(p, e)] = amounts.get((p, e), 0) + a
                        p = parent.get(p)
            mapped: dict = {}
            for m in q("""select m.cost_centre_code, m.entity_code, m.ledger_cost_centre, l.ledger_name from plan.cost_centre_map m
                          join dims.dim_ledger_cost_centre l using (entity_code, ledger_cost_centre) where m.cost_centre_code is not null
                          order by m.ledger_cost_centre"""):
                mapped.setdefault((m["cost_centre_code"], m["entity_code"]), []).append(m)
            outside = q(f"""select entity_code, ledger_cost_centre, any_value(ledger_name) ledger_name, state, sum(amount) amount from plan.cost_actual
                            where state <> 'mapped' and period in ({','.join('?' * len(year))}) group by all order by 1, 2""", *year)
            waiting = q("select count(*) n from plan.worklist_cost_centre_unmapped")[0]["n"]
            return page(CENTRES, title="Cost centres", active="cc_tree", entities=ents, centres=centres, mapped=mapped, amounts=amounts,
                        totals=totals, outside=outside, year=year, waiting=waiting, entity_note=ENTITY_NOTE)
        except Busy as e:
            return busy("Cost centres", e)

    @bp.get("/costs/entities")
    def cost_entities():
        try:
            year = rolling_year()
            inn = ",".join("?" * len(year))
            ledgers = q(f"""select l.entity_code, l.ledger_cost_centre, l.ledger_name, m.cost_centre_code, c.cost_centre_name, m.valid_from, m.how, m.mapped_by, m.note,
                                   (select sum(a.amount) from plan.cost_actual a where a.entity_code = l.entity_code and a.ledger_cost_centre = l.ledger_cost_centre
                                    and a.period in ({inn})) as year
                            from dims.dim_ledger_cost_centre l
                            left join plan.cost_centre_map m on m.entity_code = l.entity_code and m.ledger_cost_centre = l.ledger_cost_centre
                            left join plan.planning_cost_centre c on c.cost_centre_code = m.cost_centre_code
                            order by l.entity_code, l.ledger_cost_centre""", *year)
            ents = [{**e, "n": sum(1 for l in ledgers if l["entity_code"] == e["entity_code"]),
                     "year": sum(l["year"] or 0 for l in ledgers if l["entity_code"] == e["entity_code"])} for e in entities()]
            return page(ENTITIES, title="Entities and ledgers", active="cc_entities", entities=ents, ledgers=ledgers, entity_note=ENTITY_NOTE)
        except Busy as e:
            return busy("Entities and ledgers", e)

    @bp.get("/costs/actuals")
    def cost_actuals():
        try:
            years = [int(r["fiscal_year"]) for r in q("select distinct fiscal_year from plan.cost_actual order by 1 desc")]
            fy = int(request.args.get("year") or (years[0] if years else 0))
            entity = request.args.get("entity") or ""
            at = "ledger" if request.args.get("at") == "ledger" else ""
            ents = entities()
            periods = [r["period"] for r in q("select period from dims.dim_period where fiscal_year = ? and period_state = 'CLOSED' order by period", fy)]
            rows = q("""select * from plan.cost_actual where fiscal_year = ? and (? = '' or entity_code = ?) order by entity_code, ledger_cost_centre, account_code""",
                     fy, entity, entity) if periods else []
            groups: dict = {}
            outside: dict = {}
            total: dict = {}
            for r in rows:
                if r["state"] != "mapped":
                    g = outside.setdefault((r["entity_code"], r["ledger_cost_centre"]), {"code": r["ledger_cost_centre"], "label": r["ledger_name"],
                                           "state": "not mapped" if r["state"] == "unmapped" else "left out", "beneath": r["entity_code"], "by": {}, "total": 0})
                    g["by"][r["period"]] = g["by"].get(r["period"], 0) + r["amount"]; g["total"] += r["amount"]
                    continue
                if at == "ledger":
                    key, label, beneath = (r["entity_code"], r["ledger_cost_centre"]), f"{r['ledger_cost_centre']} {r['ledger_name']}", f"{r['cost_centre_name']} · {r['entity_code']}"
                else:
                    key, label, beneath = r["cost_centre_code"], r["cost_centre_name"], None
                g = groups.setdefault(key, {"label": label, "beneath": beneath, "ledgers": set(), "by": {}, "total": 0, "rows": {}})
                g["ledgers"].add(f"{r['entity_code']} {r['ledger_cost_centre']}")
                g["by"][r["period"]] = g["by"].get(r["period"], 0) + r["amount"]; g["total"] += r["amount"]
                a = g["rows"].setdefault(r["account_code"], {"account_code": r["account_code"], "account_name": r["account_name"], "by": {}, "total": 0})
                a["by"][r["period"]] = a["by"].get(r["period"], 0) + r["amount"]; a["total"] += r["amount"]
                total[r["period"]] = total.get(r["period"], 0) + r["amount"]
            out = []
            order = {c_["code"]: i for i, c_ in enumerate(planning_cost_centres())}
            for k in sorted(groups, key=lambda k: (order.get(k, 999), str(k)) if at != "ledger" else (k[0] != "CF", k[1])):
                g = groups[k]
                out.append({**g, "beneath": g["beneath"] or " · ".join(sorted(g["ledgers"])), "rows": [g["rows"][a] for a in sorted(g["rows"])]})
            label = next((e["entity_name"] for e in ents if e["entity_code"] == entity), "both entities")
            return page(ACTUALS, title="Actuals", active="cc_actuals", width="100%", fy=fy, periods=periods, groups=out, outside=list(outside.values()),
                        total=total, total_all=sum(total.values()), years=years, entities=ents, entity=entity, entity_label=label, at=at, entity_note=ENTITY_NOTE)
        except Busy as e:
            return busy("Actuals", e)

    @bp.get("/costs/mapping")
    def cost_mapping():
        try:
            who = who_fn()
            return page(MAPPING, title="Mapping review · cost centres", active="cc_mapping", width="none",
                        **doors.page_context("GL", who), door_decided=doors.decided("GL"), pending=len(doors.ACTS.pending()),
                        last=session.last, entity_note=ENTITY_NOTE)
        except Busy as e:
            return busy("Mapping review", e)
