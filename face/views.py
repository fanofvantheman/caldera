"""The other two views of a cost-side object (DEC-20261115-02 points 4–5): the **compare** view — the cost centres beneath
the context's node side by side, each with its step's state, for the process owner — and the **review** view — one cost
centre's figures against the reference and against last year, side by side (DEC-20261115-07), and what was entered since it was last handed over, by whom and why, with accept
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

FLAG_CSS = "<style>td.over{font-weight:600}td.over::before{content:\"▲ \";font-size:.7em}th .sub{display:block;font-weight:400;font-size:.72rem;color:var(--muted)}</style>"

COMPARE = FLAG_CSS + """<h1>{{ o.title }} · compare<small>{{ version|plan }} · FY{{ fy }} · {{ node_name }} — the cost centres beneath side by side, each with its {{ o.step }} state</small></h1>
{% if not rows %}<p class="lede">{{ node_name }} is one cost centre: there is nothing beneath it to compare — the entry and review views show it.</p>{% else %}
<table><thead><tr><th>Cost centre</th><th>Entity</th><th class="n">{{ measure_label }}</th>{% if o.step == 'opex' %}<th class="n">Same periods last year</th><th class="n">Difference</th>{% else %}<th class="n">FTE</th><th class="n">On-costs</th>{% endif %}
{% if reference %}<th class="n">{{ reference }}{% if o.step == 'labour' %} wages and on-costs{% endif %}<span class="sub">{{ ref_n }} of {{ n_all }} periods</span></th><th class="n">Difference<span class="sub">over the same periods</span></th>{% if o.step == 'labour' %}<th class="n">{{ reference }} FTE</th>{% endif %}{% endif %}
{% if o.step == 'opex' %}<th class="n">Adjusted · locked</th>{% endif %}<th>State</th><th>By · since</th><th></th></tr></thead><tbody>
{% for r in rows %}<tr><td><a href="{{ url_for(o.entry, cc=r.code) }}">{{ r.name }}</a> <span class="small muted">{{ r.code }}</span></td><td class="small">{{ r.entities }}</td><td class="n">{{ r.plan|aud }}</td>
{% if o.step == 'opex' %}<td class="n">{{ r.prior|aud }}</td><td class="n {{ 'over' if r.flag and r.ref_diff is none }}">{{ r.diff|aud }}</td>{% else %}<td class="n">{{ r.fte|n(1) }}</td><td class="n">{{ r.on_costs|aud }}</td>{% endif %}
{% if reference %}<td class="n">{{ r.ref|aud }}</td><td class="n {{ 'over' if r.flag and r.ref_diff is not none }}">{{ r.ref_diff|aud }}</td>{% if o.step == 'labour' %}<td class="n">{{ r.ref_fte|n(1) if r.ref_fte is not none else '' }}</td>{% endif %}{% endif %}
{% if o.step == 'opex' %}<td class="n small">{{ r.adjusted }} · {{ r.locked }}</td>{% endif %}
<td><span class="state {{ r.state }}">{{ says[r.state] }}</span></td><td class="small muted">{{ r.acted_by or '' }}{% if r.acted_on %} · {{ r.acted_on }}{% endif %}</td>
<td>{% if may_review %}<a class="small" href="{{ url_for(review_ep, cc=r.code) }}">review</a>{% endif %}</td></tr>{% endfor %}
<tr class="total"><td colspan="2">{{ node_name }}</td><td class="n">{{ tot.plan|aud }}</td>{% if o.step == 'opex' %}<td class="n">{{ tot.prior|aud }}</td><td class="n">{{ tot.diff|aud }}</td>{% else %}<td class="n">{{ tot.fte|n(1) }}</td><td class="n">{{ tot.on_costs|aud }}</td>{% endif %}
{% if reference %}<td class="n">{{ tot.ref|aud }}</td><td class="n">{{ tot.ref_diff|aud }}</td>{% if o.step == 'labour' %}<td class="n">{{ tot.ref_fte|n(1) if tot.ref_fte is not none else '' }}</td>{% endif %}{% endif %}
{% if o.step == 'opex' %}<td></td>{% endif %}<td class="small">{{ n_in }} of {{ rows|length }} in</td><td></td><td></td></tr></tbody></table>
<p class="hint">{{ measure_says }}{% if reference %} {{ reference }} is the reference: its own figures for the same {{ 'lines' if o.step == 'opex' else 'cost centres' }}, period for period, over the {{ ref_n }} of {{ n_all }} periods it covers — a period it does not cover is left out, not filled; its difference is the plan less the reference over those periods.{% if o.step == 'opex' %} ▲ marks a plan above the reference where the reference covers it, above last year where it does not.{% else %} ▲ marks a plan above the reference.{% endif %}{% elif o.step == 'opex' %} ▲ marks a plan above last year.{% endif %} The state is the workflow's: who handed the cost centre over and when, or that it is still open. A cost centre is opened from its name; its review from the last column.</p>{% endif %}"""

REVIEW = FLAG_CSS + """<h1>{{ o.title }} · review<small>{{ version|plan }} · {{ node_name }} — {% if o.step == 'opex' %}the figures against {% if reference %}the reference, {{ reference }}, and {% endif %}last year{% elif reference %}the figures against the reference, {{ reference }}{% else %}the figures by period{% endif %}, and what was entered since it was last handed over; nothing is typed here</small></h1>
{% if not leaf %}<p class="lede">Review is of one cost centre. Beneath {{ node_name }}:</p>
<table><thead><tr><th>Cost centre</th><th>State</th><th>By · since</th></tr></thead><tbody>{% for r in beneath %}<tr><td><a href="{{ url_for(review_ep, cc=r.code) }}">{{ r.name }}</a></td><td><span class="state {{ r.state }}">{{ says[r.state] }}</span></td><td class="small muted">{{ r.acted_by or '' }}{% if r.acted_on %} · {{ r.acted_on }}{% endif %}</td></tr>{% endfor %}</tbody></table>
{% else %}<div class="cards"><div class="card stat"><b>{{ says[st.state] if st else 'open' }}</b><span>{{ o.step }} at {{ node_name }}{% if st and st.acted_by %} · {{ st.acted_by }}, {{ st.acted_on }}{% endif %}{% if st and st.note %} — {{ st.note }}{% endif %}</span></div>
<div class="card stat"><b>{{ tot.plan|aud }}</b><span>{{ measure_label }}</span></div>{% if reference and tot.ref is not none %}<div class="card stat"><b>{{ tot.ref_diff|aud }}</b><span>against {{ reference }} ({{ tot.ref|aud }}{% if o.step == 'labour' %} wages and on-costs{% endif %}) over the {{ tot.ref_n }} of {{ tot.n }} periods it covers</span></div>{% endif %}{% if o.step == 'opex' %}<div class="card stat"><b>{{ tot.diff|aud }}</b><span>against the same periods last year ({{ tot.prior|aud }})</span></div>{% endif %}</div>
{% if may_decide %}<div class="form-row">{% for a in may_decide %}<form class="inline" method="post" action="{{ url_for('plan.workflow_act', via='finplan') }}"><input type="hidden" name="step" value="{{ o.step }}"><input type="hidden" name="node" value="{{ cc }}"><input type="hidden" name="act" value="{{ a }}"><input type="hidden" name="next" value="{{ request.full_path }}">{% if a == 'send_back' %}<input name="note" size="24" required placeholder="why it goes back">{% endif %}<button class="{{ 'primary' if a == 'accept' else 'act' }}">{{ a.replace('_', ' ') }}</button></form>{% endfor %}</div>{% endif %}
{% if o.step == 'opex' %}<h2>Lines<span class="count">the version's {{ n_periods }} planned periods against {% if reference %}{{ reference }} over the periods it covers and {% endif %}the same periods a year earlier</span></h2>
<table><thead><tr><th>Line</th><th>Entity</th><th>Driver</th><th class="n">Plan</th>{% if reference %}<th class="n">{{ reference }}<span class="sub">periods covered</span></th><th class="n">Difference<span class="sub">over the same periods</span></th>{% endif %}<th class="n">Last year</th><th class="n">Difference</th><th class="n">Adjusted · locked</th></tr></thead><tbody>
{% for l in lines %}<tr><td>{{ l.account_code }} {{ l.account_name }}</td><td class="small">{{ l.entity_code }}</td><td class="small">{{ l.driver_label }}</td><td class="n">{{ l.plan|aud }}</td>{% if reference %}<td class="n">{{ l.ref|aud }}{% if l.ref is not none and l.ref_n < l.periods %} <span class="small muted">{{ l.ref_n }} of {{ l.periods }}</span>{% endif %}</td><td class="n {{ 'over' if l.flag and l.ref_diff is not none }}">{{ l.ref_diff|aud }}</td>{% endif %}<td class="n">{{ l.prior|aud }}</td><td class="n {{ 'over' if l.flag and l.ref_diff is none }}">{{ l.diff|aud }}</td><td class="n small">{{ l.adjusted }} · {{ l.locked }}</td></tr>{% endfor %}
<tr class="total"><td colspan="3">{{ node_name }}</td><td class="n">{{ tot.plan|aud }}</td>{% if reference %}<td class="n">{{ tot.ref|aud }} <span class="small muted">{{ tot.ref_n }} of {{ tot.n }} periods</span></td><td class="n">{{ tot.ref_diff|aud }}</td>{% endif %}<td class="n">{{ tot.prior|aud }}</td><td class="n">{{ tot.diff|aud }}</td><td></td></tr></tbody></table>
{% endif %}
{% if by_period %}<h2>By period<span class="count">{% if reference %}each planned period against {{ reference }} where it covers the period{{ ', and the same period last year' if o.step == 'opex' }}{% else %}{{ 'each planned period against the same period last year' if o.step == 'opex' else 'each planned period' }}{% endif %}</span></h2>
<table><thead><tr><th>Period</th>{% if o.step == 'labour' %}<th class="n">FTE</th>{% endif %}<th class="n">{{ 'Plan' if o.step == 'opex' else 'Wages and on-costs' }}</th>{% if reference %}{% if o.step == 'labour' %}<th class="n">{{ reference }} FTE</th>{% endif %}<th class="n">{{ reference }}</th><th class="n">Difference</th>{% endif %}{% if o.step == 'opex' %}<th class="n">Last year</th><th class="n">Difference</th>{% endif %}</tr></thead><tbody>
{% for p, b in by_period.items() %}<tr><td>{{ p }}</td>{% if o.step == 'labour' %}<td class="n">{{ b.fte|n(1) }}</td>{% endif %}<td class="n">{{ b.plan|aud }}</td>{% if reference %}{% if o.step == 'labour' %}<td class="n">{{ b.ref_fte|n(1) if b.ref_fte is not none else '' }}</td>{% endif %}<td class="n">{{ b.ref|aud }}</td><td class="n">{{ (b.plan - b.ref)|aud if b.ref is not none else '' }}</td>{% endif %}{% if o.step == 'opex' %}<td class="n">{{ b.prior|aud }}</td><td class="n">{{ (b.plan - b.prior)|aud }}</td>{% endif %}</tr>{% endfor %}
<tr class="total"><td>{{ tot.n }} periods</td>{% if o.step == 'labour' %}<td></td>{% endif %}<td class="n">{{ tot.plan_all|aud if o.step == 'labour' else tot.plan|aud }}</td>{% if reference %}{% if o.step == 'labour' %}<td></td>{% endif %}<td class="n">{{ tot.ref|aud }} <span class="small muted">{{ tot.ref_n }} of {{ tot.n }}</span></td><td class="n">{{ tot.ref_diff|aud }}</td>{% endif %}{% if o.step == 'opex' %}<td class="n">{{ tot.prior|aud }}</td><td class="n">{{ tot.diff|aud }}</td>{% endif %}</tr></tbody></table>
<p class="hint">{% if reference %}{{ reference }} is the reference: its own {{ 'schedule' if o.step == 'opex' else 'labour' }} for this cost centre, period for period. A period it does not cover is empty and left out of its total, never filled from last year; the difference is the plan less the reference over the periods it covers. {% if o.step == 'opex' %}▲ marks a line above the reference where the reference covers it, above last year where it does not.{% endif %}{% elif o.step == 'opex' %}{{ version|plan }} is read against the same periods last year. ▲ marks a line above it.{% endif %}</p>{% endif %}
<h2>Entered since the last hand-over<span class="count">{{ since or 'nothing handed over yet' }} — every act on {{ node_name }}, newest first; those after the hand-over marked</span></h2>
<table><thead><tr><th>When</th><th>Act</th><th>By</th><th>Why</th><th>Standing</th></tr></thead><tbody>
{% for a in changes %}<tr class="{{ '' if a.after else 'off' }}"><td class="small">{{ (a.entered_on|string)[:16] }}</td><td class="small">{{ a.says }}</td><td class="small">{{ a.entered_by }}</td><td class="small">{{ a.reason or '' }}</td><td class="small">{{ a.standing }}{% if a.after %} · <b>since the hand-over</b>{% endif %}</td></tr>
{% else %}<tr><td colspan="5" class="muted">Nothing entered on {{ node_name }} on {{ version|plan }}.</td></tr>{% endfor %}</tbody></table>{% endif %}"""


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

    def _ref(v: dict, version: str, table: str) -> str | None:
        """The plan's reference version where there is one to read against (DEC-20261115-07 point 5): not itself, and
        carrying the object's own figures."""
        ref = v.get("reference_version")
        if not ref or ref == version:
            return None
        return ref if q(f"select 1 ok from plan.{table} where version_id = ? limit 1", ref) else None

    def _opex(version: str, entity: str, here: set, ref: str | None = None) -> dict:
        """Per line of the schedule within the node: the plan over its planned periods, the same periods a year earlier,
        and — period for period — the reference's own figure for the same line where its schedule has one (ambiguity
        #51 b): a period it does not cover is None, never filled from the other."""
        rows = q("select * from plan.opex_schedule where version_id = ?", version)
        prior = {r["period"]: r["prior_year_period"] for r in q("select period, prior_year_period from dims.dim_period")}
        act = defaultdict(float)
        for r in q("select entity_code, cost_centre_code, account_code, period, sum(amount) a from plan.cost_actual where state = 'mapped' and coalesce(cost_family, '') <> 'material' group by all"):
            act[(r["entity_code"], r["cost_centre_code"], r["account_code"], r["period"])] = r["a"]
        refd = {(r["entity_code"], r["cost_centre_code"], r["account_code"], r["period"]): r["a"] or 0.0
                for r in (q("select entity_code, cost_centre_code, account_code, period, sum(amount) a from plan.opex_schedule where version_id = ? group by all", ref)
                          if ref else [])}
        out: dict = {}
        for r in rows:
            if r["cost_centre_code"] not in here or (entity and r["entity_code"] != entity):
                continue
            k = (r["entity_code"], r["cost_centre_code"], r["account_code"])
            l = out.setdefault(k, {"entity_code": k[0], "cost_centre_code": k[1], "account_code": k[2], "driver": r["driver"], "plan": 0.0, "prior": 0.0,
                                   "ref": None, "plan_cov": 0.0, "ref_n": 0, "adjusted": 0, "locked": 0, "periods": 0, "by": {}})
            a, pr, rf = r["amount"] or 0, act.get((*k, prior.get(r["period"])), 0.0), refd.get((*k, r["period"]))
            l["plan"] += a; l["prior"] += pr
            if rf is not None:
                l["ref"] = (l["ref"] or 0.0) + rf; l["plan_cov"] += a; l["ref_n"] += 1
            b = l["by"].setdefault(r["period"], {"plan": 0.0, "prior": 0.0, "ref": None})
            b["plan"] += a; b["prior"] += pr
            if rf is not None:
                b["ref"] = (b["ref"] or 0.0) + rf
            l["adjusted"] += r["state"] == "adjusted"; l["locked"] += r["state"] == "locked"; l["periods"] += 1
        return out

    def _sum(lines: list) -> dict:
        """Lines summed: the plan and last year over every period; the reference only over the periods it covers, with
        the plan over the same periods beside it, and how many of the periods it compares (DEC-20261115-07 point 2)."""
        by: dict = {}
        for l in lines:
            for p, b in l["by"].items():
                t = by.setdefault(p, {"plan": 0.0, "prior": 0.0, "ref": None})
                t["plan"] += b["plan"]; t["prior"] += b["prior"]
                if b["ref"] is not None:
                    t["ref"] = (t["ref"] or 0.0) + b["ref"]
        cov = [b for b in by.values() if b["ref"] is not None]
        plan, prior = sum(b["plan"] for b in by.values()), sum(b["prior"] for b in by.values())
        ref = sum(b["ref"] for b in cov) if cov else None
        pc = sum(b["plan"] for b in cov)
        return {"plan": plan, "prior": prior, "diff": plan - prior, "ref": ref, "ref_diff": (pc - ref) if cov else None,
                "ref_n": len(cov), "n": len(by), "by": dict(sorted(by.items()))}

    def _flag(r: dict) -> bool:
        """The reviewer's mark: the plan above its comparison — the reference where it covers the line, else last year."""
        d = r["ref_diff"] if r.get("ref_diff") is not None else r.get("diff")
        return bool(d and d > 0.5)

    def _labour(version: str, fy: int, entity: str, may_pay: bool, periods: set | None = None) -> dict:
        """Per cost centre and period: wages, on-costs and FTE from the labour model, a pure read of `plan.labour_line`."""
        out: dict = defaultdict(dict)
        for r in q("""select cost_centre_code, period, string_agg(distinct entity_code, ', ') entities, sum(wages) wages, sum(on_costs) on_costs, sum(fte * 1.0) fte
                      from plan.labour_line where version_id = ? and (? = 0 or fiscal_year = ?) and (? = '' or entity_code = ?) and (model = 'role' or ?) group by 1, 2""",
                   version, fy if periods is None else 0, fy, entity, entity, may_pay):
            if periods is None or r["period"] in periods:
                out[r["cost_centre_code"]][r["period"]] = r
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
                ref = _ref(v, version, "opex_schedule")
                lines = _opex(version, entity, here, ref)
                for c in leaves:
                    mine = [l for k, l in lines.items() if k[1] == c["code"] and not (k[1] in named and k[2] in labour)]
                    if not mine:
                        continue
                    t = _sum(mine)
                    rows.append({"code": c["code"], "name": c["name"], "entities": ", ".join(sorted({l["entity_code"] for l in mine})), **{k: t[k] for k in ("plan", "prior", "diff", "ref", "ref_diff", "ref_n", "n")},
                                 "adjusted": sum(l["adjusted"] for l in mine), "locked": sum(l["locked"] for l in mine)})
                label, says = "Plan, its planned periods", "Plan is the schedule's planned periods; last year the same periods' actuals through the mapping."
                n_all = max((r["n"] for r in rows), default=0)
                ref_n = len({p for k, l in lines.items() if k[1] in {r["code"] for r in rows} for p, b in l["by"].items() if b["ref"] is not None})
            else:
                may_pay = roles.may(who, costs.PAY_VERB)
                ref = _ref(v, version, "labour_line")
                mine = _labour(version, fy, entity, may_pay)
                theirs = _labour(ref, fy, entity, may_pay, {p for per in mine.values() for p in per}) if ref else {}
                for cc, per in mine.items():
                    if cc not in here:
                        continue
                    c = tree.get(cc, {"name": cc})
                    n = max(len(per), 1)
                    rf = {p: x for p, x in theirs.get(cc, {}).items() if p in per}
                    r = {"code": cc, "name": c["name"], "entities": ", ".join(sorted({e for x in per.values() for e in (x["entities"] or "").split(", ") if e})),
                         "plan": sum(x["wages"] or 0 for x in per.values()), "on_costs": sum(x["on_costs"] or 0 for x in per.values()),
                         "fte": sum(x["fte"] or 0 for x in per.values()) / n, "n": len(per), "ref_n": len(rf), "ref": None, "ref_fte": None, "ref_diff": None}
                    if rf:
                        loaded = sum((per[p]["wages"] or 0) + (per[p]["on_costs"] or 0) for p in rf)
                        r["ref"] = sum((x["wages"] or 0) + (x["on_costs"] or 0) for x in rf.values())
                        r["ref_diff"] = loaded - r["ref"]
                        r["ref_fte"] = sum(x["fte"] or 0 for x in rf.values()) / len(rf)
                        r["fte_diff"] = sum(per[p]["fte"] or 0 for p in rf) / len(rf) - r["ref_fte"]
                    rows.append(r)
                label, says = f"FY{fy} wages", "Wages and on-costs are the labour model's for the year's planned periods; FTE the average over them. Individual pay is left out for those without the right to read it."
                n_all = max((r["n"] for r in rows), default=0)
                ref_n = len({p for cc, per in theirs.items() if cc in {r["code"] for r in rows} for p in per})
            for r in rows:
                r["flag"] = _flag(r)
            for r in rows:
                s = st.get(r["code"]) or {}
                r.update(state=s.get("state") or "open", acted_by=s.get("acted_by"), acted_on=s.get("acted_on"))
            order = list(tree)
            rows.sort(key=lambda r: order.index(r["code"]) if r["code"] in order else 999)
            tot = {k: sum((r.get(k) or 0) for r in rows) for k in ("plan", "prior", "diff", "fte", "on_costs")}
            cov = [r for r in rows if r.get("ref") is not None]
            tot.update(ref=sum(r["ref"] for r in cov) if cov else None, ref_diff=sum(r["ref_diff"] for r in cov) if cov else None,
                       ref_fte=sum(r["ref_fte"] for r in cov) if cov and obj == "headcount" else None)
            return page(COMPARE, title=f"{o['title']} · compare", active=f"{o['tab']}_compare", width="none", o=o, version=version, fy=fy,
                        node_name=tree.get(node, {}).get("name", node), rows=rows if len(leaves) > 1 or node not in {c["code"] for c in leaves} else [],
                        tot=tot, says=STATE_SAYS, n_in=sum(1 for r in rows if r["state"] in ("submitted", "accepted")), measure_label=label, measure_says=says,
                        may_review=roles.may(who, f"review.{o['step']}.close"), review_ep=f"plan.{obj}_review",
                        reference=ref, ref_n=ref_n, n_all=n_all)
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
                   "review_ep": f"plan.{obj}_review", "acts": [], "reference": None, "by_period": None}
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
                ref = _ref(v, version, "opex_schedule")
                lines = [l for k, l in _opex(version, entity, {node}, ref).items() if not (k[1] in named and k[2] in labour)]
                for l in lines:
                    l.update(account_name=accounts.get(l["account_code"], ""), driver_label=labels.get(l["driver"], l["driver"]), diff=l["plan"] - l["prior"],
                             ref_diff=(l["plan_cov"] - l["ref"]) if l["ref"] is not None else None)
                    l["flag"] = _flag(l)
                lines.sort(key=lambda l: (l["account_code"], l["entity_code"]))
                tot = _sum(lines)
                ctx.update(lines=lines, n_periods=max((l["periods"] for l in lines), default=0), tot=tot, by_period=tot["by"], reference=ref)
                changes = q("""select r.acted_at entered_on, r.what says, r.by_whom entered_by, r.why reason, r.standing from plan.change_record r
                               join plan.schedule_edit e on e.edit_id = r.act_id
                               where r.record = 'opex schedule' and r.version_id = ? and e.cost_centre_code = ? order by r.acted_at desc""", version, node)
            else:
                may_pay = roles.may(who, costs.PAY_VERB)
                ref = _ref(v, version, "labour_line")
                per = _labour(version, fy, entity, may_pay).get(node, {})
                theirs = (_labour(ref, fy, entity, may_pay, set(per)).get(node, {}) if ref else {})
                by = {p: {"plan": (x["wages"] or 0) + (x["on_costs"] or 0), "fte": x["fte"] or 0,
                          "ref": ((theirs[p]["wages"] or 0) + (theirs[p]["on_costs"] or 0)) if p in theirs else None,
                          "ref_fte": (theirs[p]["fte"] or 0) if p in theirs else None} for p, x in sorted(per.items())}
                cov = [b for b in by.values() if b["ref"] is not None]
                ctx.update(tot={"plan": sum(x["wages"] or 0 for x in per.values()), "plan_all": sum(b["plan"] for b in by.values()), "n": len(by), "ref_n": len(cov),
                                "ref": sum(b["ref"] for b in cov) if cov else None, "ref_diff": sum(b["plan"] - b["ref"] for b in cov) if cov else None},
                           lines=[], by_period=by, reference=ref)
                changes = []                  # headcount is read here, not entered yet: nothing to have changed
            ctx["measure_label"] = "plan over the planned periods" if obj == "schedule" else f"FY{fy} wages"
            for a in changes:
                a["after"] = bool(since) and str(a["entered_on"])[:10] >= since
            ctx.update(changes=changes, since=f"handed over {since}" if since else None)
            return page(REVIEW, title=f"{o['title']} · review", active=f"{o['tab']}_review", width="none", **ctx)
        except Busy as e:
            return busy(f"{o['title']} · review", e)
