"""Headcount, two ways (DEC-20261113-02): by role in the factory cost centres — positions priced through the agreement, a
name beside a position carrying nothing — and by name in the overhead ones — each person's own terms, which is individual
pay and read under its own verb (`read.pay`). Both land on the opex schedule's labour lines through plan.labour_cost.

Read here; the positions, people and agreements are registers (entering headcount is not built). Registered on the
plan's blueprint by `register(...)`, called once from `face/__main__.py`."""
from __future__ import annotations

from collections import defaultdict

from chassis.warehouse import Busy, q
from flask import request

from . import costs
from .words import said

ROLE = """<h1>Headcount by role<small>FY{{ fy }} · {{ version }} · the factory cost centres — positions priced through each entity's agreement; a change of person moves nothing</small></h1>
{% if plan_in_fy %}<p class="hint">FY{{ fy }} here is {{ version }}'s plan periods in the year, {{ plan_in_fy[0] }} to {{ plan_in_fy[-1] }}{% if upto %}: the periods to {{ upto }} are actual for this version and are not planned — what was paid in them is in the <a href="{{ url_for('plan.cost_actuals') }}">ledgers' actuals</a>{% endif %}.</p>{% endif %}
<p class="hint">FTE are positions at 38 paid hours a week; the casual pool is a position for the campaign periods at a 25% loading. Wages land on the schedule's 6100 line and the employer's on-costs on 6150, for every period of the schedule. Penalties, allowances and leave are not yet planned.</p>
{% for g in groups %}<h2>{{ g.name }}<span class="count">{{ g.code }} · {{ g.entity }}</span></h2>
<table><thead><tr><th>Position</th><th>Classification</th><th>Employment</th><th class="n">FTE</th><th class="n">Rate now</th><th class="n">From {{ step }}</th><th class="n">FY{{ fy }} wages</th><th class="n">On-costs</th></tr></thead><tbody>
{% for r in g.rows %}<tr><td><code>{{ r.position_id }}</code>{% if r.shown_name %} <span class="small muted">{{ r.shown_name }}</span>{% endif %}</td><td>{{ r.classification_name }}</td><td class="small">{{ r.employment_type }}{% if r.to_period %} · {{ r.from_period }}–{{ r.to_period }}{% endif %}</td>
<td class="n">{{ r.fte|n(1) }}</td><td class="n">{{ '%.2f'|format(r.rate_now) if r.rate_now else '' }}</td><td class="n">{{ '%.2f'|format(r.rate_step) if r.rate_step else '' }}</td><td class="n">{{ r.wages|aud }}</td><td class="n">{{ r.on_costs|aud }}</td></tr>{% endfor %}
<tr class="total"><td colspan="3">{{ g.name }}</td><td class="n">{{ g.fte|n(1) }}</td><td></td><td></td><td class="n">{{ g.wages|aud }}</td><td class="n">{{ g.on_costs|aud }}</td></tr></tbody></table>{% endfor %}
<h2>The agreements<span class="count">classification × hourly rate, effective from a period</span></h2>
<table><thead><tr><th>Agreement</th><th>Classification</th>{% for p in agreement_periods %}<th class="n">from {{ p }}</th>{% endfor %}</tr></thead><tbody>
{% for a in agreements %}<tr><td class="small">{{ a.agreement_name }} <span class="muted">{{ a.entity_code }}</span></td><td>{{ a.classification_name }}</td>{% for p in agreement_periods %}<td class="n">{{ '%.2f'|format(a.rates[p]) if a.rates.get(p) else '' }}</td>{% endfor %}</tr>{% endfor %}</tbody></table>"""

NAME = """<h1>Headcount by name<small>FY{{ fy }} · {{ version }} · the overhead cost centres — each person's own terms; nothing accrues to a role</small></h1>
{% if plan_in_fy %}<p class="hint">FY{{ fy }} here is {{ version }}'s plan periods in the year, {{ plan_in_fy[0] }} to {{ plan_in_fy[-1] }}{% if upto %}: the periods to {{ upto }} are actual for this version and are not planned — what was paid in them is in the <a href="{{ url_for('plan.cost_actuals') }}">ledgers' actuals</a>{% endif %}.</p>{% endif %}
{% if not may %}<p class="lede">This is individual pay. It is read by {{ pay_holders|join(', ') or 'nobody yet' }} — not by the cost centre's owner — and {{ viewer }} does not hold it.</p>
{% else %}<p class="hint">Individual pay, read by the holders of {{ pay_said }}. Salary × (1 + the incentive at target) for the weeks each person is employed in a period; a named vacancy is planned at a typed figure from its start; the employer's on-costs at the entity's rates. Wages land on the schedule's 6100 line, on-costs on 6150.</p>
{% for g in groups %}<h2>{{ g.name }}<span class="count">{{ g.code }} · {{ g.entity }}</span></h2>
<table><thead><tr><th>Person</th><th>Title</th><th class="n">Salary</th><th class="n">Incentive</th><th>From</th><th>To</th><th class="n">FTE in FY{{ fy }}</th><th class="n">FY{{ fy }} wages</th><th class="n">On-costs</th></tr></thead><tbody>
{% for r in g.rows %}<tr class="{{ 'off' if r.vacancy }}"><td>{{ r.person_name }}{% if r.vacancy %} <span class="state">vacancy</span>{% endif %}</td><td class="small">{{ r.title }}</td><td class="n">{{ '{:,.0f}'.format(r.annual_salary) }}</td><td class="n">{{ r.incentive_pct|pct1 }}</td>
<td class="small">{{ r.start_date }}</td><td class="small">{{ r.end_date or '' }}</td><td class="n">{{ r.fte|n(2) }}</td><td class="n">{{ r.wages|aud }}</td><td class="n">{{ r.on_costs|aud }}</td></tr>{% endfor %}
<tr class="total"><td colspan="6">{{ g.name }}</td><td class="n">{{ g.fte|n(2) }}</td><td class="n">{{ g.wages|aud }}</td><td class="n">{{ g.on_costs|aud }}</td></tr></tbody></table>{% endfor %}{% endif %}"""


def register(bp, page, who_fn, ctx_fn, busy, session, roles) -> None:
    from . import reads

    def _scope(who: str) -> set | None:
        nodes = {r["node"] for r in q("select distinct node from dims.effective_entitlements where principal = ? and scope_dimension = 'organisation'", who or "")}
        return nodes or None

    def _lines(model: str, version: str, fy: int, who: str) -> dict:
        mine = _scope(who)
        out: dict = defaultdict(lambda: {"wages": 0.0, "on_costs": 0.0, "fte": 0.0, "n": 0})
        for r in q("""select line_id, sum(wages) wages, sum(on_costs) on_costs, sum(fte * 1.0) fte, count(*) n from plan.labour_line
                      where version_id = ? and fiscal_year = ? and model = ? group by 1""", version, fy, model):
            out[r["line_id"]] = r
        return out, mine

    def _groups(rows: list[dict], key_rows, mine) -> list[dict]:
        centres = {c["code"]: c for c in costs.planning_cost_centres()}
        groups: dict = {}
        for r in rows:
            if mine is not None and r["cost_centre_code"] not in mine:
                continue
            g = groups.setdefault((r["cost_centre_code"], r["entity_code"]), {"code": r["cost_centre_code"], "name": centres.get(r["cost_centre_code"], {}).get("name", r["cost_centre_code"]),
                                                                              "entity": r["entity_code"], "rows": [], "fte": 0.0, "wages": 0.0, "on_costs": 0.0})
            g["rows"].append(r)
            for k in ("fte", "wages", "on_costs"):
                g[k] += r.get(k) or 0
        order = {c: i for i, c in enumerate(centres)}
        return [groups[k] for k in sorted(groups, key=lambda k: (order.get(k[0], 999), k[1]))]

    def _where():
        c = ctx_fn()
        version = c.get("version") or reads.default_version()
        v = reads.version(version) or {}
        return version, int(v.get("fiscal_year") or c.get("fy") or 0)          # the version's own year

    def _plan_in(version: str, fy: int) -> dict:
        """The version's plan periods in the year, asked of the version — the periods the year's wages are summed over."""
        vp = reads.version_periods(version)
        return {"plan_in_fy": [p["period"] for p in vp["periods"] if not p["actual"] and p["fiscal_year"] == fy] if vp["periods"] else [], "upto": vp["from"]}

    @bp.get("/headcount/role")
    def headcount_role():
        try:
            who = who_fn(); version, fy = _where()
            by, mine = _lines("role", version, fy, who)
            n_periods = len({r["period"] for r in q("select distinct period from plan.labour_line where version_id = ? and fiscal_year = ?", version, fy)}) or 1
            agree = q("select * from dims.reg_agreement order by entity_code, classification, valid_from_period")
            periods = sorted({a["valid_from_period"] for a in agree})
            rates: dict = {}
            for a in agree:
                rates.setdefault((a["agreement"], a["classification"]), {**a, "rates": {}})["rates"][a["valid_from_period"]] = a["hourly_rate"]
            step = periods[-1] if periods else ""
            rows = []
            for p in q("""select r.*, a.classification_name from dims.reg_position r
                          left join (select distinct agreement, classification, classification_name from dims.reg_agreement) a using (agreement, classification)
                          order by r.cost_centre_code, r.entity_code, r.position_id"""):
                x = rates.get((p["agreement"], p["classification"]), {}).get("rates", {})
                l = by.get(p["position_id"]) or {}
                rows.append({**p, "rate_now": x.get(periods[0]) if periods else None, "rate_step": x.get(step), "wages": l.get("wages"), "on_costs": l.get("on_costs"),
                             "fte": p["fte"]})
            return page(ROLE, title="Headcount by role", active="hc_role", version=version, fy=fy, groups=_groups(rows, by, mine), **_plan_in(version, fy),
                        agreements=list(rates.values()), agreement_periods=periods, step=step)
        except Busy as e:
            return busy("Headcount by role", e)

    @bp.get("/headcount/name")
    def headcount_name():
        try:
            who = who_fn(); version, fy = _where()
            may = roles.may(who, costs.PAY_VERB)
            groups = []
            if may:
                by, mine = _lines("name", version, fy, who)
                n = len({r["period"] for r in q("select distinct period from plan.labour_line where version_id = ? and fiscal_year = ?", version, fy)}) or 1
                rows = [{**p, "wages": (by.get(p["person_id"]) or {}).get("wages"), "on_costs": (by.get(p["person_id"]) or {}).get("on_costs"),
                         "fte": ((by.get(p["person_id"]) or {}).get("fte") or 0) / n}
                        for p in q("select * from dims.reg_person order by cost_centre_code, entity_code, vacancy, person_id")]
                groups = _groups(rows, by, mine)
            return page(NAME, title="Headcount by name", active="hc_name", version=version, fy=fy, may=may, viewer=who, groups=groups, **_plan_in(version, fy),
                        pay_holders=reads.holders(costs.PAY_VERB), pay_verb=costs.PAY_VERB, pay_said=said(costs.PAY_VERB))
        except Busy as e:
            return busy("Headcount by name", e)
