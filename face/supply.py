"""The supply plan's first two pages (DEC-20261117-02 point 7), under Integrated business planning → Supply:

- **Inventory** — a material at a stocking point: its demand, target, receipts, projected stock at period end with the
  period's peak beside it, and its safety stock; above a material, every material at the node with its class and cover.
- **Supply plan** — the production requirement by plant, with the stocking points it comes from; a material's
  requirement period by period — proposed, typed, standing — and a form for the supply plan's owner to type a quantity
  over a proposal with a reason, the proposal kept beside it (DEC-20261118-04 point 3).

Both read plan.inventory_flow, made by calc.inventory. Registered on the plan's blueprint by `register(...)`."""
from __future__ import annotations

import datetime as dt

from chassis import receipts
from chassis.landing import LogLanding
from chassis.warehouse import Busy, q
from flask import redirect, request, url_for

from .words import said

VERB = "delta.supply.enter"
ACT_COLUMNS = ["act_id", "action", "withdraws", "version_id", "material_code", "plant_code", "period", "quantity", "reason", "entered_by", "entered_at"]
ACTS = LogLanding("plan", "reg_production_act", ACT_COLUMNS)

MACRO = """{% macro n0(x) %}{{ '' if x is none else '{:,.0f}'.format(x) }}{% endmacro %}"""

INVENTORY = """<h1>Inventory<small>{{ version }} · {{ node_name }}{% if mat_name %} · {{ mat_name }}{% endif %} · replenished to an order-up-to target from the plant that supplies it</small></h1>
<p class="hint">Each stocking point holds the demand over the next review period and lead time, plus a safety stock solved for the fill rate of the material's class ({% for s in levels %}{{ s.service_class }} {{ '{:.0%}'.format(s.fill_rate) }}{{ ', ' if not loop.last }}{% endfor %}); each week it receives what restores the target and ships its demand. A DC's demand is the plan's cases at the ship-tos it serves; a plant's is the DCs' receipts, by the share each takes from it. The variability is what the node shipped a week over the last 52 closed weeks — <b>demand variability, an upper bound</b>: no weekly record of the plan against what shipped is kept yet, so the buffer is larger than a residual would make it. Opening stock is each point's target at the plan's first week — no stock position is loaded. Stock at period end, the week-grain peak beside it.</p>
<div class="seg toolbar"><span class="small muted">node</span>{% for n in nodes %}{% if n.code == node %}<b>{{ n.name }}</b>{% else %}<a href="{{ url_for('plan.inventory', location=n.code, material=material) }}">{{ n.name }}</a>{% endif %}{% endfor %}</div>
{% if rows %}<div style="overflow-x:auto"><table class="stock"><thead><tr><th></th>{% for r in rows %}<th class="n">{{ r.period[2:4] }}·{{ r.period[5:] }}</th>{% endfor %}<th class="n">Total</th></tr></thead><tbody>
<tr><td>Demand</td>{% for r in rows %}<td class="n">{{ n0(r.demand) }}</td>{% endfor %}<td class="n">{{ n0(tot.demand) }}</td></tr>
<tr><td>{{ 'Production' if is_plant else 'Receipts' }}</td>{% for r in rows %}<td class="n {{ 'typed' if r.typed }}">{{ n0(r.receipt) }}{% if r.typed %} ◆{% endif %}</td>{% endfor %}<td class="n">{{ n0(tot.receipt) }}</td></tr>
<tr><td>Target at period end</td>{% for r in rows %}<td class="n">{{ n0(r.target) }}</td>{% endfor %}<td></td></tr>
<tr class="avg"><td><b>Projected stock</b></td>{% for r in rows %}<td class="n"><b>{{ n0(r.closing) }}</b></td>{% endfor %}<td></td></tr>
<tr><td>Peak in the period</td>{% for r in rows %}<td class="n">{{ n0(r.peak) }}</td>{% endfor %}<td></td></tr>
<tr><td>Safety stock</td>{% for r in rows %}<td class="n">{{ n0(r.safety_stock) }}</td>{% endfor %}<td></td></tr>
</tbody></table></div>
<p class="hint">{{ mat_name }} at {{ node_name }}: class {{ cls.service_class or '—' }} ({{ '{:.0%}'.format(cls.fill_rate) if cls.fill_rate else 'no fill rate' }}), {{ var.weeks_shipped or 0 }} of the last 52 weeks shipped, σ {{ n0(var.sigma) if var.sigma is not none else 'none — under 13 weeks shipped, no safety stock' }} a week. <a href="{{ url_for('plan.inventory', location=node, material='ALL') }}">Every material at {{ node_name }}</a>.</p>
{% else %}<h2>Materials at {{ node_name }}<span class="count">{{ listing|length }} · by stock held, average over the plan's periods</span></h2>
<table><thead><tr><th>Material</th><th>Class</th><th class="n">Demand</th><th class="n">Safety stock</th><th class="n">Average stock</th><th class="n">Weeks of cover</th><th class="n">Peak</th></tr></thead><tbody>
{% for m in listing %}<tr><td><a href="{{ url_for('plan.inventory', location=node, material=m.material_code) }}">{{ m.material_name }}</a> <span class="small muted">{{ m.material_code }}</span></td><td>{{ m.service_class or '' }}</td><td class="n">{{ n0(m.demand) }}</td><td class="n">{{ n0(m.safety_stock) }}</td><td class="n">{{ n0(m.avg_stock) }}</td><td class="n">{{ '%.1f'|format(m.cover) if m.cover is not none else '' }}</td><td class="n">{{ n0(m.peak) }}</td></tr>
{% else %}<tr><td colspan="7" class="muted">Nothing stocked at {{ node_name }} on {{ version }}.</td></tr>{% endfor %}</tbody></table>{% endif %}
<style>table.stock td{white-space:nowrap}table.stock td.typed{box-shadow:inset 0 0 0 1px var(--ink)}table.stock tr.avg td{border-top:1px solid var(--rule)}.seg{display:flex;gap:.6rem;flex-wrap:wrap;margin:.4rem 0}</style>"""

SUPPLY = """<h1>Supply plan<small>{{ version }} · the production requirement by plant — what the inventory plan asks each plant to make, not sequenced against the lines</small></h1>
<p class="hint">Each plant's requirement is its replenishment of the DCs it supplies, less its own finished stock, on its own order-up-to target. Whether the lines can make it is the capacity reading's question, not this page's. {% if may and is_open %}You plan supply: type a quantity over a period's proposal with a reason — the proposal stays beside it, and materials read what stands after the next run.{% else %}Typed over by {{ holders|join(', ') or 'nobody yet' }}.{% endif %}</p>
{% for pl in plants %}<h2>{{ pl.name }}<span class="count">cases to make · {{ n0(pl.total) }} over the plan{% if pl.typed %} · {{ pl.typed }} period{{ 's' if pl.typed != 1 }} typed{% endif %}</span></h2>
<div style="overflow-x:auto"><table class="stock"><thead><tr><th></th>{% for p in periods %}<th class="n">{{ p[2:4] }}·{{ p[5:] }}</th>{% endfor %}<th class="n">Total</th></tr></thead><tbody>
<tr><td><b>To make</b></td>{% for p in periods %}<td class="n"><b>{{ n0(pl.by.get(p, {}).get('quantity')) }}</b></td>{% endfor %}<td class="n"><b>{{ n0(pl.total) }}</b></td></tr>
<tr><td class="small muted">proposed</td>{% for p in periods %}<td class="n small muted">{{ n0(pl.by.get(p, {}).get('proposed')) }}</td>{% endfor %}<td class="n small muted">{{ n0(pl.proposed) }}</td></tr>
{% for s in pl.sources %}<tr><td class="small">for {{ s.name }}</td>{% for p in periods %}<td class="n small">{{ n0(s.by.get(p)) }}</td>{% endfor %}<td class="n small">{{ n0(s.total) }}</td></tr>{% endfor %}
<tr><td class="small muted">finished stock at period end</td>{% for p in periods %}<td class="n small muted">{{ n0(pl.by.get(p, {}).get('finished_stock')) }}</td>{% endfor %}<td></td></tr>
</tbody></table></div>{% endfor %}
<h2 id="material">A material<span class="count">{{ mat_name or 'choose a material in the context' }}</span></h2>
{% if mrows %}<div style="overflow-x:auto"><table class="stock"><thead><tr><th>Plant</th><th></th>{% for p in periods %}<th class="n">{{ p[2:4] }}·{{ p[5:] }}</th>{% endfor %}</tr></thead><tbody>
{% for plant, rs in mrows.items() %}<tr><td rowspan="3">{{ plant }}</td><td class="small">to make</td>{% for p in periods %}{% set r = rs.get(p) %}<td class="n {{ 'typed' if r and r.typed }}">{{ n0(r.quantity) if r else '' }}{% if r and r.typed %} ◆{% endif %}</td>{% endfor %}</tr>
<tr><td class="small muted">proposed</td>{% for p in periods %}{% set r = rs.get(p) %}<td class="n small muted">{{ n0(r.proposed) if r else '' }}</td>{% endfor %}</tr>
<tr><td class="small muted">to the DCs</td>{% for p in periods %}{% set r = rs.get(p) %}<td class="n small muted">{{ n0(r.shipped_to_dcs) if r else '' }}</td>{% endfor %}</tr>{% endfor %}</tbody></table></div>{% endif %}
{% if typed %}<h2>Typed<span class="count">{{ typed|length }} standing on {{ version }}</span></h2><table><thead><tr><th>Material</th><th>Plant</th><th>Period</th><th class="n">Typed</th><th class="n">Proposed</th><th>Why</th><th>By</th><th></th></tr></thead><tbody>
{% for t in typed %}<tr><td>{{ t.material_code }}</td><td>{{ t.plant_code }}</td><td>{{ t.period }}</td><td class="n">{{ n0(t.quantity) }}</td><td class="n">{{ n0(t.proposed) }}</td><td class="small">{{ t.reason }}</td><td class="small">{{ t.entered_by }}</td>
<td>{% if may and is_open %}<form class="inline" method="post" action="{{ url_for('plan.production_withdraw') }}"><input type="hidden" name="act_id" value="{{ t.act_id }}"><input name="reason" required placeholder="why" size="10"> <button class="act">Withdraw</button></form>{% endif %}</td></tr>{% endfor %}</tbody></table>{% endif %}
{% if may and is_open %}<h2 id="type">Type a production quantity<span class="count">over a period's proposal, with a reason</span></h2>
<form class="entry" method="post" action="{{ url_for('plan.production_type') }}">
<label class="wide">material at a plant<select name="key">{% for m in materials %}<option value="{{ m.material_code }}|{{ m.plant_code }}" {{ 'selected' if m.material_code == material }}>{{ m.material_name }} · {{ m.plant_code }}</option>{% endfor %}</select></label>
<label>period<select name="period">{% for x in periods %}<option>{{ x }}</option>{% endfor %}</select></label>
<label>cases<input name="quantity" type="number" step="any" min="0" required></label>
<label class="wide">why<input name="reason" required placeholder="a campaign run, a line down, a build ahead"></label>
<div class="actions"><button class="primary">Place</button><span class="hint">by {{ who_ }} — in the plan after the next run</span></div></form>{% endif %}
{% if last %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else ('!' if c.flag else '✕') }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}
<style>table.stock td{white-space:nowrap}table.stock td.typed{box-shadow:inset 0 0 0 1px var(--ink)}</style>"""


def register(bp, page, who_fn, ctx_fn, busy, session, roles) -> None:
    from . import reads

    def version_of() -> str:
        return ctx_fn().get("version") or reads.default_version()

    def leaf(code: str | None) -> str | None:
        return code if code and q("select 1 ok from dims.dim_material where material_code = ?", code) else None

    @bp.get("/supply/inventory")
    def inventory():
        try:
            c = ctx_fn(); version = version_of()
            nodes = [{"code": r["node_code"], "name": r["node_name"], "kind": r["node_kind"]} for r in q("select node_code, node_name, node_kind from dims.dim_node order by node_kind desc, node_code")]
            node = c.get("location") if c.get("location") in {n["code"] for n in nodes} else next((n["code"] for n in nodes if n["kind"] != "plant"), nodes[0]["code"])
            mat = leaf(c.get("material"))
            names = {r["material_code"]: r["material_name"] for r in q("select material_code, material_name from dims.dim_material")}
            rows, listing, cls, var = [], [], {}, {}
            if mat:
                rows = q("select * from plan.inventory_flow where version_id = ? and node_code = ? and material_code = ? order by period", version, node, mat)
                cls = (q("select * from plan.service_class where version_id = ? and material_code = ?", version, mat) or [{}])[0]
                var = (q("select * from plan.demand_variability where node_code = ? and material_code = ?", node, mat) or [{}])[0]
            else:
                listing = q("""select f.material_code, any_value(c.service_class) service_class, sum(f.demand) demand, max(f.safety_stock) safety_stock,
                                      avg(f.closing) avg_stock, max(f.peak) peak, avg(f.closing) / nullif(sum(f.demand) / nullif(sum(f.weeks), 0), 0) cover
                               from plan.inventory_flow f left join plan.service_class c on c.version_id = f.version_id and c.material_code = f.material_code
                               where f.version_id = ? and f.node_code = ? group by 1 order by avg_stock desc nulls last limit 150""", version, node)
                listing = [{**m, "material_name": names.get(m["material_code"], m["material_code"])} for m in listing]
            tot = {k: sum(r[k] or 0 for r in rows) for k in ("demand", "receipt")}
            return page(MACRO + INVENTORY, title="Inventory", active="inventory", width="none", version=version, nodes=nodes, node=node,
                        node_name=next(n["name"] for n in nodes if n["code"] == node), is_plant=next(n["kind"] for n in nodes if n["code"] == node) == "plant",
                        material=mat or "ALL", mat_name=names.get(mat) if mat else None, rows=rows, tot=tot, listing=listing, cls=cls, var=var,
                        levels=q("select * from dims.ref_service_level order by service_class"))
        except Busy as e:
            return busy("Inventory", e)

    @bp.get("/supply/plan")
    def supply_plan():
        try:
            c = ctx_fn(); who = who_fn(); version = version_of(); v = reads.version(version) or {}
            loc = c.get("location") or "ALL"
            mat = leaf(c.get("material"))
            names = {r["node_code"]: r["node_name"] for r in q("select node_code, node_name from dims.dim_node")}
            req = q("select plant_code, period, sum(quantity) quantity, sum(proposed) proposed, sum(finished_stock) finished_stock, count(*) filter (where typed) typed from plan.production_requirement where version_id = ? group by all order by 1, 2", version)
            src = q("select plant_code, node_code, period, sum(cases) cases from plan.production_source where version_id = ? group by all", version)
            periods = sorted({r["period"] for r in req})
            plants = []
            for p in sorted({r["plant_code"] for r in req}):
                if loc != "ALL" and loc != p and loc in names and q("select 1 ok from dims.dim_node where node_code = ? and node_kind = 'plant'", loc):
                    continue
                by = {r["period"]: r for r in req if r["plant_code"] == p}
                sources = []
                for n in sorted({s["node_code"] for s in src if s["plant_code"] == p}):
                    sb = {s["period"]: s["cases"] for s in src if s["plant_code"] == p and s["node_code"] == n}
                    sources.append({"name": names.get(n, n), "by": sb, "total": sum(sb.values())})
                plants.append({"name": names.get(p, p), "by": by, "total": sum(r["quantity"] or 0 for r in by.values()), "proposed": sum(r["proposed"] or 0 for r in by.values()),
                               "typed": sum(1 for r in by.values() if r["typed"]), "sources": sources})
            mrows: dict = {}
            if mat:
                for r in q("select * from plan.production_requirement where version_id = ? and material_code = ? order by plant_code, period", version, mat):
                    mrows.setdefault(r["plant_code"], {})[r["period"]] = r
            typed = q("""select a.*, r.proposed from plan.production_act a left join plan.production_requirement r using (version_id, material_code, plant_code, period)
                         where a.version_id = ? order by a.material_code, a.period""", version)
            materials = q("""select distinct r.material_code, m.material_name, r.plant_code from plan.production_requirement r join dims.dim_material m using (material_code)
                             where r.version_id = ? order by m.material_name""", version)
            mat_name = (q("select material_name from dims.dim_material where material_code = ?", mat) or [{}])[0].get("material_name") if mat else None
            return page(MACRO + SUPPLY, title="Supply plan", active="supply", width="none", version=version, plants=plants, periods=periods, mrows=mrows,
                        material=mat, mat_name=mat_name, typed=typed, materials=materials, may=roles.may(who, VERB), holders=reads.holders(VERB),
                        is_open=v.get("status") == "open", who_=who, last=session.last, receipt_acts=("production",))
        except Busy as e:
            return busy("Supply plan", e)

    @bp.post("/supply/plan/type")
    def production_type():
        f = request.form; who = who_fn(); version = version_of(); v = reads.version(version) or {}
        mat, _, plant = (f.get("key") or "").partition("|")
        period, reason = f.get("period") or "", (f.get("reason") or "").strip()
        try:
            qty = float(f.get("quantity") or "")
        except ValueError:
            qty = None
        cell = q("select proposed from plan.production_requirement where version_id = ? and material_code = ? and plant_code = ? and period = ?", version, mat, plant, period)
        stage = reads.stage_open(version, "production") if hasattr(reads, "stage_open") else (True, "")
        checks = [
            {"check": "who may plan supply", "ok": roles.may(who, VERB), "says": f"{who} holds {said(VERB)}" if roles.may(who, VERB) else f"{who} does not hold {said(VERB)} — supply is planned by {', '.join(reads.holders(VERB))}"},
            {"check": "the plan is open", "ok": v.get("status") == "open", "says": f"{version} is {v.get('status', 'unknown')}"},
            {"check": "the stage is open", "ok": stage[0], "says": stage[1] or "production is open on this plan"},
            {"check": "a proposal to type over", "ok": bool(cell), "says": f"{mat} at {plant} in {period}: {cell[0]['proposed']:,.0f} proposed" if cell else f"{mat or 'nothing'} at {plant or '—'} has no requirement in {period or 'no period'}"},
            {"check": "a quantity", "ok": qty is not None and qty >= 0, "says": f"{qty:,.0f} cases" if qty is not None and qty >= 0 else "a number of cases, not below zero"},
            {"check": "a reason", "ok": bool(reason), "says": reason or "a typed quantity says why"},
        ]
        placed = receipts.judge(checks)
        if placed:
            now = dt.datetime.now()
            ACTS.place([{"act_id": f"PRD-{now:%Y%m%d%H%M%S%f}", "action": "set", "withdraws": "", "version_id": version, "material_code": mat, "plant_code": plant,
                         "period": period, "quantity": qty, "reason": reason, "entered_by": who, "entered_at": now.isoformat(timespec="seconds")}], who)
        session.last = receipts.write("production.type", who, f"{mat}:{plant}:{period}", checks, placed)
        session.say(f"{mat} at {plant} in {period} placed — in the plan after the next run" if placed else "refused: " + "; ".join(x["says"] for x in checks if not x["ok"]), placed)
        return redirect(url_for("plan.supply_plan") + "#type")

    @bp.post("/supply/plan/withdraw")
    def production_withdraw():
        f = request.form; who = who_fn()
        act = q("select * from plan.production_act where act_id = ?", f.get("act_id") or "")
        reason = (f.get("reason") or "").strip()
        v = (reads.version(act[0]["version_id"]) or {}) if act else {}
        checks = [
            {"check": "who may plan supply", "ok": roles.may(who, VERB), "says": f"{who} holds {said(VERB)}" if roles.may(who, VERB) else f"{who} does not hold {said(VERB)}"},
            {"check": "a typed quantity standing", "ok": bool(act), "says": f"{act[0]['act_id']}: {act[0]['material_code']} at {act[0]['plant_code']} in {act[0]['period']}" if act else "no such typed quantity in force"},
            {"check": "the plan is open", "ok": v.get("status") == "open", "says": f"{v.get('version_id', '—')} is {v.get('status', 'unknown')}"},
            {"check": "a reason", "ok": bool(reason), "says": reason or "a withdrawal says why"},
        ]
        placed = receipts.judge(checks)
        if placed:
            now = dt.datetime.now(); a = act[0]
            ACTS.place([{"act_id": f"PRD-{now:%Y%m%d%H%M%S%f}", "action": "withdraw", "withdraws": a["act_id"], "version_id": a["version_id"], "material_code": a["material_code"],
                         "plant_code": a["plant_code"], "period": a["period"], "quantity": "", "reason": reason, "entered_by": who, "entered_at": now.isoformat(timespec="seconds")}], who)
        session.last = receipts.write("production.withdraw", who, f.get("act_id") or "", checks, placed)
        session.say("withdrawn — the proposal stands again after the next run" if placed else "refused: " + "; ".join(x["says"] for x in checks if not x["ok"]), placed)
        return redirect(url_for("plan.supply_plan"))
