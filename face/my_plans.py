"""My plans (DEC-20261121-01 points 1–3, 6–12): the material planner's purchasing plans — what are my plans, construct a
new one, push one into an IBP plan — on one screen. What a plan reads and the sending of it are here; the plan itself,
its material balance, opens from it (face/purchases.py). No IBP plan is chosen above the page: one appears only as where a
copy was taken from and where a snapshot is sent.

Registered on the plan's blueprint by `register(...)`, called once from `face/__main__.py`."""
from __future__ import annotations

from chassis import receipts
from chassis.warehouse import Busy, q
from flask import redirect, request, url_for

from . import overrides, purchasing_plan as W
from .purchases import VERB, per, when
from .words import said

PAGE = """<h1>My plans<small>the purchasing plans you keep · what each reads · the snapshots you have sent to an IBP plan</small></h1>
<div class="cards">
<div class="card stat"><span>Plans</span><b>{{ rows|length }}</b><div class="small muted">yours</div></div>
<div class="card stat"><span>Changed since sent</span><b>{{ n_changed }}</b><div class="small muted">receipts, in {{ n_changed_plans }} plan{{ '' if n_changed_plans == 1 else 's' }}</div></div>
<div class="card stat"><span>Standing</span><b>{{ n_standing }}</b><div class="small muted">IBP plan{{ '' if n_standing == 1 else 's' }} holding a copy of one of your plans</div></div>
</div>

<h2>Plans<span class="count">yours</span>{% if may %}<span class="right"><a class="button primary" href="#new">New plan</a></span>{% endif %}</h2>
{% if rows %}<table class="plans"><thead><tr><th>Plan</th><th>Actuals to</th><th>Consumption copied from</th><th>Received</th><th class="n">Typed</th><th class="n">Changed</th><th>Sent to</th><th></th></tr></thead><tbody>
{% for r in rows %}<tr class="{{ 'chosen' if chosen and r.p.id == chosen.id }}"><td><b><a href="{{ url_for('plan.purchasing_plans', purchasing=r.p.id) }}">{{ r.p.name }}</a></b><div class="small muted">made {{ when(r.p.made_at) }}{% if r.p.made_from %}, from “{{ r.p.made_from }}”{% else %}, nothing copied{% endif %}</div></td>
<td>{{ per(r.p.actuals_to) }}<div class="small muted">through {{ per(r.p.through) }}</div></td>
<td>{% if r.sources|length == 1 %}{{ r.sources[0]|planfull }}<div class="small muted">copy of {{ when(r.taken[0]) }}</div>{% else %}{{ r.p.plants|length }} plants, {{ r.sources|length }} source{{ '' if r.sources|length == 1 else 's' }}<div class="small muted">{% for pl, c in r.reads.consumption.items() %}{{ plants.get(pl, pl) }}: {% if c %}{{ c.source|planfull }}, copy of {{ when(c.taken_at) }}{% else %}<b>not yet received</b>{% endif %}{{ ' · ' if not loop.last }}{% endfor %}</div>{% endif %}</td>
<td>{{ r.received }} of {{ r.inputs }}{% for pl in r.missing %}<div class="small"><b>○ {{ plants.get(pl, pl) }}</b></div>{% endfor %}</td>
<td class="n">{{ r.typed }}</td><td class="n">{% if r.changed %}<b>{{ r.changed }}</b>{% else %}0{% endif %}</td>
<td>{% if r.sent %}{{ r.sent.version|planfull }}<div class="small muted">{{ when(r.sent.at) }} · {% if r.standing_here %}{{ r.sent.receipts|length }} receipt{{ '' if r.sent.receipts|length == 1 else 's' }}{% if r.closed %} · closed with it — no longer replaced{% endif %}{% else %}since replaced by {{ r.replaced_by }}{% endif %}</div>{% else %}<span class="muted">never sent</span>{% endif %}</td>
<td class="acts"><a class="button act" href="{{ url_for('plan.material_purchases', purchasing=r.p.id) }}">Open</a> {% if may %}<a class="button act" href="{{ url_for('plan.purchasing_plans', purchasing=r.p.id) }}#send">Send</a> <a class="button act" href="{{ url_for('plan.purchasing_plans', purchasing=chosen.id if chosen else None, start=r.p.id) }}#new">Copy</a>{% endif %}</td></tr>{% endfor %}
</tbody></table>{% else %}<p class="lede">You keep no purchasing plan yet. Make one below; it opens on its material balance.</p>{% endif %}
<p class="hint">Typed is the receipts typed in the plan; changed is how many are new or different since its last snapshot. A plan is always yours. Sending puts a snapshot of it into the IBP plan — the receipts you typed, as they stand at that moment — and the plan stays here to go on working. The IBP plan works out the rest again. A receipt is a quantity and a price together; one without the other is not taken.</p>

{% if chosen %}<h2 id="chosen">{{ chosen.name }}<span class="count">the plan chosen above · <a href="{{ url_for('plan.material_purchases', purchasing=chosen.id) }}">open its material balance</a></span></h2>
<div class="card status"><h3>Received <span class="small muted" style="font-weight:400">— {{ cur.received }} of {{ cur.inputs }}</span></h3>
<table><tbody>
{% for pl, c in cur.reads.consumption.items() %}<tr><td class="{{ 'ok' if c else 'no' }}">{{ '●' if c else '○' }}</td><td>{% if c %}Consumption, {{ plants.get(pl, pl) }}{% else %}<b>Consumption, {{ plants.get(pl, pl) }}</b>{% endif %}</td><td class="small">{% if c %}{{ when(c.taken_at) }} · {{ c.source|planfull }}{% else %}<b>not received</b>{% endif %}</td></tr>{% endfor %}
<tr><td class="{{ 'ok' if cur.reads.structures else 'no' }}">{{ '●' if cur.reads.structures else '○' }}</td><td>Materials, plants, calendar</td><td class="small">{{ when(cur.reads.structures.taken_at) if cur.reads.structures else 'not received' }}</td></tr>
<tr><td class="{{ 'ok' if cur.reads.structures else 'no' }}">{{ '●' if cur.reads.structures else '○' }}</td><td>Opening stock</td><td class="small">close of {{ per(chosen.actuals_to) }}</td></tr>
<tr><td class="{{ 'ok' if cur.reads.structures else 'no' }}">{{ '●' if cur.reads.structures else '○' }}</td><td>Contracted receipts</td><td class="small">close of {{ per(chosen.actuals_to) }}</td></tr>
</tbody></table>
<p class="hint">● received · ○ not received.{% if cur.missing %} {{ pn(cur.missing, ', ') }} waits on its consumption; the rest can be worked now.{% endif %}</p></div>

<div class="two">
<div class="card"><h3>What it reads <span class="small muted" style="font-weight:400">— copies, not connections</span></h3>
<table><thead><tr><th>Input</th><th>Taken from</th><th>How</th><th>Copy taken</th><th></th></tr></thead><tbody>
{% for pl, c in cur.reads.consumption.items() %}<tr><td>Consumption<div class="small muted">{{ plants.get(pl, pl) }}</div></td><td>{% if c %}{{ c.source|planfull }}<div class="small muted">IBP plan</div>{% else %}—{% endif %}</td><td>{{ c.how if c else '' }}</td><td>{% if c %}{{ when(c.taken_at) }}{% else %}<b>○ none yet</b>{% endif %}</td><td class="acts">{% if may %}<a class="button act" href="{{ url_for('plan.purchasing_plans', purchasing=chosen.id, change=pl) }}#change">Change</a>{% endif %}</td></tr>{% endfor %}
<tr><td>Materials, plants, calendar</td><td>The structures as loaded<div class="small muted">the key materials, their plants and how each is bought</div></td><td>master data</td><td>{{ when(cur.reads.structures.taken_at) if cur.reads.structures else '' }}</td><td></td></tr>
<tr><td>Opening stock</td><td>Actuals<div class="small muted">volume and value on hand</div></td><td>the record</td><td>close of {{ per(chosen.actuals_to) }}</td><td></td></tr>
<tr><td>Contracted receipts</td><td>Actuals<div class="small muted">on order or under contract</div></td><td>the record</td><td>close of {{ per(chosen.actuals_to) }}</td><td></td></tr>
</tbody></table>
{% if may %}<form class="row" style="margin-top:.9rem" method="post" action="{{ url_for('plan.purchasing_refresh') }}"><input type="hidden" name="plan" value="{{ chosen.id }}"><button class="primary">Refresh from the sources</button><span class="hint">takes a new copy from each IBP plan it reads, and of the structures</span></form>{% endif %}
<p class="hint"><b>Endorsed</b> — taken from an IBP plan: what stands in it has been submitted and accepted, and that is the endorsement, so no one is asked. <b>The record</b> — closed periods, read at the close the plan was made at.</p>
<p class="hint">One purchasing plan can buy for several plants, and each plant’s consumption has its own source. This plan holds a copy of each thing it reads; a source changing changes nothing here until you refresh.</p>
{% if change and may %}<h3 id="change" style="margin-top:1.2rem">Change — Consumption, {{ plants.get(change, change) }}</h3>
<form method="post" action="{{ url_for('plan.purchasing_take') }}"><input type="hidden" name="plan" value="{{ chosen.id }}"><input type="hidden" name="plant" value="{{ change }}"><table><tbody>
<tr><td>From an IBP plan<div class="small muted">endorsed · take it now</div></td><td>{% if same_close %}<select name="source">{% for v in same_close %}<option value="{{ v.version_id }}">{{ v.version_id|planfull }}{{ ' · closed' if v.status != 'open' }}</option>{% endfor %}</select>{% else %}<span class="muted">no IBP plan has actuals to {{ per(chosen.actuals_to) }}</span>{% endif %}</td><td class="acts">{% if same_close %}<button class="act">Take</button>{% endif %}</td></tr>
</tbody></table></form>
<p class="hint">Only IBP plans with actuals to {{ per(chosen.actuals_to) }} are offered: a plan at another close is a new plan.</p>{% endif %}
</div>

<div class="card" id="send"><h3>Send a snapshot to the IBP plan</h3>
<form class="row" method="get" action="{{ url_for('plan.purchasing_plans') }}#send"><input type="hidden" name="purchasing" value="{{ chosen.id }}"><label>into the plan and version <select name="into" onchange="this.form.submit()">{% for g in groups %}<optgroup label="{{ g.plan|planfull }}">{% for v in g.versions %}<option value="{{ v.version_id }}" {{ 'selected' if v.version_id == into }} {{ 'disabled' if v.status != 'open' }}>version {{ v.n }} · {{ v.label }}{{ ' · locked' if v.status != 'open' else (' · supply signed off' if locks.get(v.version_id) else '') }}</option>{% endfor %}</optgroup>{% endfor %}</select></label></form>
{% if preview %}<table><thead><tr><th>Material</th><th>Plant</th><th>Period</th><th class="n">Quantity</th><th class="n">Price</th><th>Why</th></tr></thead><tbody>
{% for t in preview[:6] %}<tr><td>{% if t.since != 'as last sent' %}<b>{{ names.get(t.input_code, t.input_code) }}</b>{% else %}{{ names.get(t.input_code, t.input_code) }}{% endif %}</td><td>{{ plants.get(t.plant_code, t.plant_code) }}</td><td>{{ per(t.period) }}</td><td class="n">{{ '{:,.0f}'.format(t.quantity) }}</td><td class="n">{{ '{:,.2f}'.format(t.price) }}</td><td class="small">{{ t.reason }} · {% if t.since != 'as last sent' %}<b>{{ t.since }}</b>{% else %}{{ t.since }}{% endif %}</td></tr>{% endfor %}
{% if preview|length > 6 %}<tr><td colspan="6" class="small muted">and {{ preview|length - 6 }} more</td></tr>{% endif %}
</tbody></table>{% else %}<p class="hint">Nothing typed in this plan: sending it clears what stands for purchasing in the IBP plan.</p>{% endif %}
<p class="hint">The plan as it stands now: {{ preview|length }} receipt{{ '' if preview|length == 1 else 's' }}, {{ n_new }} of them new or different from {% if there and there.carried %}the copy standing there — “{{ there.source }}”, carried across from {{ there.carried.from|planfull }} — which this one replaces{% elif there %}the copy of {{ when(there.at) }} standing there — “{{ there.source }}” — which this one replaces{% else %}anything standing there: nothing stands there yet{% endif %}. Made against {% for pl, c in cur.reads.consumption.items() if c %}consumption of {{ when(c.taken_at) }} at {{ plants.get(pl, pl) }}{{ ', ' if not loop.last }}{% endfor %} and actuals to {{ per(chosen.actuals_to) }}.{% if left_out %} Periods {{ into|plan }} does not plan are left out: {{ left_out|join(', ') }}.{% endif %}</p>
{% if gone %}<p class="warn small"><b>Fewer plants:</b> the copy standing there has receipts at {{ pn(gone, ', ') }}, and this one none — sending leaves nothing standing for {{ 'it' if gone|length == 1 else 'them' }}.</p>{% endif %}
{% if may %}<form class="row" method="post" action="{{ url_for('plan.purchasing_send') }}"><input type="hidden" name="plan" value="{{ chosen.id }}"><input type="hidden" name="into" value="{{ into or '' }}"><button class="primary" {{ 'disabled' if not into_open or into_lock }}>Send the snapshot</button>{% if not into_open %}<span class="hint">{{ into|planfull if into else 'no IBP plan' }} is locked: what stands in it is no longer replaced</span>{% elif into_lock %}<span class="hint">{{ into_lock }}</span>{% endif %}</form>
<form class="row" method="post" enctype="multipart/form-data" action="{{ url_for('plan.purchasing_sheet') }}"><input type="hidden" name="into" value="{{ into or '' }}"><label class="small">or send receipts from a spreadsheet, saved as CSV — {{ sheet_columns|join(', ') }} <input type="file" name="sheet" accept=".csv"></label><button class="act" {{ 'disabled' if not into_open or into_lock }}>Send the spreadsheet</button></form>{% endif %}
</div>
</div>{% endif %}

<h2 id="standing">What stands in each IBP plan<span class="count">one purchasing copy each · read-only, yours included</span></h2>
<table><thead><tr><th>IBP plan</th><th>Version</th><th>Standing there</th><th>Sent</th><th class="n">Receipts</th><th>Supply</th><th>Used after supply</th><th></th></tr></thead><tbody>
{% for v in targets %}{% set s = standing.get(v.version_id) %}<tr><td class="{{ 'muted' if v.status != 'open' }}">{{ pv[v.version_id].plan|planfull }}{% if v.status != 'open' %}<div class="small">locked</div>{% endif %}</td><td class="small">{{ pv[v.version_id].n }} · {{ pv[v.version_id].label }}</td>
<td class="{{ 'muted' if v.status != 'open' }}">{% if s and s.carried %}<span class="muted">carried across from {{ s.carried.from|planfull }}</span><div class="small muted">“{{ s.source }}”, sent {{ when(s.carried.at) }} by {{ s.carried.by }}{% if s.carried.left_behind %} · {{ s.carried.left_behind|length }} left behind{% endif %} · replaced by the first send to this plan{% if v.status != 'open' %} · closed with it — no longer replaced{% endif %}</div>{% elif s %}{{ s.source }}<div class="small muted">by {{ s.by }}{% if s.replaced %} · replaced “{{ s.replaced.source }}”{% if s.replaced.carried_from %}, carried across from {{ s.replaced.carried_from|plan }}{% else %}, sent {{ when(s.replaced.at) }}{% endif %}{% endif %}{% if v.status != 'open' %} · closed with it — no longer replaced{% endif %}</div>{% else %}<span class="muted">nothing sent</span>{% endif %}</td>
<td class="small">{{ (when(s.at) ~ (' — carried' if s.carried else '')) if s else '' }}</td><td class="n">{{ s.receipts|length if s else '' }}</td>
<td class="small">{{ stage_said.get(stage_of.get(v.version_id), 'open') }}</td>
<td class="small">{% set pb = pubs.get(v.version_id) %}{% if pb %}{{ pb.receipts|length }} receipt{{ '' if pb.receipts|length == 1 else 's' }}, {{ pb.says or 'published' }}<div class="muted">{{ when(pb.at) }}{% if waits.get(v.version_id) %} · <b>{{ waits[v.version_id] }} sent since, not yet published</b>{% endif %}</div>{% else %}<span class="muted">as it stands — never published</span>{% endif %}</td>
<td class="acts">{% if s %}<a class="button act" href="{{ url_for('plan.purchasing_plans', purchasing=chosen.id if chosen else None, view=v.version_id) }}#standing">View</a>{% endif %}</td></tr>{% endfor %}
</tbody></table>
{% if viewing %}<h3>Standing in {{ view|planfull }} <span class="small muted" style="font-weight:400">— “{{ viewing.source }}”, {% if viewing.carried %}carried across from {{ viewing.carried.from|planfull }}, sent {{ when(viewing.carried.at) }} by {{ viewing.carried.by }}{% else %}sent {{ when(viewing.at) }} by {{ viewing.by }}{% endif %} · read-only</span></h3>
<table><thead><tr><th>Material</th><th>Plant</th><th>Period</th><th class="n">Quantity</th><th class="n">Price</th><th>Why</th></tr></thead><tbody>
{% for t in viewing.receipts %}<tr><td>{{ names.get(t.input_code, t.input_code) }}</td><td>{{ plants.get(t.plant_code, t.plant_code) }}</td><td>{{ per(t.period) }}</td><td class="n">{{ '{:,.0f}'.format(t.quantity) }}</td><td class="n">{{ '{:,.2f}'.format(t.price) }}</td><td class="small">{{ t.reason }}</td></tr>{% else %}<tr><td colspan="6" class="muted">no receipts — the copy stands empty</td></tr>{% endfor %}
</tbody></table>{% if viewing.carried and viewing.carried.left_behind %}<p class="hint">Left behind when it was carried across: {% for t in viewing.carried.left_behind %}{{ names.get(t.input_code, t.input_code) }}, {{ plants.get(t.plant_code, t.plant_code) }}, {{ per(t.period) }} — {{ t.why }}{{ '; ' if not loop.last else '.' }}{% endfor %}</p>{% endif %}{% endif %}
<p class="hint">Sending makes a read-only copy of the plan’s receipts, held against that IBP plan. Sending again to the same IBP plan replaces the copy — only one ever stands there, and earlier ones are not kept. A new IBP plan begins with the copy that stood in the plan it was started from, carried across, less what was planned for periods that have since closed; your first send to it replaces that. Your plan here stays yours to go on working. What you send is seen at once by the other plans working in supply. The stages after supply — the costing, and Finance — go on using what was last published until supply is signed off twice: its owner’s sign-off locks it, and nothing more is taken from you; the IBP process’s publishes it.</p>

{% if may %}<h2 id="new">New plan</h2>
<div class="card"><form class="entry" method="post" action="{{ url_for('plan.purchasing_new') }}">
<label>Name <input name="name" required value="{{ new_name }}"></label>
<label>Start from <select name="start_from">{% for r in rows %}<option value="{{ r.p.id }}" {{ 'selected' if r.p.id == start }}>{{ r.p.name }} — copy its {{ r.typed }} typed receipt{{ '' if r.typed == 1 else 's' }}</option>{% endfor %}<option value="ibp">What stands in the IBP plan chosen below — purchasing’s receipts there, whoever sent or typed them</option><option value="" {{ 'selected' if not start }}>Nothing typed</option></select></label>
<label>Consumption from <select name="source"><optgroup label="Endorsed — from an IBP plan">{% for v in all_sources %}<option value="{{ v.version_id }}" {{ 'selected' if v.version_id == default_source }}>{{ pv[v.version_id].plan|planfull }}, version {{ pv[v.version_id].n }} · {{ pv[v.version_id].label }} — as it stands now · actuals to {{ per(v.from_period) }}</option>{% endfor %}</optgroup></select><span class="hint">a copy is taken now; it does not follow the source</span></label>
<label>Covers <select name="covers"><option value="ALL">{{ pn(key_plants, ' and ') }} — one plan for {{ 'both plants' if key_plants|length == 2 else 'every plant' }}</option>{% for pl in key_plants %}<option value="{{ pl }}">{{ plants.get(pl, pl) }}</option>{% endfor %}</select><span class="hint">each plant’s consumption can be taken from its own source once the plan is made</span></label>
<label>Actuals to <input value="as the consumption chosen" disabled><span class="hint">opening stock and contracted receipts are read at this close</span></label>
<label>Plans through <input value="as far as the consumption chosen runs" disabled></label>
<div class="actions"><button class="primary">Make the plan</button><span class="hint">opens on its material balance</span></div>
</form></div>{% endif %}
<style>tr.chosen td{background:var(--soft)} tr.chosen td:first-child{box-shadow:inset 3px 0 0 var(--ink)}
.two{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:1.4rem;align-items:start}
@media (max-width:1100px){.two{grid-template-columns:1fr}}
.card h3{margin-top:0} h2 .right{float:right}
a.button{display:inline-block;font-size:.74rem;font-weight:500;padding:.18rem .65rem;border:1px solid var(--rule);border-radius:999px;background:var(--panel);color:var(--ink);text-transform:uppercase;letter-spacing:.07em;text-decoration:none}
a.button:hover{background:var(--soft);border-color:var(--faint)} a.button.primary{background:var(--accent);color:var(--on-accent);border-color:var(--accent);text-transform:none;letter-spacing:0;font-size:.86rem;padding:.42rem 1rem}
.card.status{max-width:560px;padding:.9rem 1.1rem} .card.status td{padding:.3rem .6rem}
table.plans td:first-child{min-width:13rem} table.plans td:nth-child(7){min-width:10rem} table.plans td:nth-child(4){white-space:nowrap}</style>"""


def register(bp, page, who_fn, ctx_fn, busy, session, roles) -> None:
    from . import reads

    def _view():
        who = who_fn()
        mine = W.plans(who)
        chosen = W.plan(ctx_fn().get("purchasing"))
        chosen = chosen if chosen and chosen["owner"] == who else (mine[0] if mine else None)
        plants = {r["node_code"]: r["node_name"] for r in q("select node_code, node_name from dims.dim_node")}
        names = {r["material_code"]: r["material_name"] for r in q("select material_code, material_name from dims.dim_input_material")}
        targets = W.sources()
        state = {v["version_id"]: v for v in targets}
        standing = W.standing_all()
        pv = W.plan_versions(targets)
        groups: list[dict] = []
        for v in targets:
            g = next((x for x in groups if x["plan"] == pv[v["version_id"]]["plan"]), None)
            if not g:
                groups.append(g := {"plan": pv[v["version_id"]]["plan"], "versions": []})
            g["versions"].append({**v, **pv[v["version_id"]]})
        for g in groups:
            g["versions"].sort(key=lambda x: x["n"])
        locks = {v["version_id"]: W.stage_lock(v["version_id"]) for v in targets}
        stage_of = {r["version_id"]: r["state"] for r in q("select version_id, state from plan.stage_state where stage = ?", W.STAGE)}
        pubs = W.published_all()

        def line(p: dict) -> dict:
            rd = W.reads_of(p)
            cons = rd["consumption"]
            got = [c for c in cons.values() if c]
            s = W.sent(p["id"])
            there = standing.get(s["version"]) if s else None
            return {"p": p, "reads": rd, "sources": sorted({c["source"] for c in got}), "taken": sorted({c["taken_at"] for c in got}),
                    "received": len(got) + (3 if rd["structures"] else 0), "inputs": len(cons) + 3, "missing": [pl for pl, c in cons.items() if not c],
                    "typed": len(W.typed(p["id"])), "changed": len(W.changed(p["id"])), "sent": s,
                    "standing_here": bool(there and there.get("plan") == p["id"]),
                    "replaced_by": (there or {}).get("source") or "another", "closed": bool(s) and (state.get(s["version"]) or {}).get("status") != "open"}
        rows = [line(p) for p in mine]
        cur = next((r for r in rows if chosen and r["p"]["id"] == chosen["id"]), None)
        ctx: dict = {}
        if chosen:
            open_ids = [v["version_id"] for v in targets if v["status"] == "open"]
            last = (cur["sent"] or {}).get("version")
            first = next((c["source"] for c in cur["reads"]["consumption"].values() if c), None)
            into = request.args.get("into") if request.args.get("into") in state else \
                next((x for x in (last, first, reads.default_version()) if x in open_ids), open_ids[0] if open_ids else None)
            there = standing.get(into) if into else None
            at_there = {W._cell(r): (r["quantity"], r["price"]) for r in (there or {}).get("receipts", [])}
            typed = W.typed(chosen["id"])
            preview = [{**t, "since": "as last sent" if at_there.get(W._cell(t)) == (t["quantity"], t["price"]) else ("changed" if W._cell(t) in at_there else "new")} for t in typed]
            preview.sort(key=lambda t: (t["since"] == "as last sent", t["input_code"], t["plant_code"], t["period"]))
            into_periods = set(reads.version_periods(into)["plan"]) if into else set()
            ctx = dict(cur=cur, into=into, into_lock=locks.get(into) if into else None, into_open=bool(into) and (state.get(into) or {}).get("status") == "open", there=there, preview=preview,
                       n_new=sum(1 for t in preview if t["since"] != "as last sent"),
                       left_out=sorted({t["period"] for t in typed if t["period"] not in into_periods}),
                       gone=sorted({x["plant_code"] for x in (there or {}).get("receipts", [])} - {t["plant_code"] for t in typed}),
                       change=request.args.get("change") if request.args.get("change") in chosen["plants"] else None,
                       same_close=W.sources(chosen["actuals_to"]))
        view = request.args.get("view")
        open_sources = [v for v in targets if v["status"] == "open"]
        start = request.args.get("start") if any(r["p"]["id"] == request.args.get("start") for r in rows) else None
        start_name = next((r["p"]["name"] for r in rows if r["p"]["id"] == start), None)
        return page(PAGE, title="My plans", active="my_plans", width="1240px", rows=rows, chosen=chosen, plants=plants, names=names, targets=targets,
                    pv=pv, groups=groups, locks=locks, stage_of=stage_of, pubs=pubs, waits={k: W.unpublished(k) for k in pubs},
                    stage_said={"open": "open", "handed over": "signed off — locked", "published": "published"},
                    standing=standing, n_standing=sum(1 for s in standing.values() if s.get("owner") == who),
                    n_changed=sum(r["changed"] for r in rows), n_changed_plans=sum(1 for r in rows if r["changed"]),
                    view=view if view in standing else None, viewing=standing.get(view) if view else None,
                    may=roles.may(who, VERB), start=start, new_name=f"{start_name} — copy" if start_name else "",
                    all_sources=targets, default_source=(open_sources[0]["version_id"] if open_sources else None),
                    pn=lambda codes, sep: sep.join(plants.get(c, c) for c in codes), key_plants=W.key_plants(), sheet_columns=W.SHEET_COLUMNS, per=per, when=when, **ctx)

    @bp.get("/purchasing")
    def purchasing_plans():
        try:
            return _view()
        except Busy as e:
            return busy("My plans", e)

    def _mine(who: str) -> dict | None:
        p = W.plan(request.form.get("plan") or ctx_fn().get("purchasing"))
        return p if p and p["owner"] == who else None

    def _refused(who: str) -> str | None:
        return None if roles.may(who, VERB) else f"{who} does not hold {said(VERB)} — purchases are planned by {', '.join(reads.holders(VERB))}"

    @bp.post("/purchasing/new")
    def purchasing_new():
        who = who_fn(); f = request.form
        name = (f.get("name") or "").strip()
        covers = f.get("covers") or "ALL"
        plants = W.key_plants() if covers == "ALL" else [covers] if covers in W.key_plants() else []
        no = _refused(who) or (None if name else "a plan has a name") or (None if plants else "a plan buys for a plant")
        if no:
            session.say("refused: " + no, False)
            return redirect(url_for("plan.purchasing_plans") + "#new")
        try:
            p = W.make(who, name, f.get("source") or "", plants, f.get("start_from") or None)
        except ValueError as e:
            session.say(f"refused: {e}", False)
            return redirect(url_for("plan.purchasing_plans") + "#new")
        receipts.act("purchasing.plan.make", who, p["name"], True, f"made {p['name']}{' from ' + p['made_from'] if p.get('made_from') else ''}: actuals to {p['actuals_to']}, through {p['through']}, for {', '.join(plants)}")
        session.say(f"{p['name']} made — consumption copied from {reads.plan_codes().get(f.get('source'), (f.get('source'),) * 2)[1]}", True)
        return redirect(url_for("plan.material_purchases", purchasing=p["id"]))

    @bp.post("/purchasing/take")
    def purchasing_take():
        who = who_fn(); p = _mine(who)
        plant, source = request.form.get("plant") or "", request.form.get("source") or ""
        try:
            if _refused(who) or not p:
                raise ValueError(_refused(who) or "no plan of yours is chosen")
            c = W.change(p["id"], plant, source, who)
            session.say(f"{p['name']} reads a copy of {plant}'s consumption from {reads.plan_codes().get(source, (source,) * 2)[1]}, taken {when(c['taken_at'])}", True)
        except ValueError as e:
            session.say(f"refused: {e}", False)
        return redirect(url_for("plan.purchasing_plans") + "#chosen")

    @bp.post("/purchasing/refresh")
    def purchasing_refresh():
        who = who_fn(); p = _mine(who)
        try:
            if _refused(who) or not p:
                raise ValueError(_refused(who) or "no plan of yours is chosen")
            n = len(W.refresh(p["id"], who)) - 1
            session.say(f"{p['name']}: a new copy of the structures and of {n} plant{'s' if n != 1 else ''}' consumption", True)
        except ValueError as e:
            session.say(f"refused: {e}", False)
        return redirect(url_for("plan.purchasing_plans") + "#chosen")

    def _sent(who: str, into: str, checks: list, placed: bool, copy: dict, what: str):
        checks = [{"check": "who may plan purchases", "ok": not _refused(who), "says": _refused(who) or f"{who} holds {said(VERB)}"}] + checks
        placed = placed and not _refused(who)
        session.last = receipts.write("purchase.send", who, what, checks, placed)
        name = reads.plan_codes().get(into, (into, into))[1]
        if overrides.released(who, "purchase", session, f"{what} stands in {name}, replacing whatever stood there", placed):
            return redirect(url_for("plan.run"))
        if not placed:
            session.say("refused: " + "; ".join(x["says"] for x in checks if not x["ok"]), False)
        return redirect(url_for("plan.purchasing_plans", view=into if placed else None) + ("#standing" if placed else "#send"))

    @bp.post("/purchasing/send")
    def purchasing_send():
        """The chosen plan's receipts, as they stand, sent into an IBP plan: they replace what stood there for purchasing."""
        who = who_fn(); p = _mine(who); into = request.form.get("into") or ""
        if not p or _refused(who):
            session.say("refused: " + (_refused(who) or "no plan of yours is chosen"), False)
            return redirect(url_for("plan.purchasing_plans"))
        checks, placed, copy = W.send(into, W.typed(p["id"]), p["name"], who, p)
        return _sent(who, into, checks, placed, copy, f"a snapshot of {p['name']} ({len(copy['receipts'])} receipts)")

    @bp.post("/purchasing/sheet")
    def purchasing_sheet():
        """Receipts from a spreadsheet: the same checks, and they replace what stood there the same way."""
        who = who_fn(); into = request.form.get("into") or ""
        fs = request.files.get("sheet")
        rows = W.read_sheet(fs.read().decode("utf-8-sig")) if fs else []
        if _refused(who):
            session.say("refused: " + _refused(who), False)
            return redirect(url_for("plan.purchasing_plans"))
        checks, placed, copy = W.send(into, rows, "a spreadsheet", who)
        return _sent(who, into, checks, placed, copy, f"a spreadsheet ({len(copy['receipts'])} receipts)")
