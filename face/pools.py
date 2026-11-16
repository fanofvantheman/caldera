"""Cost pools (DEC-20261116-03): the short set of pools the cost of a case is made of, each in one of the four components,
and the map of the plan's cost centre × account onto them — kept on this page by whoever keeps the cost centre map, each
rule set or removed an act (`reg_cost_pool_rule`), the latest per key standing. Every cell carrying a cost resolves to a
pool or to *not in cost of goods*; a cell with no rule is marked here and waits on the worklist until a rule reaches it.
The pool declares the component; a schedule line whose driver disagrees is marked, never a second answer.

Registered on the plan's blueprint by `register(...)`, called once from `face/__main__.py`."""
from __future__ import annotations

import datetime as dt

from chassis import receipts
from chassis.landing import LogLanding
from chassis.warehouse import Busy, q
from flask import redirect, request, url_for

from .costs import pay_withheld, planning_cost_centres
from .words import said

VERB = "register.cost_centre_map.maintain"
RULE_COLUMNS = ["act_id", "action", "entity_code", "cost_centre_code", "account_code", "pool_code", "set_by", "set_at", "reason"]
RULES = LogLanding("plan", "reg_cost_pool_rule", RULE_COLUMNS)
COMPONENTS = [("material", "Material"), ("labour", "Labour"), ("variable_overhead", "Variable overhead"), ("fixed_overhead", "Fixed overhead"), (None, "Not in cost of goods")]

POOLS = """<h1>Cost pools<small>{{ version }} · the kinds of cost a case is made of, each in one of the four components — where a rate is set and read</small></h1>
{% for comp, label in components %}<h2>{{ label }}<span class="count">{{ pools_by[comp]|length }} pool{{ '' if pools_by[comp]|length == 1 else 's' }}</span></h2>
<table><thead><tr><th>Pool</th><th>Reaches a case by</th>{% if comp %}{% for p in plants %}<th class="n">{{ p.name }} · cost</th><th class="n">{{ p.name }} · per case</th>{% endfor %}{% else %}<th class="n">Cost</th>{% endif %}<th class="n">Cells</th></tr></thead><tbody>
{% for pl in pools_by[comp] %}<tr><td><b>{{ pl.pool_name }}</b></td><td class="small">{{ pl.reaches }}</td>
{% if comp %}{% for p in plants %}{% set f = figs.get((pl.pool_code, p.code)) %}<td class="n">{{ money0(f.cost) if f else '' }}</td><td class="n">{{ money(f.per_case) if f else '' }}</td>{% endfor %}{% else %}<td class="n">{{ money0(not_cogs) }}</td>{% endif %}
<td class="n">{% if pl.cells %}<a href="{{ url_for('plan.cost_pool_map', pool=pl.pool_code) }}">{{ pl.cells }}</a>{% elif comp == 'material' %}<span class="small muted">read from the input</span>{% elif comp == 'labour' %}<span class="small muted">read from the route</span>{% else %}0{% endif %}</td></tr>{% endfor %}
{% if comp %}<tr class="total"><td>{{ label }}</td><td></td>{% for p in plants %}{% set t = totals.get((comp, p.code)) %}<td class="n">{{ money0(t.cost) if t and t.cost is not none else '' }}</td><td class="n"><b>{{ money(t.per_case) if t else '' }}</b></td>{% endfor %}<td></td></tr>{% endif %}
</tbody></table>{% endfor %}
<p class="hint">Per case at {{ period }}, weighted by its cases at the plant. <b>Cost</b>: for an overhead pool, its schedule lines at the plant over the {{ n_sched }} planned periods — indirect labour less the direct labour the routes' crews take for the plan's cases; for material and direct labour, the cases planned at the plant × their cost per case over the same periods. A variable pool's per case is its lines' rates per case made; a fixed pool's is its cost for the year ÷ the planned cases at the plant, both set on the business plan of the year and held on every plan of it. The cost centre stops at the map: from here on a rate is a pool's at a plant. <a href="{{ url_for('plan.cost_pool_map') }}">The map</a> says which cost centre × account is in which pool.</p>
{% if waiting %}<p class="hint"><b>{{ waiting }}</b> cell{{ '' if waiting == 1 else 's' }} carrying a cost in no pool — <a href="{{ url_for('plan.cost_pool_map') }}#unmapped">set a rule for each</a>.</p>{% endif %}"""

MAP = """<h1>The map<small>{{ version }} · the plan's cost centre × account onto the cost pools · the cost over its {{ n_sched }} planned periods{% if pool %} · {{ pool_name }} only{% endif %}</small></h1>
<p class="hint">Each cell is the pool its cost is in, by the most specific rule: a cost centre × account rule, then a cost centre whatever the account, then an account whatever the cost centre; a rule naming the entity before one that does not. {% if may %}You keep the map: a rule set or removed is in force after the next run.{% else %}The map is kept by {{ holders|join(', ') or 'nobody yet' }}.{% endif %}{% if pool %} <a href="{{ url_for('plan.cost_pool_map', pool=None) }}">Every pool</a>.{% endif %}</p>
<div class="cards"><div class="card stat"><b>{{ counts.cells }}</b><span>cells carrying a cost</span></div><div class="card stat"><b>{{ counts.in_cogs }}</b><span>in a pool of cost of goods</span></div>
<div class="card stat"><b>{{ counts.unmapped }}</b><span>in no pool{% if counts.unmapped %} — marked ✕{% endif %}</span></div><div class="card stat"><b>{{ counts.disagree }}</b><span>whose driver disagrees with the pool{% if counts.disagree %} — marked ▲{% endif %}</span></div></div>
<div style="overflow-x:auto"><table class="poolmap"><thead><tr><th>Cost centre</th><th>Plant</th>{% for a in accounts %}<th class="n" title="{{ a.account_name }}">{{ a.account_code }}<br><span class="small">{{ a.account_name }}</span></th>{% endfor %}</tr></thead><tbody>
{% for r in rows %}<tr class="{{ 'out' if r.all_out }}"><td style="white-space:nowrap">{{ r.cost_centre_name }} <span class="small muted">{{ r.cost_centre_code }}{% if r.entity_code %} · {{ r.entity_code }}{% endif %}</span></td><td class="small">{{ r.plant_name or '' }}</td>
{% for a in accounts %}{% set c = r.cells.get(a.account_code) %}<td class="n small {{ 'none' if c and c.unmapped }}{{ ' dis' if c and c.driver_disagrees }}{{ ' dim' if c and pool and c.pool_code != pool }}">{% if c %}<span class="pool" title="{{ c.why }}">{% if c.unmapped %}✕ no rule{% else %}{{ c.pool_name }}{% if c.driver_disagrees %} ▲{% endif %}{% endif %}</span><br>{{ c.shown }}{% endif %}</td>{% endfor %}</tr>{% endfor %}
</tbody></table></div>
<p class="hint">Amounts are this version's schedule over its planned periods; a cell carried only in the ledgers' actuals shows the last twelve closed periods' actuals, in italics. ▲: the pool's component and the line's driver disagree — a variable pool whose line is not driven by cases made at the plant, or a fixed pool whose line is; the pool decides, the driver is the check. Hover a cell for the rule that reaches it.{% if withheld %} Labour in the cost centres planned by name is individual pay and is not shown here.{% endif %}</p>
{% if unmapped %}<h2 id="unmapped">In no pool<span class="count">a cost the plan cannot place — set a rule for each</span></h2>
<table><thead><tr><th>Cost centre</th><th>Account</th><th>Entity</th><th>Driver</th></tr></thead><tbody>{% for u in unmapped %}<tr><td>{{ u.cost_centre_name }} <span class="small muted">{{ u.cost_centre_code }}</span></td><td>{{ u.account_code }} {{ u.account_name }}</td><td>{{ u.entity_code }}</td><td class="small">{{ u.drivers or 'actuals only' }}</td></tr>{% endfor %}</tbody></table>{% endif %}
{% if may %}<h2 id="rule">Set a rule<span class="count">the pool a cost centre × account is in — leave either blank for any</span></h2>
<form class="entry" method="post" action="{{ url_for('plan.cost_pool_rule') }}">
<label>entity<select name="entity_code"><option value="">any</option>{% for e in entities %}<option value="{{ e.entity_code }}">{{ e.entity_name }}</option>{% endfor %}</select></label>
<label>cost centre<select name="cost_centre_code"><option value="">any</option>{% for c in centres %}<option value="{{ c.cost_centre_code }}">{{ c.cost_centre_name }} · {{ c.cost_centre_code }}</option>{% endfor %}</select></label>
<label>account<select name="account_code"><option value="">any</option>{% for a in all_accounts %}<option value="{{ a.account_code }}">{{ a.account_code }} {{ a.account_name }}</option>{% endfor %}</select></label>
<label>pool<select name="pool_code">{% for comp, label in components %}<optgroup label="{{ label }}">{% for pl in pools_by[comp] if pl.component not in ('material', 'labour') %}<option value="{{ pl.pool_code }}">{{ pl.pool_name }}</option>{% endfor %}</optgroup>{% endfor %}<option value="">— remove the rule for this key</option></select></label>
<label class="wide">why<input name="reason" required placeholder="what the rule is for"></label>
<div class="actions"><button class="primary">Set the rule</button><span class="hint">by {{ who }} — in force after the next run</span></div></form>{% endif %}
<h2>Rules in force<span class="count">{{ rules|length }} · the latest act per key</span></h2>
<table><thead><tr><th>Entity</th><th>Cost centre</th><th>Account</th><th>Pool</th><th>Why</th><th>Set by</th><th>When</th></tr></thead><tbody>
{% for r in rules %}<tr><td>{{ r.entity_code or 'any' }}</td><td>{{ r.cost_centre_code or 'any' }}</td><td>{{ r.account_code or 'any' }}</td><td>{{ r.pool_name or r.pool_code }}</td><td class="small">{{ r.reason or '' }}</td><td class="small">{{ r.set_by }}</td><td class="small">{{ r.set_at }}</td></tr>{% endfor %}</tbody></table>
{% if last %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else ('!' if c.flag else '✕') }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}
<style>table.poolmap td{vertical-align:top}table.poolmap td .pool{font-size:.72rem;color:var(--muted)}table.poolmap td.none .pool{color:var(--bad,#a33);font-weight:600}
table.poolmap td.dis .pool{color:var(--warn,#a60);font-weight:600}table.poolmap td.dim{opacity:.35}table.poolmap tr.out td{color:var(--muted)}</style>"""

MACRO = """{% macro money(x) %}{{ '' if x is none else '{:,.2f}'.format(x) }}{% endmacro %}{% macro money0(x) %}{{ '' if x is none else '{:,.0f}'.format(x) }}{% endmacro %}"""


def pools() -> list[dict]:
    return q("select * from dims.ref_cost_pool order by sort_order")


def register(bp, page, who_fn, ctx_fn, busy, session, roles) -> None:
    from . import reads

    def version_of() -> str:
        return ctx_fn().get("version") or reads.default_version()

    @bp.get("/costs/pools")
    def cost_pools():
        try:
            version = version_of()
            plan_periods = reads.version_periods(version)["plan"] or [""]
            period = plan_periods[0]
            plants = [{"code": r["node_code"], "name": r["node_name"]} for r in q(
                "select distinct n.node_code, n.node_name from dims.dim_node n join plan.ref_cost_centre_plant c on c.plant_code = n.node_code order by 1")]
            ps = pools()
            cells = {r["pool_code"]: r["n"] for r in q("select pool_code, count(*) n from plan.cost_pool_cell where pool_code is not null group by 1")}
            figs: dict = {}
            # overheads: the pool's cost over the schedule's planned periods at the plant; per case at the first plan period
            for r in q("""select plant_code, pool_code, sum(case when component = 'variable_overhead' then lines_amount else amount end) as "cost"
                          from plan.cost_pool_rate where version_id = ? group by all""", version):
                figs[(r["pool_code"], r["plant_code"])] = {"cost": r["cost"], "per_case": None}
            sched = [r["period"] for r in q("select distinct period from plan.cost_pool_rate where version_id = ? order by 1", version)]
            per_case = q("""select s.plant_code, s.pool_code, s.component, sum(s.per_case * d.c) / nullif(sum(d.c), 0) per_case
                            from plan.planned_unit_cost_pool s
                            join (select material_code, sum(cases) c from plan.demand_financialised where version_id = ? and period = ? group by 1) d using (material_code)
                            where s.version_id = ? and s.period = ? group by all""", version, period, version, period)
            for r in per_case:
                figs.setdefault((r["pool_code"], r["plant_code"]), {"cost": None, "per_case": None})["per_case"] = r["per_case"]
            # material and direct labour have no schedule line: their cost is the plan's cases × the cost per case over the same periods
            if sched:
                ph = ",".join("?" * len(sched))
                for r in q(f"""select s.plant_code, s.pool_code, sum(s.per_case * d.c) as "cost" from plan.planned_unit_cost_pool s
                               join (select material_code, period, sum(cases) c from plan.demand_financialised where version_id = ? group by all) d using (material_code, period)
                               where s.version_id = ? and s.component in ('material', 'labour') and s.period in ({ph}) group by all""", version, version, *sched):
                    figs.setdefault((r["pool_code"], r["plant_code"]), {"cost": None, "per_case": None})["cost"] = r["cost"]
            totals: dict = {}
            for pl in ps:
                for p in plants:
                    f = figs.get((pl["pool_code"], p["code"]))
                    if f and pl["component"]:
                        t = totals.setdefault((pl["component"], p["code"]), {"cost": 0.0, "per_case": 0.0})
                        t["cost"] += f["cost"] or 0; t["per_case"] += f["per_case"] or 0
            not_cogs = q("""select sum(s.amount) a from plan.opex_schedule s join plan.cost_pool_cell c using (entity_code, cost_centre_code, account_code)
                            where s.version_id = ? and c.pool_code = 'NOT_COGS'""", version)[0]["a"]
            pools_by = {comp: [] for comp, _ in COMPONENTS}
            for pl in ps:
                pools_by[pl["component"]].append({**pl, "cells": cells.get(pl["pool_code"], 0)})
            waiting = q("select count(*) n from plan.worklist_cost_pool_unmapped")[0]["n"]
            return page(MACRO + POOLS, title="Cost pools", active="pools_set", version=version, period=period, plants=plants, components=COMPONENTS,
                        pools_by=pools_by, figs=figs, totals=totals, not_cogs=not_cogs, n_sched=len(sched), waiting=waiting)
        except Busy as e:
            return busy("Cost pools", e)

    @bp.get("/costs/pool_map")
    def cost_pool_map():
        try:
            who = who_fn(); version = version_of()
            pool = request.args.get("pool") or ""
            ps = pools(); names = {p["pool_code"]: p["pool_name"] for p in ps}
            cond, named = pay_withheld(roles, who)
            labour = {r["account_code"] for r in q("select account_code from dims.dim_gl_account where is_labour")}
            cells = q("""select c.*, coalesce(cc.cost_centre_name, c.cost_centre_code) cost_centre_name from plan.cost_pool_cell c
                         left join plan.planning_cost_centre cc on cc.cost_centre_code = c.cost_centre_code""")
            amounts = {(r["entity_code"], r["cost_centre_code"], r["account_code"]): r["a"] for r in q(
                "select entity_code, cost_centre_code, account_code, sum(amount) a from plan.opex_schedule where version_id = ? group by all", version)}
            year = [r["period"] for r in q("select period from dims.dim_period where period_state = 'CLOSED' order by period desc limit 12")]
            actual = {}
            if year:
                ph = ",".join("?" * len(year))
                actual = {(r["entity_code"], r["cost_centre_code"], r["account_code"]): r["a"] for r in q(
                    f"select entity_code, cost_centre_code, account_code, sum(amount) a from plan.cost_actual where state = 'mapped' and period in ({ph}) group by all", *year)}
            plant_names = {r["node_code"]: r["node_name"] for r in q("select node_code, node_name from dims.dim_node")}
            accounts = sorted({c["account_code"] for c in cells})
            acct_names = {r["account_code"]: r["account_name"] for r in q("select account_code, account_name from dims.dim_gl_account")}
            rows: dict = {}
            for c in cells:
                key = (c["cost_centre_code"], c["entity_code"])
                r = rows.setdefault(key, {"cost_centre_code": c["cost_centre_code"], "cost_centre_name": c["cost_centre_name"], "entity_code": c["entity_code"],
                                          "plant_name": plant_names.get(c["plant_code"]) if c["plant_code"] else "", "cells": {}, "all_out": True})
                k = (c["entity_code"], c["cost_centre_code"], c["account_code"])
                hide = c["cost_centre_code"] in named and c["account_code"] in labour
                if k in amounts:
                    shown = "" if hide else f"{amounts[k]:,.0f}"
                elif k in actual:
                    shown = "" if hide else f"<i>{actual[k]:,.0f}</i>"
                else:
                    shown = ""
                if c["unmapped"]:
                    why = "no rule reaches this cell"
                else:
                    rule = " × ".join(x for x in [c["rule_cost_centre"] or "", c["rule_account"] or ""] if x) or "?"
                    why = f"{c['pool_name']} by the rule {rule}{' for ' + c['entity_code'] if c['rule_names_entity'] else ''}" + (f" · driver: {c['drivers']}" if c["drivers"] else "")
                r["cells"][c["account_code"]] = {**c, "shown": shown, "why": why}
                r["all_out"] &= c["pool_code"] == "NOT_COGS"
            order = {cc["code"]: i for i, cc in enumerate(planning_cost_centres())}
            shown_rows = sorted(rows.values(), key=lambda r: (r["all_out"], order.get(r["cost_centre_code"], 999), r["entity_code"]))
            if pool:
                shown_rows = [r for r in shown_rows if any(c["pool_code"] == pool for c in r["cells"].values())]
            rules = [{**r, "pool_name": names.get(r["pool_code"])} for r in q("select * from plan.cost_pool_map order by tier, cost_centre_code, account_code, entity_code")]
            counts = {"cells": len(cells), "in_cogs": sum(1 for c in cells if c["component"]), "unmapped": sum(1 for c in cells if c["unmapped"]),
                      "disagree": sum(1 for c in cells if c["driver_disagrees"])}
            pools_by = {comp: [p for p in ps if p["component"] == comp] for comp, _ in COMPONENTS}
            n_sched = q("select count(distinct period) n from plan.opex_schedule where version_id = ?", version)[0]["n"]
            return page(MACRO + MAP, title="The map", active="pools_map", width="none", version=version, pool=pool, pool_name=names.get(pool, ""),
                        accounts=[{"account_code": a, "account_name": acct_names.get(a, a)} for a in accounts], rows=shown_rows, counts=counts,
                        unmapped=q("select * from plan.worklist_cost_pool_unmapped order by cost_centre_code, account_code"), rules=rules,
                        may=roles.may(who, VERB), holders=reads.holders(VERB), entities=q("select entity_code, entity_name from dims.dim_entity order by 1"),
                        centres=q("select cost_centre_code, cost_centre_name from plan.planning_cost_centre where kind not in ('company', 'function') order by 1"),
                        all_accounts=q("select account_code, account_name from dims.dim_gl_account order by 1"), components=COMPONENTS, pools_by=pools_by,
                        withheld=bool(named), n_sched=n_sched, last=session.last, receipt_acts=("pool",))
        except Busy as e:
            return busy("The map", e)

    @bp.post("/costs/pool_map/rule")
    def cost_pool_rule():
        """A rule set or removed: one act in the map's register. The rule in force for the key is replaced by the latest act;
        removing a key that has no rule is refused."""
        f = request.form; who = who_fn()
        e, cc, acct = (f.get("entity_code") or "").strip(), (f.get("cost_centre_code") or "").strip(), (f.get("account_code") or "").strip()
        pool, reason = (f.get("pool_code") or "").strip(), (f.get("reason") or "").strip()
        may = roles.may(who, VERB)
        known = {p["pool_code"]: p for p in pools()}
        existing = q("select * from plan.cost_pool_map where entity_code = ? and cost_centre_code = ? and account_code = ?", e, cc, acct)
        key = " × ".join(x for x in [cc or "any cost centre", acct or "any account"]) + (f" for {e}" if e else "")
        settable = pool in known and known[pool]["component"] not in ("material", "labour")
        checks = [
            {"check": "who may keep the map", "ok": may, "says": f"{who} holds {said(VERB)}" if may else f"{who} does not hold {said(VERB)} — the map is kept by {', '.join(reads.holders(VERB))}"},
            {"check": "a cost centre or an account", "ok": bool(cc or acct), "says": key if (cc or acct) else "a rule names a cost centre, an account, or both"},
            {"check": "the pool", "ok": settable if pool else bool(existing),
             "says": (known[pool]["pool_name"] if settable else f"{pool} is not a pool the map can name — material and direct labour are not mapped") if pool
                     else (f"removes the rule {key} → {existing[0]['pool_code']}" if existing else f"there is no rule for {key} to remove")},
            {"check": "a reason", "ok": bool(reason), "says": reason or "a rule says why"},
        ]
        placed = receipts.judge(checks)
        if placed:
            now = dt.datetime.now()
            RULES.place([{"act_id": f"POOL-{now:%Y%m%d%H%M%S%f}", "action": "set" if pool else "remove", "entity_code": e, "cost_centre_code": cc,
                          "account_code": acct, "pool_code": pool, "set_by": who, "set_at": now.isoformat(timespec="seconds"), "reason": reason}], who)
        session.last = receipts.write("pool.rule", who, key, checks, placed)
        session.say((f"{key} → {known[pool]['pool_name']}" if pool else f"the rule for {key} removed") + " — in force after the next run" if placed
                    else "rule refused: " + "; ".join(c["says"] for c in checks if not c["ok"]), placed)
        return redirect(url_for("plan.cost_pool_map") + "#rule")
