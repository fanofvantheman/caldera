"""The other two views of a cost-side object (DEC-20261115-02 points 4–5): the **compare** view — the cost centres beneath
the context's node side by side, each with its step's state, for the process owner — and the **review** view — one cost
centre's figures against the last year and what was entered since it was last handed over, by whom and why, with accept
and send back; it types nothing. The entry view is the object's own page (the schedule, Headcount by role). Each view is a
tab of the object's entry, offered by the right that makes it relevant: the step's `review.<step>.close`, which Commercial
finance holds at the top.

Registered on the plan's blueprint by `register(...)`, called once from `face/__main__.py`."""
from __future__ import annotations

from collections import defaultdict

from chassis.warehouse import Busy, q
from flask import request, url_for

from . import costs
from .workflow import STATE_SAYS

OBJECTS = {
    # object → its step, the entry view's endpoint, what its figures are, the page's title
    "schedule": {"step": "opex", "entry": "plan.schedule", "title": "Opex schedule", "tab": "sch"},
    "headcount": {"step": "labour", "entry": "plan.headcount_role", "title": "Headcount", "tab": "hc"},
}

COMPARE = """<h1>{{ o.title }} · compare<small>{{ version }} · FY{{ fy }} · {{ node_name }} — the cost centres beneath side by side, each with its {{ o.step }} state</small></h1>
{% if not rows %}<p class="lede">{{ node_name }} is one cost centre: there is nothing beneath it to compare — the entry and review views show it.</p>{% else %}
<table><thead><tr><th>Cost centre</th><th>Entity</th><th class="n">{{ measure_label }}</th>{% if o.step == 'opex' %}<th class="n">Same periods last year</th><th class="n">Difference</th><th class="n">Adjusted · locked</th>{% else %}<th class="n">FTE</th><th class="n">On-costs</th>{% endif %}<th>State</th><th>By · since</th><th></th></tr></thead><tbody>
{% for r in rows %}<tr><td><a href="{{ url_for(o.entry, cc=r.code) }}">{{ r.name }}</a> <span class="small muted">{{ r.code }}</span></td><td class="small">{{ r.entities }}</td><td class="n">{{ r.plan|aud }}</td>
{% if o.step == 'opex' %}<td class="n">{{ r.prior|aud }}</td><td class="n {{ 'down' if r.diff and r.diff > 0 }}">{{ r.diff|aud }}</td><td class="n small">{{ r.adjusted }} · {{ r.locked }}</td>{% else %}<td class="n">{{ r.fte|n(1) }}</td><td class="n">{{ r.on_costs|aud }}</td>{% endif %}
<td><span class="state {{ r.state }}">{{ says[r.state] }}</span></td><td class="small muted">{{ r.acted_by or '' }}{% if r.acted_on %} · {{ r.acted_on }}{% endif %}</td>
<td>{% if may_review %}<a class="small" href="{{ url_for(review_ep, cc=r.code) }}">review</a>{% endif %}</td></tr>{% endfor %}
<tr class="total"><td colspan="2">{{ node_name }}</td><td class="n">{{ tot.plan|aud }}</td>{% if o.step == 'opex' %}<td class="n">{{ tot.prior|aud }}</td><td class="n">{{ tot.diff|aud }}</td><td></td>{% else %}<td class="n">{{ tot.fte|n(1) }}</td><td class="n">{{ tot.on_costs|aud }}</td>{% endif %}<td class="small">{{ n_in }} of {{ rows|length }} in</td><td></td><td></td></tr></tbody></table>
<p class="hint">{{ measure_says }} The state is the workflow's: who handed the cost centre over and when, or that it is still open. A cost centre is opened from its name; its review from the last column.</p>{% endif %}"""

REVIEW = """<h1>{{ o.title }} · review<small>{{ version }} · {{ node_name }} — the figures against last year, and what was entered since it was last handed over; nothing is typed here</small></h1>
{% if not leaf %}<p class="lede">Review is of one cost centre. Beneath {{ node_name }}:</p>
<table><thead><tr><th>Cost centre</th><th>State</th><th>By · since</th></tr></thead><tbody>{% for r in beneath %}<tr><td><a href="{{ url_for(review_ep, cc=r.code) }}">{{ r.name }}</a></td><td><span class="state {{ r.state }}">{{ says[r.state] }}</span></td><td class="small muted">{{ r.acted_by or '' }}{% if r.acted_on %} · {{ r.acted_on }}{% endif %}</td></tr>{% endfor %}</tbody></table>
{% else %}<div class="cards"><div class="card stat"><b>{{ says[st.state] if st else 'open' }}</b><span>{{ o.step }} at {{ node_name }}{% if st and st.acted_by %} · {{ st.acted_by }}, {{ st.acted_on }}{% endif %}{% if st and st.note %} — {{ st.note }}{% endif %}</span></div>
<div class="card stat"><b>{{ tot.plan|aud }}</b><span>{{ measure_label }}</span></div>{% if o.step == 'opex' %}<div class="card stat"><b>{{ tot.diff|aud }}</b><span>against the same periods last year ({{ tot.prior|aud }})</span></div>{% endif %}</div>
{% if may_decide %}<div class="form-row">{% for a in may_decide %}<form class="inline" method="post" action="{{ url_for('plan.workflow_act', via='finplan') }}"><input type="hidden" name="step" value="{{ o.step }}"><input type="hidden" name="node" value="{{ cc }}"><input type="hidden" name="act" value="{{ a }}"><input type="hidden" name="next" value="{{ request.full_path }}">{% if a == 'send_back' %}<input name="note" size="24" required placeholder="why it goes back">{% endif %}<button class="{{ 'primary' if a == 'accept' else 'act' }}">{{ a.replace('_', ' ') }}</button></form>{% endfor %}</div>{% endif %}
{% if o.step == 'opex' %}<h2>Lines<span class="count">the version's {{ n_periods }} planned periods against the same periods a year earlier</span></h2>
<table><thead><tr><th>Line</th><th>Entity</th><th>Driver</th><th class="n">Plan</th><th class="n">Last year</th><th class="n">Difference</th><th class="n">Adjusted · locked</th></tr></thead><tbody>
{% for l in lines %}<tr><td>{{ l.account_code }} {{ l.account_name }}</td><td class="small">{{ l.entity_code }}</td><td class="small">{{ l.driver_label }}</td><td class="n">{{ l.plan|aud }}</td><td class="n">{{ l.prior|aud }}</td><td class="n">{{ l.diff|aud }}</td><td class="n small">{{ l.adjusted }} · {{ l.locked }}</td></tr>{% endfor %}</tbody></table>
<p class="hint">{% if ref_has %}The reference version, {{ reference }}, carries its own opex schedule over its year — <a href="{{ url_for('plan.schedule', version=reference, cc=cc) }}">open it here</a>, read only; the figures above are read against the same periods a year earlier.{% else %}The reference version, {{ reference or 'none' }}, carries no opex schedule, so the figures are read against the same periods a year earlier.{% endif %}</p>{% endif %}
<h2>Entered since the last hand-over<span class="count">{{ since or 'nothing handed over yet' }} — every act on {{ node_name }}, newest first; those after the hand-over marked</span></h2>
<table><thead><tr><th>When</th><th>Act</th><th>By</th><th>Why</th><th>Standing</th></tr></thead><tbody>
{% for a in changes %}<tr class="{{ '' if a.after else 'off' }}"><td class="small">{{ (a.entered_on|string)[:16] }}</td><td class="small">{{ a.says }}</td><td class="small">{{ a.entered_by }}</td><td class="small">{{ a.reason or '' }}</td><td class="small">{{ a.standing }}{% if a.after %} · <b>since the hand-over</b>{% endif %}</td></tr>
{% else %}<tr><td colspan="5" class="muted">Nothing entered on {{ node_name }} on {{ version }}.</td></tr>{% endfor %}</tbody></table>{% endif %}"""


def register(bp, page, who_fn, ctx_fn, busy, session, roles) -> None:
    from . import reads

    def _where():
        c = ctx_fn()
        version = c.get("version") or reads.default_version()
        v = reads.version(version) or {}
        node, entity, here = costs.node_of(c)
        tree = {t["code"]: t for t in costs.planning_cost_centres()}
        return version, v, int(v.get("fiscal_year") or c.get("fy") or 0), node or "CAL", entity, here, tree

    def _states(version: str, step: str) -> dict:
        return {r["node"]: r for r in q("select * from plan.step_state where version_id = ? and step = ?", version, step)}

    def _opex(version: str, entity: str, here: set) -> dict:
        """Per line of the schedule within the node: the plan over its planned periods, the same periods a year earlier."""
        rows = q("select * from plan.opex_schedule where version_id = ?", version)
        prior = {r["period"]: r["prior_year_period"] for r in q("select period, prior_year_period from dims.dim_period")}
        act = defaultdict(float)
        for r in q("select entity_code, cost_centre_code, account_code, period, sum(amount) a from plan.cost_actual where state = 'mapped' group by all"):
            act[(r["entity_code"], r["cost_centre_code"], r["account_code"], r["period"])] = r["a"]
        out: dict = {}
        for r in rows:
            if r["cost_centre_code"] not in here or (entity and r["entity_code"] != entity):
                continue
            k = (r["entity_code"], r["cost_centre_code"], r["account_code"])
            l = out.setdefault(k, {"entity_code": k[0], "cost_centre_code": k[1], "account_code": k[2], "driver": r["driver"], "plan": 0.0, "prior": 0.0,
                                   "adjusted": 0, "locked": 0, "periods": 0})
            l["plan"] += r["amount"] or 0
            l["prior"] += act.get((*k, prior.get(r["period"])), 0.0)
            l["adjusted"] += r["state"] == "adjusted"; l["locked"] += r["state"] == "locked"; l["periods"] += 1
        return out

    def _withheld(who: str) -> tuple[set, set]:
        _, named = costs.pay_withheld(roles, who)
        return set(named), {r["account_code"] for r in q("select account_code from dims.dim_gl_account where is_labour")}

    @bp.get("/schedule/compare")
    def schedule_compare():
        return _compare("schedule")

    @bp.get("/headcount/compare")
    def headcount_compare():
        return _compare("headcount")

    def _compare(obj: str):
        o = OBJECTS[obj]
        try:
            who = who_fn(); version, v, fy, node, entity, here, tree = _where()
            st = _states(version, o["step"])
            leaves = [c for c in tree.values() if c["code"] in here and c["kind"] not in ("company", "function")]
            rows = []
            if obj == "schedule":
                named, labour = _withheld(who)
                lines = _opex(version, entity, here)
                for c in leaves:
                    mine = [l for k, l in lines.items() if k[1] == c["code"] and not (k[1] in named and k[2] in labour)]
                    if not mine:
                        continue
                    p, pr = sum(l["plan"] for l in mine), sum(l["prior"] for l in mine)
                    rows.append({"code": c["code"], "name": c["name"], "entities": ", ".join(sorted({l["entity_code"] for l in mine})), "plan": p, "prior": pr,
                                 "diff": p - pr, "adjusted": sum(l["adjusted"] for l in mine), "locked": sum(l["locked"] for l in mine)})
                label, says = "Plan, its planned periods", "Plan is the schedule's planned periods; last year the same periods' actuals through the mapping."
            else:
                for r in q("""select cost_centre_code, string_agg(distinct entity_code, ', ') entities, sum(wages) wages, sum(on_costs) on_costs,
                                     sum(fte * 1.0) / greatest(count(distinct period), 1) fte from plan.labour_line
                              where version_id = ? and fiscal_year = ? and (? = '' or entity_code = ?) and (model = 'role' or ?) group by 1""",
                              version, fy, entity, entity, roles.may(who, costs.PAY_VERB)):
                    if r["cost_centre_code"] in here:
                        c = tree.get(r["cost_centre_code"], {"name": r["cost_centre_code"]})
                        rows.append({"code": r["cost_centre_code"], "name": c["name"], "entities": r["entities"], "plan": r["wages"], "on_costs": r["on_costs"], "fte": r["fte"]})
                label, says = f"FY{fy} wages", "Wages and on-costs are the labour model's for the year's planned periods; FTE the average over them. Individual pay is left out for those without the right to read it."
            for r in rows:
                s = st.get(r["code"]) or {}
                r.update(state=s.get("state") or "open", acted_by=s.get("acted_by"), acted_on=s.get("acted_on"))
            order = list(tree)
            rows.sort(key=lambda r: order.index(r["code"]) if r["code"] in order else 999)
            tot = {k: sum((r.get(k) or 0) for r in rows) for k in ("plan", "prior", "diff", "fte", "on_costs")}
            return page(COMPARE, title=f"{o['title']} · compare", active=f"{o['tab']}_compare", width="none", o=o, version=version, fy=fy,
                        node_name=tree.get(node, {}).get("name", node), rows=rows if len(leaves) > 1 or node not in {c["code"] for c in leaves} else [],
                        tot=tot, says=STATE_SAYS, n_in=sum(1 for r in rows if r["state"] in ("submitted", "accepted")), measure_label=label, measure_says=says,
                        may_review=roles.may(who, f"review.{o['step']}.close"), review_ep=f"plan.{obj}_review")
        except Busy as e:
            return busy(f"{o['title']} · compare", e)

    @bp.get("/schedule/review")
    def schedule_review():
        return _review("schedule")

    @bp.get("/headcount/review")
    def headcount_review():
        return _review("headcount")

    def _review(obj: str):
        o = OBJECTS[obj]
        try:
            who = who_fn(); version, v, fy, node, entity, here, tree = _where()
            st = _states(version, o["step"])
            leaf = node in tree and tree[node]["kind"] not in ("company", "function")
            ctx = {"o": o, "version": version, "node_name": tree.get(node, {}).get("name", node), "says": STATE_SAYS, "leaf": leaf, "cc": node,
                   "review_ep": f"plan.{obj}_review", "acts": []}
            if not leaf:
                ctx["beneath"] = [{"code": c["code"], "name": c["name"], **{k: (st.get(c["code"]) or {}).get(k) for k in ("acted_by", "acted_on")},
                                   "state": (st.get(c["code"]) or {}).get("state") or "open"}
                                  for c in tree.values() if c["code"] in here and c["kind"] not in ("company", "function") and (st.get(c["code"]) or {}).get("has_figures")]
                return page(REVIEW, title=f"{o['title']} · review", active=f"{o['tab']}_review", **ctx)
            s = st.get(node)
            from .workflow import ACTS
            decide = f"review.{o['step']}.close"
            ctx["may_decide"] = [a for a in ("accept", "send_back") if s and s["state"] in ACTS[a][1] and v.get("status") == "open"
                                 and roles.may(who, decide, node, dimension="organisation", kind=v.get("version_kind"))]
            ctx["st"] = s
            since = str(s["acted_on"]) if s and s.get("acted_on") and s["state"] in ("submitted", "accepted", "sent_back") else None
            labels = {d["driver"]: d["driver_label"] for d in q("select * from dims.ref_cost_driver")} | {"labour_model": "the labour model", "capex_model": "the capital plan"}
            accounts = {a["account_code"]: a["account_name"] for a in q("select account_code, account_name from dims.dim_gl_account")}
            if obj == "schedule":
                named, labour = _withheld(who)
                lines = [l for k, l in _opex(version, entity, {node}).items() if not (k[1] in named and k[2] in labour)]
                for l in lines:
                    l.update(account_name=accounts.get(l["account_code"], ""), driver_label=labels.get(l["driver"], l["driver"]), diff=l["plan"] - l["prior"])
                lines.sort(key=lambda l: (l["account_code"], l["entity_code"]))
                ctx.update(lines=lines, n_periods=max((l["periods"] for l in lines), default=0),
                           tot={"plan": sum(l["plan"] for l in lines), "prior": sum(l["prior"] for l in lines), "diff": sum(l["diff"] for l in lines)},
                           reference=v.get("reference_version"),
                           ref_has=bool(q("select 1 ok from plan.opex_schedule where version_id = ? limit 1", v.get("reference_version") or "")))
                changes = q("""select r.acted_at entered_on, r.what says, r.by_whom entered_by, r.why reason, r.standing from plan.change_record r
                               join plan.schedule_edit e on e.edit_id = r.act_id
                               where r.record = 'opex schedule' and r.version_id = ? and e.cost_centre_code = ? order by r.acted_at desc""", version, node)
            else:
                tot = q("select sum(wages) w from plan.labour_line where version_id = ? and fiscal_year = ? and cost_centre_code = ? and (model = 'role' or ?)",
                        version, fy, node, roles.may(who, costs.PAY_VERB))
                ctx.update(tot={"plan": (tot[0]["w"] if tot else 0) or 0}, lines=[])
                changes = []                  # headcount is read here, not entered yet: nothing to have changed
            ctx["measure_label"] = "plan over the planned periods" if obj == "schedule" else f"FY{fy} wages"
            for a in changes:
                a["after"] = bool(since) and str(a["entered_on"])[:10] >= since
            ctx.update(changes=changes, since=f"handed over {since}" if since else None)
            return page(REVIEW, title=f"{o['title']} · review", active=f"{o['tab']}_review", width="none", **ctx)
        except Busy as e:
            return busy(f"{o['title']} · review", e)
