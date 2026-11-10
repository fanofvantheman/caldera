"""The plan's pages. Every act is a file placed in the landing by the chassis's writer and a receipt; every number shown
is what the last run said. The checks an entry must pass to be placed live here — the chassis judges them, it does not
know them."""
from __future__ import annotations

import datetime as dt
import pathlib

from flask import Blueprint, redirect, request, url_for

from chassis import app as chassis_app, receipts
from chassis.landing import LogLanding
from chassis.run import Runner, attention, health
from chassis.warehouse import Busy, q

from . import ENTRY_COLUMNS, HEALTH, SHELL, SUBMISSION_COLUMNS, roles, session
from . import reads
from . import dashboard

plan = Blueprint("plan", __name__)
ENTRIES = LogLanding("plan", "layer_entry", ENTRY_COLUMNS)
SUBMISSIONS = LogLanding("plan", "reg_submission", SUBMISSION_COLUMNS)
SPREADS = ["baseline_shape", "history_shape", "catchment"]
KINDS = ["cases", "rate_on_baseline"]
EFFECTS = ["primary", "cannibalisation"]


def _who() -> str:
    return session.who(roles.principals())


def _page(body: str, **ctx) -> str:
    try:
        principals = roles.principals()
    except Busy:
        principals = []
    who = _who() if principals else None
    held = roles.actions_held(who) if who else set()
    return SHELL.page(body, who=who, held=held, principals=principals, flash=session.flash(), **ctx)


def _version() -> str | None:
    return request.args.get("version") or reads.default_version()


def _n(x: float | None, d: int = 0) -> str:
    return "" if x is None else f"{x:,.{d}f}"


plan.add_app_template_filter(_n, "n")
plan.add_app_template_filter(lambda x: f"{x:+,.0f}", "signed")
plan.add_app_template_filter(lambda x: "" if x is None else (f"{x / 1e6:,.2f}M" if abs(x) >= 1e6 else f"{x / 1e3:,.0f}k"), "k")
plan.add_app_template_filter(lambda x: "" if x is None else f"${x / 1e6:,.1f}M", "m")
plan.add_app_template_filter(lambda x: "" if x is None else (f"${x / 1e6:,.2f}M" if abs(x) >= 1e6 else f"${x / 1e3:,.0f}k"), "aud")
plan.add_app_template_filter(lambda x: "" if x is None else f"{x:+.1%}", "pct")
plan.add_app_template_filter(lambda x: "" if x is None else f"{x:.1%}", "pct1")
plan.add_app_template_filter(lambda x: "" if x is None else f"{x:+.1%}", "pct1s")
plan.add_app_template_filter(lambda x: "" if x is None else f"{x * 100:+.1f} pp", "pp")
plan.add_app_template_filter(lambda x: "" if x is None else ("up" if x > 0.0005 else "down" if x < -0.0005 else "flat"), "dir")
plan.add_app_template_filter(lambda x: "" if x is None else ("high" if x > 0.02 else "low" if x < -0.02 else ""), "hl")

VERSION_PICKER = """<form class="toolbar" method="get"><label>version<select name="version" onchange="this.form.submit()">
{% for v in versions %}<option value="{{ v.version_id }}" {{ 'selected' if v.version_id == version }}>{{ v.version_id }} · {{ v.status }}</option>{% endfor %}</select></label>{{ extra|safe }}</form>"""


def _busy(title: str, e: Busy) -> str:
    return _page(f"<h1>{title}</h1><p class='lede'>{e}</p>", title=title)


# ---- the role's home: what the processes you reach expect of you ----
HOME = """<h1>{{ who }}<small>what the processes you reach expect of you today</small></h1>
<h2 id="attention">My attention<span class="count">{{ mine|length }} item{{ '' if mine|length == 1 else 's' }} the last run routed to you</span></h2>
{% if mine %}<table><thead><tr><th>Activity</th><th>Context</th><th>What to do</th><th>Status</th></tr></thead><tbody>
{% for m in mine %}<tr><td>{% if m.href %}<a href="{{ m.href }}">{{ m.item }}</a>{% else %}{{ m.item }}{% endif %}</td><td>{{ m.name }}</td><td class="small muted">{{ m.what_to_do }}</td><td><span class="severity">{{ m.severity }}</span></td></tr>{% endfor %}
</tbody></table>{% else %}<p class="muted">Nothing is waiting on you.</p>{% endif %}
<h2 id="planning">My planning<span class="count">the processes your roles reach</span></h2>
{% for p in reach %}<h2>{{ p.label }}<span class="count">{{ p.says }}</span></h2>
<div class="cards">{% for a in p.areas %}<div class="card"><b>{{ a.label }}</b>
{% for line in a.lines %}<div class="small {{ 'muted' if not line.live }}">{{ line.says }}</div>{% endfor %}
<div class="small" style="margin-top:.5rem">{% for s in a.sections %}<a href="{{ s.href }}">{{ s.label }}</a>{{ ' · ' if not loop.last }}{% endfor %}</div></div>{% endfor %}</div>{% endfor %}
{% if not reach %}<p class="lede">Your roles reach no process in this product.</p>{% endif %}"""


def _expected(area_key: str, who: str, held: set[str]) -> list[dict]:
    """What an area expects of this person, as lines on their home card. Read from the last run; nothing invented."""
    v = reads.default_version(); lines = []
    def say(s: str, live: bool = True): lines.append({"says": s, "live": live})
    try:
        if area_key == "demand":
            mine = [n for n in (1, 2, 4, 6) if f"layer.{n}.enter" in held]
            if mine and v:
                rows = reads.entries(v, mine, False)
                say(f"{len(rows)} entries on {v} in your layers ({', '.join(map(str, mine))})")
            elif v:
                say(f"{v} is the open version; you read it")
            pend = ENTRIES.pending()
            if pend:
                say(f"{len(pend)} file{'s' if len(pend) > 1 else ''} placed since the last run — not yet in the plan", False)
        elif area_key == "innovation" and v:
            mine = [n for n in (7, 8) if f"layer.{n}.enter" in held]
            rows = reads.entries(v, mine or [7, 8], False)
            say(f"{len(rows)} {'of your ' if mine else ''}launch and exit entries on {v}")
        elif area_key == "reconciliation" and v:
            g = reads.bridge(v)["gap"]
            if g:
                say(f"{v} reads {g['net_sales_gap']:,.0f} net sales against {g['reference_version']}")
        elif area_key == "management":
            vs = reads.versions()
            say(", ".join(f"{x['version_id']} {x['status']}" for x in vs if x["version_kind"] != "actual"))
        elif area_key == "run":
            pend = ENTRIES.pending()
            say(f"{len(pend)} file{'s' if len(pend) > 1 else ''} waiting for the next run" if pend else "the plan is current with the landing")
            if session.run_log:
                say("last run: " + ("completed" if "✗" not in session.run_log else "stopped"), "✗" not in session.run_log)
        else:
            say("named, not yet built", False)
    except Busy as e:
        say(str(e), False)
    return lines


def _where(surface: str, r: dict) -> str | None:
    """Where the work behind a worklist row is: the page that shows it, opened at the row's scope. Routed on what the
    row carries — an entry goes to the entries page at its layer, a cell to the demand grid at its account, a
    submission to the matrix at its unit. A row with nothing to go to gets no link."""
    v = r.get("version_id")
    try:
        if r.get("entry_id"):
            return url_for("plan.entries", version=v, layer=r.get("layer_no") or "", withdrawn=1) + f"#{r['entry_id']}"
        if r.get("ship_to_code"):
            acct = reads.account_of_ship_to(r["ship_to_code"])
            return url_for("plan.demand", version=v, account=acct) if acct else url_for("plan.demand", version=v)
        if r.get("subject"):
            node = r.get("node"); lvl = r.get("level")
            unit = node if lvl == "planning_unit" else (reads.unit_of_account(node) if lvl == "account" else None)
            return url_for("plan.submissions", version=v, unit=unit) if unit else url_for("plan.submissions", version=v)
    except Exception:
        return None
    return None


def _mine(who: str, held: set[str]) -> list[dict]:
    """What the last run routed to this person, plus the one thing the face itself can see: files placed and not yet run."""
    rows = [{"item": a["row"].get("item") or a["surface"], "name": a["name"], "what_to_do": a["what_to_do"], "severity": a["severity"], "href": _where(a["surface"], a["row"])}
            for a in attention(q, who, HEALTH)]
    if "run.plan" in held:
        for f in ENTRIES.pending():
            rows.append({"item": f"{f.name} placed, not yet in the plan", "name": "landing", "what_to_do": "run the plan to take it in", "severity": "PENDING", "href": url_for("plan.run")})
    return rows


def _d(a: float | None, b: float | None) -> float | None:
    return None if not a or not b else a / b - 1


def _head(who: str, held: set[str]) -> str:
    """The home page of someone who submits the demand plan: the plan as a whole, read from the run — tiles, the year by
    period, the tree by category, the units and their submissions, the ladder and the one act at its end."""
    version = _version(); v = reads.version(version) or {}
    fy = int(v.get("fiscal_year") or 0)
    lag = 3
    ps = reads.accuracy_periods(lag); last, prior = ps[-12:], ps[-24:-12]
    acc = (reads.accuracy(lag, last) or [{}])[0]; acc_prior = (reads.accuracy(lag, prior) or [{}])[0]
    acc["d"] = None if acc.get("accuracy") is None or acc_prior.get("accuracy") is None else acc["accuracy"] - acc_prior["accuracy"]
    acc_of = {}
    for c in reads.accuracy_tree(lag, last):
        acc_of[c["category_code"]] = c
        for pr in c["children"]:
            acc_of[pr["product_code"]] = pr
            for m in pr["children"]:
                acc_of[m["standard_material"]] = m
    tree = reads.demand_tree(version, fy)
    for c in tree["categories"]:
        for node in [c] + c["children"] + [m for pr in c["children"] for m in pr["children"]]:
            node["py_d"] = _d(node["value"], node["py"]); node["ref_d"] = _d(node["value"], node["ref"])
    t = {"value": tree["total"]["value"], "value_d": _d(tree["total"]["value"], tree["total"]["py"]), "ref_d": _d(tree["total"]["value"], tree["total"]["ref"])}
    rev = reads.revenue_fy(version, fy); rev["d"] = _d(rev["net_sales"], rev["ref_net_sales"])
    units = reads.unit_status(version, fy)
    for u in units:
        u["d"] = _d(u["value"], u["py"])
        u["cell"] = _cell(who, {"subject": "unit", "node": u["code"], "state": u["state"] or "nothing", "open_below": u["open_below"], "acted_by": u["acted_by"], "acted_on": u["acted_on"]})
    ladder = reads.ladder(version)
    now = next((i for i, s in enumerate(ladder) if s["done"] < s["total"] or not s["total"]), len(ladder))
    st = next((r for r in reads.submission_matrix(version) if r["subject"] == "plan" and r["node"] == "ALL"), None)
    plan_cell = _cell(who, st)
    open_units = [u["unit_name"] for u in units if u["state"] not in ("submitted", "rolled_up")]
    status_line = ("plan submitted" + (f" · {st['open_below']} open beneath" if st and st.get("open_below") else "")) if st and st["state"] == "submitted" \
        else ("open: " + ", ".join(open_units) if open_units else "every unit in — ready to submit")
    actions = [{"label": s.label, "href": url_for(s.endpoint, **s.args), "says": a.label}
               for p, areas in SHELL.reach(held) if p.key == "ibp" for a, secs in areas for s in secs if s.key in ("demand", "submissions", "accuracy", "entries", "gap", "versions", "run")]
    links = {"demand": url_for("plan.demand", version=version), "money": url_for("plan.gap", version=version), "accuracy": url_for("plan.accuracy"),
             "submissions": url_for("plan.submissions", version=version), "versions": url_for("plan.versions")}
    for u in units:
        u["href"] = url_for("plan.submissions", version=version, unit=u["code"])
    # the figure's drill: a node of one structure, its children as small multiples beneath
    # read per week (the 4-4-5 calendar steps a period total every third period); the grain and measure travel with every link
    dim = request.args.get("dim") if request.args.get("dim") in ("customer", "material") else "customer"
    node = request.args.get("node") or "ALL"
    grain = request.args.get("grain") if request.args.get("grain") in ("period", "week") else "period"
    leaf = dim == "material" and reads.is_material(node)             # cases mean one thing at a material and nothing above it
    measure = "cases" if leaf and request.args.get("measure") == "cases" else "net_sales"
    def L(**kw): return url_for("plan.home", **{"version": version, "dim": dim, "node": node, "grain": grain, "measure": measure, **kw})
    at = {"customer": node} if dim == "customer" else {"material": node}
    series = reads.demand_series(version, fy, grain=grain, measure=measure, **at)
    drill = {"dim": dim, "node": node, "label": reads.node_label(dim, node),
             "path": [{**n, "href": L(node=n["code"])} for n in reads.node_path(dim, node)],
             "other": L(dim=("material" if dim == "customer" else "customer"), node="ALL"),
             "children": []}
    fig = {"grains": [{"label": g, "on": g == grain, "href": L(grain=g)} for g in ("period", "week")],
           "measures": [{"label": lab, "on": m == measure, "href": L(measure=m)} for m, lab in (("net_sales", "net sales"), ("cases", "cases"))] if leaf else []}
    for ch in reads.node_children(dim, node):
        cs = reads.demand_series(version, fy, grain=grain, measure=measure, **({"customer": ch["code"]} if dim == "customer" else {"material": ch["code"]}))
        if cs["view"]:
            drill["children"].append({**ch, "href": L(node=ch["code"]), "total": cs["total"],
                                      "chart": dashboard.chart(cs, fy, width=360, height=110, small=True)})
    drill["children"].sort(key=lambda c: -c["total"])
    return _page(dashboard.HEAD_PAGE, title="Demand", active=None, width="none", links=links, drill=drill, fig=fig, version=version, versions=reads.versions(), fy=fy, lag=lag,
                 t=t, rev=rev, acc=acc, acc_of=acc_of, tree=tree, units=units, ladder=ladder, now=now, plan_cell=plan_cell, status_line=status_line,
                 series=series, chart=dashboard.chart(series, fy), mine=_mine(who, held), actions=actions)


@plan.get("/")
def home():
    try:
        who = _who(); held = roles.actions_held(who)
        if "demand.plan.submit" in held:
            return _head(who, held)
        reach = [{"label": p.label, "says": p.says,
                  "areas": [{"label": a.label, "lines": _expected(a.key, who, held),
                             "sections": [{"label": s.label, "href": url_for(s.endpoint, **s.args)} for s in secs]} for a, secs in areas]}
                 for p, areas in SHELL.reach(held)]
        return _page(HOME, title="Home", active=None, reach=reach, mine=_mine(who, held))
    except Busy as e:
        return _busy("Home", e)


# ---- the demand plan ----
DEMAND = VERSION_PICKER + """
<h1>Demand plan<small>{{ version }} · unconstrained · cases by standard material{% if account %} · {{ account }}{% endif %} · {{ d.n_actual }} closed periods as actuals, then the plan · totals by fiscal year with comparatives</small></h1>
{% if editable %}<p class="hint">Cells are open: click one, type the total you want, Enter, give a reason. What is placed is an entry on layer {{ layer }} for the difference; the cell shows the run's number until the next run takes it in.</p>
{% elif can_enter %}<p class="hint">Choose an account to open the cells for input.</p>{% endif %}
<div class="wide"><table class="plan" {% if editable %}data-cells-post="{{ url_for('plan.cell') }}" data-cells-reasons="reasons"{% endif %}><thead>
<tr><th rowspan="2" class="sticky">Material</th><th colspan="{{ d.periods|length }}" style="text-align:center">Periods</th>
{% for c in d.comps %}<th colspan="{{ 1 + (1 if c.py else 0) + (1 if c.ref else 0) }}" style="text-align:center;border-left:1px solid var(--rule)">FY{{ c.fy }}</th>{% endfor %}<th class="n" rowspan="2">Horizon</th></tr>
<tr>{% for pp in d.periods %}<th class="n {{ 'actual' if d.source_of[pp] == 'actual' }}" title="{{ pp }}{{ ' · actual' if d.source_of[pp] == 'actual' }}">{{ pp[2:4] }}·{{ pp[5:] }}</th>{% endfor %}
{% for c in d.comps %}<th class="n" style="border-left:1px solid var(--rule)">Total</th>{% if c.py %}<th class="n" title="same periods, prior fiscal year: shipments where closed, else this view">PY</th>{% endif %}{% if c.ref %}<th class="n" title="{{ d.ref_id }}">{{ d.ref_id }}</th>{% endif %}{% endfor %}</tr></thead><tbody>
{% for r in d.rows + [d.totals] %}<tr class="{{ 'total' if r.material == 'Total' }}"><td class="sticky">{{ r.material }}</td>{% for c in r.cells %}{% set pp = d.periods[loop.index0] %}{% set key = r.material ~ '|' ~ pp %}
<td class="n {{ 'actual' if d.source_of[pp] == 'actual' }} {{ 'has-pending' if key in pending }}" {% if editable and r.material != 'Total' and d.source_of[pp] != 'actual' %}data-cell='{"version": "{{ version }}", "layer": {{ layer }}, "material": "{{ r.material }}", "account": "{{ account }}", "period": "{{ pp }}"}' data-current="{{ c or 0 }}"{% endif %}>{{ c|n }}{% if key in pending %}<span class="pending" title="placed, not yet run">{{ pending[key]|signed }} pending</span>{% endif %}</td>{% endfor %}
{% for b in r.blocks %}<td class="n" style="border-left:1px solid var(--rule);font-weight:500">{{ b.total|n }}</td>{% if d.comps[loop.index0].py %}<td class="n muted">{{ b.py|n }}</td>{% endif %}{% if d.comps[loop.index0].ref %}<td class="n muted">{{ b.ref|n }}</td>{% endif %}{% endfor %}<td class="n" style="font-weight:600">{{ r.total|n }}</td></tr>{% endfor %}
</tbody></table></div>
<p class="hint">Shaded periods are closed and read from shipments; the rest is the plan. PY is the same periods a year earlier — shipments where that year is closed, otherwise this view; {{ d.ref_id }} is the reference version where its horizon overlaps.</p>
<h2>Plan by layer and fiscal year</h2>
<table><thead><tr><th>Fiscal year</th><th class="n">1 Baseline</th><th class="n">2 Adjustment</th><th class="n">4 Distribution</th><th class="n">6 Promotions</th><th class="n">7 Innovation</th><th class="n">8 Exit</th><th class="n">Plan</th></tr></thead><tbody>
{% for r in layers %}<tr><td>FY{{ r.fiscal_year }}</td><td class="n">{{ r.l1|n }}</td><td class="n">{{ r.l2|n }}</td><td class="n">{{ r.l4|n }}</td><td class="n">{{ r.l6|n }}</td><td class="n">{{ r.l7|n }}</td><td class="n">{{ r.l8|n }}</td><td class="n">{{ r.cases|n }}</td></tr>{% endfor %}
</tbody></table>
{% if editable %}<script type="application/json" id="reasons">{{ reasons_json|safe }}</script><script src="{{ url_for('static', filename='cells.js') }}"></script>{% endif %}
<style>.wide{overflow-x:auto;margin:0 -1rem;padding:0 1rem}table.plan{width:max-content;min-width:100%;font-size:.82rem}table.plan th,table.plan td{padding:.35rem .5rem}
table.plan .actual{background:var(--soft)}table.plan .sticky{position:sticky;left:0;background:var(--panel);z-index:1}table.plan th.sticky{z-index:2;background:var(--soft)}</style>"""


def _pending_cells(version: str, account: str | None) -> dict[str, float]:
    """Entries placed since the last run, as the grid would see them: material|period → cases, where the entry is a single
    period in cases at exactly the grid's grain. Anything wider is in the plan after the run, not shown as a mark."""
    out: dict[str, float] = {}
    if not account:
        return out
    db_t = ENTRIES.pending()
    names = {p.name for p in db_t}
    for r in ENTRIES.rows():
        if r["source_file"] in names and r["action"] == "enter" and r["version_id"] == version and r["scope_customer"] == account \
                and r["period_from"] == r["period_to"] and r["value_kind"] == "cases":
            k = f"{r['scope_material']}|{r['period_from']}"
            out[k] = out.get(k, 0.0) + float(r["value"] or 0)
    return out


@plan.get("/demand")
def demand():
    try:
        import json
        who = _who(); version = _version(); account = request.args.get("account") or None
        v = reads.version(version) or {}
        enterable = [n for n in roles.layers_enterable(who) if n != 1]           # layer 1 is computed on an open version; a typed change is an adjustment
        layer = int(request.args.get("layer") or (enterable[0] if enterable else 0))
        can_enter = bool(enterable) and v.get("status") == "open"
        editable = can_enter and bool(account) and layer in enterable
        reasons = [{"code": r["reason_code"], "says": r["description"]} for r in reads.reasons() if str(layer) in r["layers"].split(",")] or \
                  [{"code": r["reason_code"], "says": r["description"]} for r in reads.reasons()]
        accounts = reads.accounts()
        extra = ('<label>account<select name="account" onchange="this.form.submit()"><option value="">all</option>'
                 + "".join(f'<option value="{a["account_code"]}" {"selected" if a["account_code"] == account else ""}>{a["account_code"]}</option>' for a in accounts) + "</select></label>")
        if can_enter:
            names = {l["layer_no"]: l["layer_name"] for l in reads.layers()}
            extra += ('<label>enter as layer<select name="layer" onchange="this.form.submit()">'
                      + "".join(f'<option value="{n}" {"selected" if n == layer else ""}>{n} {names.get(n, "")}</option>' for n in enterable) + "</select></label>")
        return _page(DEMAND, title="Demand plan", active="demand", width="100%", versions=reads.versions(), version=version, account=account,
                     d=reads.demand(version, account), layers=reads.by_layer(version, account), extra=extra,
                     editable=editable, can_enter=can_enter, layer=layer, reasons_json=json.dumps(reasons), pending=_pending_cells(version, account))
    except Busy as e:
        return _busy("Demand plan", e)


# ---- entries ----
ENTRIES_PAGE = VERSION_PICKER + """
<h1>{{ title }}<small>{{ version }} · {{ lede }}</small></h1>
<table><thead><tr><th>Layer</th><th>Entry</th><th>By</th><th>On</th><th>Reason</th><th>Material</th><th>Customer</th><th>Window</th><th class="n">Value</th><th>Spread</th><th>Note</th><th></th></tr></thead><tbody>
{% for e in rows %}<tr id="{{ e.entry_id }}" class="{{ 'off' if e.withdrawn and e.withdrawn_by_owner }}">
<td>{{ e.layer_no }}</td><td><code>{{ e.entry_id }}</code>{% if not e.entered_by_owner %} <span class="state">refused</span>{% endif %}{% if e.withdrawn and not e.withdrawn_by_owner %} <span class="state">withdrawal refused</span>{% endif %}</td>
<td>{{ e.entered_by }}</td><td>{{ e.entered_on }}</td><td title="{{ e.reason_description or '' }}">{{ e.reason_code }}{% if not e.reason_known %} <span class="state">unknown</span>{% endif %}</td>
<td>{{ e.scope_material }}</td><td>{{ e.scope_customer }}</td><td>{{ e.period_from }}{% if e.period_to != e.period_from %} – {{ e.period_to }}{% endif %}</td>
<td class="n">{{ e.value|n(2) }} {{ 'cases' if e.value_kind == 'cases' else 'on baseline' }}{% if e.effect_type != 'primary' %} · {{ e.effect_type }}{% endif %}</td><td>{{ e.spread_rule }}</td><td class="small">{{ e.note or '' }}</td>
<td class="acts">{% if not e.withdrawn and e.version_status == 'open' and e.layer_no in may_withdraw %}<form class="inline" method="post" action="{{ url_for('plan.withdraw') }}">
<input type="hidden" name="entry_id" value="{{ e.entry_id }}"><input type="hidden" name="version" value="{{ version }}"><input type="hidden" name="layer_no" value="{{ e.layer_no }}"><button class="act">withdraw</button></form>{% endif %}</td></tr>{% endfor %}
</tbody></table>"""


def _entries(title: str, active: str, layers_fixed: list[int] | None = None, lede: str | None = None):
    version = _version(); layer = request.args.get("layer") or ""
    show = request.args.get("withdrawn") == "1"
    v = reads.version(version) or {}
    wanted = layers_fixed if layers_fixed else ([int(layer)] if layer else None)
    rows = [{**e, "version_status": v.get("status")} for e in reads.entries(version, wanted, show)]
    who = _who()
    may_withdraw = {l["layer_no"] for l in reads.layers() if roles.may(who, f"layer.{l['layer_no']}.withdraw")}
    layer_pick = "" if layers_fixed else ('<label>layer<select name="layer" onchange="this.form.submit()"><option value="">all</option>'
        + "".join(f'<option value="{l["layer_no"]}" {"selected" if str(l["layer_no"]) == layer else ""}>{l["layer_no"]} {l["layer_name"]}</option>' for l in reads.layers()) + "</select></label>")
    extra = layer_pick + f'<label>withdrawn<select name="withdrawn" onchange="this.form.submit()"><option value="0">hidden</option><option value="1" {"selected" if show else ""}>shown</option></select></label>'
    return _page(ENTRIES_PAGE, title=title, active=active, versions=reads.versions(), version=version, rows=rows, may_withdraw=may_withdraw, extra=extra,
                 lede=lede or "what the people typed, one row per contribution to a layer")


@plan.get("/entries")
def entries():
    try:
        return _entries("Entries", "entries")
    except Busy as e:
        return _busy("Entries", e)


@plan.get("/launches")
def launches():
    try:
        return _entries("Launches", "launches", [7], "the innovation layer: launch volume typed in by marketing, cannibalisation as its own line")
    except Busy as e:
        return _busy("Launches", e)


@plan.get("/exits")
def exits():
    try:
        return _entries("Exits", "exits", [8], "the lifecycle exit layer: run-out and discontinuation")
    except Busy as e:
        return _busy("Exits", e)


@plan.post("/withdraw")
def withdraw():
    f = request.form; who = _who(); eid = f["entry_id"]; layer = int(f["layer_no"]); version = f["version"]
    e = reads.entry(eid); v = reads.version(version)
    checks = [
        {"check": "entry on file", "ok": e is not None, "says": f"{eid} is on file" if e else f"{eid} is not on file"},
        {"check": "version open", "ok": bool(v and v["status"] == "open"), "says": f"{version} is {v['status'] if v else 'unknown'}"},
        {"check": "who may withdraw", "ok": roles.may(who, f"layer.{layer}.withdraw"), "says": f"{who} holds layer {layer} withdraw" if roles.may(who, f"layer.{layer}.withdraw") else f"{who} does not hold layer {layer} withdraw"},
        {"check": "not already withdrawn", "ok": not (e and e["withdrawn"] and e["withdrawn_by_owner"]), "says": "stands" if not (e and e["withdrawn"]) else "already withdrawn"},
    ]
    placed = receipts.judge(checks)
    if placed:
        ENTRIES.place([{"entry_id": f"LW-F-{dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')}", "action": "withdraw", "withdraws": eid, "version_id": version,
                        "layer_no": layer, "entered_by": who, "entered_on": dt.date.today().isoformat(), "reason_code": "", "effect_type": "primary",
                        "scope_material": "", "scope_customer": "", "period_from": "", "period_to": "", "value_kind": "cases", "value": 0,
                        "spread_rule": "baseline_shape", "note": f.get("note", "")}], who)
    session.last = receipts.write("withdraw", who, eid, checks, placed)
    session.say(f"withdrawal of {eid} placed — it takes effect on the next run" if placed else "withdrawal refused: " + "; ".join(c["says"] for c in checks if not c["ok"]), placed)
    return redirect(url_for("plan.entries", version=version))


# ---- new entry ----
NEW = """<h1>New entry<small>a contribution to a layer on an open version — placed as a file, read on the next run</small></h1>
{% if not layers %}<p class="lede">{{ who }} holds no enter verb on any layer.</p>{% else %}
<form class="entry" method="post" action="{{ url_for('plan.entry_new') }}">
<label>version<select name="version_id">{% for v in versions %}<option value="{{ v.version_id }}">{{ v.version_id }} · {{ v.horizon_start }} – {{ v.horizon_end }}</option>{% endfor %}</select></label>
<label>layer<select name="layer_no">{% for l in layers %}<option value="{{ l.layer_no }}">{{ l.layer_no }} {{ l.layer_name }}</option>{% endfor %}</select></label>
<label>reason<select name="reason_code">{% for r in reasons %}<option value="{{ r.reason_code }}">{{ r.reason_code }} · {{ r.description }} (layers {{ r.layers }})</option>{% endfor %}</select></label>
<label>effect<select name="effect_type">{% for e in effects %}<option>{{ e }}</option>{% endfor %}</select></label>
<label>material scope<input name="scope_material" list="materials" required placeholder="a node of the product structure, or a promo group"><datalist id="materials">{% for m in materials %}<option value="{{ m.code }}">{{ m.lvl }}</option>{% endfor %}</datalist></label>
<label>customer scope<input name="scope_customer" list="customers" required placeholder="a node of the customer structure"><datalist id="customers">{% for c in customers %}<option value="{{ c.code }}">{{ c.lvl }}</option>{% endfor %}</datalist></label>
<label>from period<input name="period_from" list="periods" required placeholder="2027P05"></label>
<label>to period<input name="period_to" list="periods" required placeholder="2027P08"><datalist id="periods">{% for p in periods %}<option value="{{ p }}">{% endfor %}</datalist></label>
<label>value<input name="value" type="number" step="any" required></label>
<label>kind<select name="value_kind">{% for k in kinds %}<option>{{ k }}</option>{% endfor %}</select></label>
<label>spread<select name="spread_rule">{% for s in spreads %}<option>{{ s }}</option>{% endfor %}</select></label>
<label class="wide">note<textarea name="note" rows="2"></textarea></label>
<div class="actions"><button class="primary">Place entry</button><span class="hint">entered by {{ who }} as at today</span></div></form>{% endif %}
{% if last %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else '✕' }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}"""


def _enter(f: dict, who: str) -> tuple[dict, bool, str]:
    """The plan's checks on a contribution, then the act: a file in the landing and a receipt. Shared by the form and
    the cell — one act, two faces. Returns (receipt, placed, entry_id)."""
    layer = int(f["layer_no"]); version = f["version_id"]
    v = reads.version(version); hz = reads.horizon(version)
    reason = next((r for r in reads.reasons() if r["reason_code"] == f["reason_code"]), None)
    try:
        value = float(f["value"])
    except (ValueError, TypeError):
        value = None
    may = roles.may(who, f"layer.{layer}.enter")
    ms, cs = reads.material_scope_resolves(f["scope_material"]), reads.customer_scope_resolves(f["scope_customer"])
    win = f["period_from"] in hz and f["period_to"] in hz and f["period_from"] <= f["period_to"]
    offered = bool(reason and str(layer) in reason["layers"].split(","))
    closed = reads.layer_closed_at(version, layer, f["scope_customer"]) if cs else None
    checks = [
        {"check": "layer open at scope", "ok": closed is None,
         "says": f"layer {layer} is open at {f['scope_customer']}" if closed is None else f"layer {layer} was submitted at {closed['scope_node']} by {closed['acted_by']} on {closed['acted_on']} — closed until reopened"},
        {"check": "version open", "ok": bool(v and v["status"] == "open"), "says": f"{version} is {v['status'] if v else 'unknown'}"},
        {"check": "who may enter", "ok": may, "says": f"{who} holds layer {layer} enter" if may else f"{who} does not hold layer {layer} enter"},
        {"check": "material scope resolves", "ok": ms, "says": f"{f['scope_material']} reaches leaf materials" if ms else f"{f['scope_material']} is not a node of the product structure or a promo group"},
        {"check": "customer scope resolves", "ok": cs, "says": f"{f['scope_customer']} reaches ship-tos" if cs else f"{f['scope_customer']} is not a node of the customer structure"},
        {"check": "window in horizon", "ok": win, "says": f"{f['period_from']} – {f['period_to']} within {v['horizon_start']} – {v['horizon_end']}" if v and win else "window outside the version's horizon or reversed"},
        {"check": "reason offered on layer", "ok": offered, "flag": True,
         "says": f"{f['reason_code']} is offered on layer {layer}" if offered else f"{f['reason_code']} is not a reason this layer usually gives — placed, flagged"},
        {"check": "value is a number", "ok": value is not None and value != 0, "says": "a number" if value is not None and value != 0 else "not a number, or zero"},
        {"check": "vocabulary", "ok": f["value_kind"] in KINDS and f["spread_rule"] in SPREADS and f["effect_type"] in EFFECTS, "says": "kind, spread and effect are known"},
    ]
    placed = receipts.judge(checks)
    eid = f"LE-F-{dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
    if placed:
        ENTRIES.place([{"entry_id": eid, "action": "enter", "withdraws": "", "version_id": version, "layer_no": layer, "entered_by": who,
                        "entered_on": dt.date.today().isoformat(), "reason_code": f["reason_code"], "effect_type": f["effect_type"],
                        "scope_material": f["scope_material"], "scope_customer": f["scope_customer"], "period_from": f["period_from"],
                        "period_to": f["period_to"], "value_kind": f["value_kind"], "value": value, "spread_rule": f["spread_rule"], "note": f.get("note") or ""}], who)
    return receipts.write("enter", who, eid, checks, placed), placed, eid


@plan.route("/new", methods=["GET", "POST"])
def entry_new():
    try:
        who = _who()
        if request.method == "POST":
            f = request.form
            session.last, placed, eid = _enter(f, who)
            session.say(f"{eid} placed on {f['version_id']} layer {f['layer_no']} — it is in the plan after the next run" if placed
                        else "entry refused: " + "; ".join(c["says"] for c in session.last["checks"] if not c["ok"]), placed)
            return redirect(url_for("plan.entry_new"))
        enterable = set(roles.layers_enterable(who))
        return _page(NEW, title="New entry", active="new", versions=reads.open_versions(),
                     layers=[l for l in reads.layers() if l["layer_no"] in enterable], reasons=reads.reasons(), effects=EFFECTS, kinds=KINDS, spreads=SPREADS,
                     materials=reads.material_scopes(), customers=reads.customer_scopes(),
                     periods=reads.horizon(reads.default_version() or ""), last=session.last)
    except Busy as e:
        return _busy("New entry", e)


@plan.post("/cell")
def cell():
    """A number typed into a plan cell. The cell is material × account × period on a version; what is placed is an entry
    on the chosen layer for the difference between what was typed and what the run last showed — the cell is never
    edited, the plan gains a contribution, and the next run shows the new number."""
    b = request.get_json(force=True); who = _who()
    delta = float(b["typed"]) - float(b.get("current") or 0)
    f = {"version_id": b["version"], "layer_no": b["layer"], "reason_code": b["reason"], "effect_type": "primary", "scope_material": b["material"],
         "scope_customer": b["account"], "period_from": b["period"], "period_to": b["period"], "value_kind": "cases", "value": delta,
         "spread_rule": "baseline_shape", "note": b.get("note") or f"typed {float(b['typed']):,.0f} over {float(b.get('current') or 0):,.0f} in the grid"}
    r, placed, eid = _enter(f, who)
    session.last = r
    says = (f"{eid}: {delta:+,.0f} cases on layer {b['layer']} for {b['material']} at {b['account']} in {b['period']} — in the plan after the next run" if placed
            else "refused: " + "; ".join(c["says"] for c in r["checks"] if not c["ok"]))
    return {"placed": placed, "says": says, "mark": f"{delta:+,.0f} pending", "entry_id": eid}


# ---- submissions: the matrix, and the acts ----
SUBMISSIONS_PAGE = VERSION_PICKER + """
<h1>Submissions<small>{{ version }} · who has declared what complete, where — every state derived by the run from the acts and the entries</small></h1>
<table class="matrix"><thead><tr><th>Subject</th>{% for u in units %}<th class="stage">{{ u.unit_name }}</th>{% endfor %}<th class="stage">Demand plan</th></tr></thead><tbody>
{% for row in rows %}<tr><td>{{ row.label }}</td>{% for cell in row.cells %}<td class="stage {{ 'can' if cell.can }}" title="{{ cell.title }}">
<span class="state {{ cell.state }} {{ 'gap' if 'beneath' in cell.show }}">{{ cell.show }}</span>{% if cell.can %}<form class="inline" method="post" action="{{ url_for('plan.submit') }}">
<input type="hidden" name="version" value="{{ version }}"><input type="hidden" name="subject" value="{{ row.subject }}"><input type="hidden" name="node" value="{{ cell.node }}">
<input type="hidden" name="act" value="{{ cell.can }}"><button class="act">{{ cell.can }}</button></form>{% endif %}
{% if cell.by %}<div class="small muted">{{ cell.by.split('@')[0] }} · {{ cell.on }}</div>{% endif %}</td>{% endfor %}</tr>{% endfor %}
</tbody></table>
<p class="hint">Filled: submitted here. Outlined: rolled up from beneath, or ready for the holder's act. Dashed: open — something beneath is not in. Layers scoped on material submit once, at the plan.</p>
{% if unit %}<h2>{{ unit_name }} by account<span class="count">the account-facing layers</span></h2>
<table class="matrix"><thead><tr><th>Layer</th>{% for a in accounts %}<th class="stage">{{ a.code }}</th>{% endfor %}</tr></thead><tbody>
{% for row in acct_rows %}<tr><td>{{ row.label }}</td>{% for cell in row.cells %}<td class="stage" title="{{ cell.title }}"><span class="state {{ cell.state }}">{{ cell.show }}</span>{% if cell.can %}<form class="inline" method="post" action="{{ url_for('plan.submit') }}">
<input type="hidden" name="version" value="{{ version }}"><input type="hidden" name="subject" value="{{ row.subject }}"><input type="hidden" name="node" value="{{ cell.node }}">
<input type="hidden" name="act" value="{{ cell.can }}"><button class="act">{{ cell.can }}</button></form>{% endif %}{% if cell.by %}<div class="small muted">{{ cell.by.split('@')[0] }} · {{ cell.on }}</div>{% endif %}</td>{% endfor %}</tr>{% endfor %}
</tbody></table>{% endif %}
<h2>Acts on file<span class="count">latest per subject and node</span></h2>
<table><thead><tr><th>Subject</th><th>Node</th><th>State</th><th>By</th><th>On</th><th>Note</th></tr></thead><tbody>
{% for a in acts %}<tr class="{{ '' if a.acted_by_holder else 'off' }}"><td>{{ a.subject }}</td><td>{{ a.scope_node }}</td><td><span class="state {{ a.state }}">{{ a.state }}</span>{% if not a.acted_by_holder %} <span class="state">refused</span>{% endif %}</td><td>{{ a.acted_by }}</td><td>{{ a.acted_on }}</td><td class="small">{{ a.note or '' }}</td></tr>{% endfor %}
</tbody></table>
{% if pending %}<p class="hint">{{ pending|length }} act{{ '' if pending|length == 1 else 's' }} placed since the last run — the matrix shows them after the run.</p>{% endif %}
<style>table.matrix td.stage{vertical-align:top}.state.submitted{background:var(--ink);color:var(--paper)}.state.rolled_up,.state.ready{background:var(--panel)}
.state.open{border-style:dashed}.state.submitted.gap{background:var(--panel);color:var(--ink);border-style:dashed;border-width:2px}.state.nothing,.state.na{color:var(--faint);border-color:var(--faint)}.state.reopened{border-style:double}</style>"""

SUBJECT_ORDER = ["layer:4", "layer:6", "layer:7", "layer:8", "layer:1", "layer:2", "unit", "plan"]


def _can_act(who: str, subject: str, node: str, state: str) -> str | None:
    """Which act this person may make here: submit when open, ready or rolled up; reopen when submitted. None if neither."""
    verb = f"layer.{subject[6:]}" if subject.startswith("layer:") else f"demand.{subject}"
    if state in ("open", "ready", "rolled_up") and roles.may(who, f"{verb}.submit", node, dimension="customer"):
        return "submit"
    if state == "submitted" and roles.may(who, f"{verb}.reopen", node, dimension="customer"):
        return "reopen"
    return None


def _label(subject: str, layer_name: str | None) -> str:
    return {"unit": "Unit demand", "plan": "Demand plan"}.get(subject) or f"Layer {subject[6:]} {layer_name or ''}"


def _cell(who: str, st: dict | None) -> dict:
    if st is None:
        return {"state": "n/a", "show": "—", "node": "", "can": None, "title": "", "by": None, "on": None}
    show = {"n/a": "—", "nothing": "nothing", "rolled_up": "rolled up"}.get(st["state"], st["state"])
    if st["state"] == "submitted" and st.get("open_below"):
        show = f"submitted · {st['open_below']} open beneath"
    return {"state": st["state"].replace("/", ""), "show": show, "node": st["node"], "can": _can_act(who, st["subject"], st["node"], st["state"]) if st["state"] != "n/a" else None,
            "title": f"{st['subject']} at {st['node']}: {st['state']}" + (f" · holders: {st['whose']}" if st.get("whose") else ""), "by": st.get("acted_by"), "on": st.get("acted_on")}


@plan.get("/submissions")
def submissions():
    try:
        who = _who(); version = _version(); unit = request.args.get("unit") or None
        units = reads.units(); matrix = reads.submission_matrix(version)
        by = {(r["subject"], r["node"]): r for r in matrix}
        names = {f"layer:{l['layer_no']}": l["layer_name"] for l in reads.layers()}
        subjects = [sj for sj in SUBJECT_ORDER if any(k[0] == sj for k in by)]
        rows = []
        for sj in subjects:
            cells = [_cell(who, by.get((sj, u["code"]))) for u in units] + [_cell(who, by.get((sj, "ALL")) if sj != "unit" else None)]
            rows.append({"subject": sj, "label": _label(sj, names.get(sj)), "cells": cells})
        acct_rows, accounts, unit_name = [], [], None
        if unit:
            accounts = reads.accounts_of(unit); unit_name = next((u["unit_name"] for u in units if u["code"] == unit), unit)
            for sj in subjects:
                if by.get((sj, accounts[0]["code"]), {}).get("state", "n/a") != "n/a" if accounts else False:
                    acct_rows.append({"subject": sj, "label": _label(sj, names.get(sj)), "cells": [_cell(who, by.get((sj, a["code"]))) for a in accounts]})
        extra = ('<label>unit by account<select name="unit" onchange="this.form.submit()"><option value="">none</option>'
                 + "".join(f'<option value="{u["code"]}" {"selected" if u["code"] == unit else ""}>{u["unit_name"]}</option>' for u in units) + "</select></label>")
        return _page(SUBMISSIONS_PAGE, title="Submissions", active="submissions", versions=reads.versions(), version=version, units=units, rows=rows,
                     unit=unit, unit_name=unit_name, accounts=accounts, acct_rows=acct_rows, acts=reads.submission_acts(version), extra=extra, pending=SUBMISSIONS.pending())
    except Busy as e:
        return _busy("Submissions", e)


@plan.post("/submit")
def submit():
    f = request.form; who = _who(); version, subject, node, act = f["version"], f["subject"], f["node"], f["act"]
    v = reads.version(version)
    st = next((r for r in reads.submission_matrix(version) if r["subject"] == subject and r["node"] == node), None)
    verb = (f"layer.{subject[6:]}" if subject.startswith("layer:") else f"demand.{subject}") + f".{act}"
    holds = roles.may(who, verb, node, dimension="customer")
    fits = bool(st) and ((act == "submit" and st["state"] in ("open", "ready", "rolled_up")) or (act == "reopen" and st["state"] == "submitted"))
    over_open = act == "submit" and bool(st) and st["state"] == "open"
    checks = [
        {"check": "version open", "ok": bool(v and v["status"] == "open"), "says": f"{version} is {v['status'] if v else 'unknown'}"},
        {"check": "who holds the verb here", "ok": holds, "says": f"{who} holds {verb} at {node}" if holds else f"{who} does not hold {verb} at {node}"},
        {"check": "act fits the state", "ok": fits, "says": f"{subject} at {node} is {st['state'] if st else 'unknown'}"},
        {"check": "submitting over open children", "ok": not over_open, "flag": True,
         "says": "something beneath is still open — submitted over it, on record" if over_open else "nothing open beneath"},
    ]
    placed = receipts.judge(checks)
    sid = f"SB-F-{dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
    if placed:
        SUBMISSIONS.place([{"submission_id": sid, "action": act, "version_id": version, "subject": subject, "scope_node": node, "submitted_by": who,
                            "submitted_on": dt.date.today().isoformat(), "note": f.get("note", "")}], who)
    session.last = receipts.write(act, who, f"{subject}@{node}", checks, placed)
    session.say(f"{act} of {subject} at {node} placed — the matrix shows it after the next run" if placed else f"{act} refused: " + "; ".join(c["says"] for c in checks if not c["ok"]), placed)
    return redirect(url_for("plan.submissions", version=version))


# ---- the revenue bridge ----
MONEY = VERSION_PICKER + """
<h1>Revenue bridge<small>{{ version }} · every line valued through the gross-to-net at the list and terms in force</small></h1>
{% if b.gap %}<div class="cards">
<div class="card stat"><b>{{ b.gap.plan_net_sales|n }}</b><span>net sales, this version</span></div>
<div class="card stat"><b>{{ b.gap.reference_net_sales|n }}</b><span>net sales, {{ b.gap.reference_version }}</span></div>
<div class="card stat"><b>{{ b.gap.net_sales_gap|n }}</b><span>gap to reference</span></div>
<div class="card stat"><b>{{ b.gap.cases_gap|n }}</b><span>cases gap</span></div></div>{% endif %}
<h2>By layer</h2>
<table><thead><tr><th>Layer</th><th class="n">Cases</th><th class="n">Gross at list</th><th class="n">On-invoice</th><th class="n">Gross invoice</th><th class="n">Off-invoice</th><th class="n">Net sales</th></tr></thead><tbody>
{% for r in b.by_layer %}<tr><td>{{ r.layer_no }} {{ r.layer_name }}</td><td class="n">{{ r.cases|n }}</td><td class="n">{{ r.gross_at_list|n }}</td><td class="n">{{ r.on_invoice|n }}</td><td class="n">{{ r.gross_invoice|n }}</td><td class="n">{{ r.off_invoice|n }}</td><td class="n">{{ r.net_sales|n }}</td></tr>{% endfor %}
</tbody></table>
<h2>By period</h2>
<table><thead><tr><th>Period</th><th class="n">Gross at list</th><th class="n">On-invoice</th><th class="n">Gross invoice</th><th class="n">Off-invoice</th><th class="n">Net sales</th></tr></thead><tbody>
{% for r in b.by_period %}<tr><td>{{ r.period }}</td><td class="n">{{ r.gross_at_list|n }}</td><td class="n">{{ r.on_invoice|n }}</td><td class="n">{{ r.gross_invoice|n }}</td><td class="n">{{ r.off_invoice|n }}</td><td class="n">{{ r.net_sales|n }}</td></tr>{% endfor %}
</tbody></table>"""


@plan.get("/money")
def money():
    try:
        version = _version()
        return _page(MONEY, title="Revenue bridge", active="money", versions=reads.versions(), version=version, b=reads.bridge(version), extra="")
    except Busy as e:
        return _busy("Revenue bridge", e)


# ---- reconciliation: the gap to the reference version ----
GAP = VERSION_PICKER + """
<h1>Gap to reference<small>{{ version }} against {{ g.reference }} · the difference the cycle exists to close</small></h1>
{% if not g.reference %}<p class="lede">This version names no reference.</p>{% else %}
<h2>By period</h2>
<table><thead><tr><th>Period</th><th class="n">Plan cases</th><th class="n">Reference cases</th><th class="n">Gap</th><th class="n">Plan net sales</th><th class="n">Reference net sales</th><th class="n">Gap</th></tr></thead><tbody>
{% for r in g.by_period %}<tr><td>{{ r.period }}</td><td class="n">{{ r.plan_cases|n }}</td><td class="n">{{ r.reference_cases|n }}</td><td class="n">{{ r.cases_gap|n }}</td><td class="n">{{ r.plan_net_sales|n }}</td><td class="n">{{ r.reference_net_sales|n }}</td><td class="n">{{ r.net_sales_gap|n }}</td></tr>{% endfor %}
</tbody></table>
<h2>By material and account<span class="count">largest shortfall first</span></h2>
<table><thead><tr><th>Material</th><th>Account</th><th class="n">Plan cases</th><th class="n">Reference cases</th><th class="n">Gap</th><th class="n">Plan net sales</th><th class="n">Reference net sales</th><th class="n">Gap</th></tr></thead><tbody>
{% for r in g.by_material %}<tr><td>{{ r.standard_material }}</td><td>{{ r.account_code }}</td><td class="n">{{ r.plan_cases|n }}</td><td class="n">{{ r.reference_cases|n }}</td><td class="n">{{ r.cases_gap|n }}</td><td class="n">{{ r.plan_net_sales|n }}</td><td class="n">{{ r.reference_net_sales|n }}</td><td class="n">{{ r.net_sales_gap|n }}</td></tr>{% endfor %}
</tbody></table>{% endif %}"""


@plan.get("/gap")
def gap():
    try:
        version = _version()
        return _page(GAP, title="Gap to reference", active="gap", versions=reads.versions(), version=version, g=reads.gap(version), extra="")
    except Busy as e:
        return _busy("Gap to reference", e)


# ---- financial planning: the revenue forecast, the versions laid over one another in net sales ----
@plan.get("/revenue")
def revenue():
    """Net sales by fiscal year across its periods, per week: invoiced, the latest view and its reference over one another,
    read against the reference only on the periods both value; at the plan or any node of either structure, the level
    below as a split. Nothing typed here."""
    try:
        version = _version(); v = reads.version(version) or {}
        years = reads.fiscal_years(version)
        fy = request.args.get("fy", type=int)
        if fy not in years:
            fy = int(v.get("fiscal_year") or 0) if int(v.get("fiscal_year") or 0) in years else (years[0] if years else 0)
        dim = request.args.get("dim") if request.args.get("dim") in ("customer", "material") else "customer"
        node = request.args.get("node") or "ALL"
        grain = request.args.get("grain") if request.args.get("grain") in ("period", "week") else "period"
        def L(**kw): return url_for("plan.revenue", **{"version": version, "fy": fy, "dim": dim, "node": node, "grain": grain, **kw})
        def at(n): return {"customer": n} if dim == "customer" else {"material": n}
        series = reads.demand_series(version, fy, **at(node))               # by period: the table, the tiles, the like-for-like
        shown = series if grain == "period" else reads.demand_series(version, fy, grain="week", **at(node))
        lfl = reads.like_for_like(series)
        both = set(lfl["keys"])
        table = []
        for k in series["keys"]:
            x, r, p = series["view"].get(k["k"]), series["ref"].get(k["k"]), series["py"].get(k["k"])
            row = {"label": k["say"].split(" · ")[0], "weeks": k["weeks"], "source": x["source"] if x else None,
                   "view_rate": x["rate"] if x else None, "ref_rate": r["rate"] if r else None, "py_rate": p["rate"] if p else None,
                   "view": x["total"] if x else None, "ref": r["total"] if r else None, "gap": None, "gap_d": None}
            if k["k"] in both:
                row["gap"] = x["total"] - r["total"]; row["gap_d"] = _d(x["total"], r["total"])
            table.append(row)
        d = {"py": _d(lfl["year"], lfl["py_year"]), "lfl": _d(lfl["view"], lfl["ref"])}
        split = []
        for ch in reads.node_children(dim, node):
            cs = reads.demand_series(version, fy, **at(ch["code"]))
            if cs["view"]:
                cl = reads.like_for_like(cs)
                split.append({**ch, "href": L(node=ch["code"]), "lfl": cl, "py_d": _d(cl["year"], cl["py_year"]), "gap_d": _d(cl["view"], cl["ref"])})
        split.sort(key=lambda c: -c["lfl"]["year"])
        level = split[0]["level"] if split else ""
        split_of = {"planning_unit": "unit", "account": "account", "category": "category", "product": "product"}.get(level, level.replace("_", " ") or "level below")
        ref_id = series["ref_id"] if series["ref"] else None              # a reference that does not carry this year is not shown against it
        ref_kind = (reads.version(ref_id) or {}).get("cycle") if ref_id else (f"{series['ref_id']} does not carry FY{fy}" if series["ref_id"] else None)
        drill = {"dim": dim, "label": reads.node_label(dim, node), "path": [{**n, "href": L(node=n["code"])} for n in reads.node_path(dim, node)],
                 "other": L(dim=("material" if dim == "customer" else "customer"), node="ALL")}
        return _page(dashboard.REVENUE_PAGE, title="Revenue forecast", active="revenue", width="none", version=version, versions=reads.versions(), fy=fy,
                     years=[{"fy": y, "href": L(fy=y)} for y in years], grain=grain, grains=[{"label": g, "on": g == grain, "href": L(grain=g)} for g in ("period", "week")],
                     series=series, chart=dashboard.chart(shown, fy), lfl=lfl, d=d, table=table, split=split, split_of=split_of, drill=drill,
                     ref_id=ref_id, ref_kind=ref_kind)
    except Busy as e:
        return _busy("Revenue forecast", e)


# ---- the rungs named but not yet built ----
RUNGS = {
    "standard": ("Standard by plant", "The standard cost of every material at every plant for the version's standard year, derived from the routes, the BOM and the cost inputs; a new plant through to a new standard and the transition."),
    "landed": ("Landed cost", "The distributor's standard: supplier price × FX + freight + duty by source; purchase price, FX and freight rate as the three variances."),
    "pnl": ("P&L plan", "Every line of the commercial P&L by cause — volume, price, mix, promotion, cost — at standard, with the planned variances beneath."),
    "balance": ("Balance sheet plan", "Every line rolled from opening actuals by one declared movement source; three identities run as a check on every version."),
    "capex": ("Capital", "Projects entered, approved and phased; the maintenance deferral that raises unplanned downtime into the capacity analysis."),
    "cycle": ("Period control", "Periods opened and closed; the latest closed period that every version's baseline is read from."),
    "proof": ("Proof", "The identities and reconciliations that let a number be trusted: stack to total, gross to net, plan to reference."),
    "supply": ("Supply plan", "Unconstrained demand met from stock, production and purchases by week and node; the rough-cut against the lines; what cannot be made and the shaping that answers it."),
    "capacity": ("Capacity", "The machine, labour and storage registers against the load the supply plan puts on them; planned downtime and the unplanned downtime a deferred overhaul raises."),
    "inventory": ("Inventory", "Projected stock by node and week against policy; weeks of cover; the working capital the plan ties up."),
    "scenarios": ("Scenarios", "A named set of deltas read against a version; promoted into the latest view by decision, or dropped."),
    "review": ("Management review", "The one set of numbers the business runs on: plan against reference, the decisions taken, the assumptions in force."),
}


@plan.get("/rung/<slug>")
def rung(slug: str):
    title, says = RUNGS.get(slug, ("Not here", "No such page."))
    return _page(f"<h1>{title}<small>named, not yet built</small></h1><p class='lede'>{says}</p>", title=title, active=slug)


# ---- registers ----
def _table(rows: list[dict], cols: list[str]) -> str:
    head = "".join(f"<th>{c}</th>" for c in cols)
    body = "".join("<tr>" + "".join(f"<td>{'' if r.get(c) is None else r.get(c)}</td>" for c in cols) + "</tr>" for r in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


@plan.get("/events")
def events():
    try:
        rows = reads.events()
        cols = ["event_id", "version_id", "account_code", "promo_group_code", "window_start", "window_end", "mechanic", "uplift_pct", "dip_pct", "tpr_per_case", "scan_funding_per_case", "fixed_fee", "status", "owner"]
        return _page("<h1>Promotions<small>the calendar: dated windows, the uplift in the window and the dip after</small></h1>" + _table(rows, cols), title="Promotions", active="events")
    except Busy as e:
        return _busy("Promotions", e)


TERMS = """<h1>Terms<small>the instruments in force, by account</small></h1>
{% for a in groups %}<h2>{{ a.account_name }}<span class="count">{{ a.account_code }} · {{ a.rows|length }} instrument{{ '' if a.rows|length == 1 else 's' }}</span></h2>
<table><thead><tr><th>Instrument</th><th>Kind</th><th>Driver basis</th><th class="n">Rate</th><th>Flow position</th><th>Conditionality</th><th>Settlement</th><th>Material scope</th><th>Valid from</th><th>Valid to</th><th>Note</th></tr></thead><tbody>
{% for r in a.rows %}<tr><td>{{ r.instrument_code }}</td><td>{{ r.instrument_kind }}</td><td>{{ r.driver_basis }}</td><td class="n">{{ r.rate }}</td><td>{{ r.flow_position }}</td><td>{{ r.conditionality }}</td><td>{{ r.settlement_timing }}</td><td>{{ r.scope_material or '' }}</td><td>{{ r.valid_from }}</td><td>{{ r.valid_to or '' }}</td><td>{{ r.note or '' }}</td></tr>{% endfor %}
</tbody></table>{% endfor %}"""


@plan.get("/terms")
def terms():
    try:
        names = {a["account_code"]: a["account_name"] for a in q("select account_code, account_name from dims.dim_account")}
        groups: dict[str, dict] = {}
        for r in reads.terms():
            g = groups.setdefault(r["account_code"], {"account_code": r["account_code"], "account_name": names.get(r["account_code"], r["account_code"]), "rows": []})
            g["rows"].append(r)
        return _page(TERMS, title="Terms", active="terms", groups=sorted(groups.values(), key=lambda g: g["account_name"]))
    except Busy as e:
        return _busy("Terms", e)


PRICE_LISTS = """<h1>Price lists<small>list price per case in the list's currency, effective-dated; an increase is a dated event</small></h1>
{% for pl in lists %}<h2>{{ pl.price_list }}<span class="count">{{ pl.currency }} · {{ pl.materials|length }} materials · on it: {% for a in pl.accounts %}{{ a.account_name }}{{ ', ' if not loop.last }}{% else %}no account{% endfor %}</span></h2>
{% if pl.events %}<table><thead><tr><th>Increase event</th><th>Effective</th><th class="n">Materials repriced</th><th class="n">Average change</th></tr></thead><tbody>
{% for e in pl.events %}<tr><td>{{ e.event }}</td><td>{{ e.effective }}</td><td class="n">{{ e.n }}</td><td class="n">{{ e.avg|pct1s }}</td></tr>{% endfor %}
</tbody></table>{% endif %}
<table><thead><tr><th>Material</th><th class="n">Price before</th><th>Valid</th><th class="n">Price in force</th><th>Valid</th><th class="n">Change</th><th>Event</th></tr></thead><tbody>
{% for m in pl.materials %}{% set c = m.current %}{% set p = m.prior %}<tr><td>{{ m.material_name }} <span class="muted">{{ m.material_code }}</span></td>
<td class="n">{{ p.price_per_case|n(2) if p else '' }}</td><td>{% if p %}{{ p.valid_from }} to {{ p.valid_to or 'open' }}{% endif %}</td>
<td class="n">{{ c.price_per_case|n(2) }}</td><td>{{ c.valid_from }} to {{ c.valid_to or 'open' }}</td>
<td class="n">{{ m.change|pct1s if m.change is not none else '' }}</td><td>{{ c.price_event or '' }}</td></tr>{% endfor %}
</tbody></table>{% endfor %}"""


@plan.get("/price_lists")
def price_lists():
    try:
        return _page(PRICE_LISTS, title="Price lists", active="pricelists", lists=reads.price_lists())
    except Busy as e:
        return _busy("Price lists", e)


@plan.get("/versions")
def versions():
    try:
        cols = ["version_id", "version_kind", "cycle", "fiscal_year", "horizon_start", "horizon_end", "calendar_variant", "standard_version", "reference_version", "status", "owner", "named_on"]
        return _page("<h1>Versions<small>named, owned, frozen or open — the plan is a stack of entries on a version</small></h1>" + _table(reads.versions(), cols), title="Versions", active="versions")
    except Busy as e:
        return _busy("Versions", e)


# ---- forecast accuracy ----
@plan.get("/accuracy")
def accuracy():
    try:
        lag = int(request.args.get("lag") or 3)
        lags = [r["lag"] for r in q("select distinct lag from plan.forecast_accuracy order by 1")]
        ps = reads.accuracy_periods(lag)
        last = (reads.accuracy(lag, ps[-12:]) or [{}])[0]; prior = (reads.accuracy(lag, ps[-24:-12]) or [{}])[0]
        d = None if last.get("accuracy") is None or prior.get("accuracy") is None else last["accuracy"] - prior["accuracy"]
        return _page(dashboard.ACCURACY_PAGE, title="Forecast accuracy", active="accuracy", lag=lag, lags=lags, last=last, prior=prior, d=d,
                     tree=reads.accuracy_tree(lag, ps[-12:]), units=reads.accuracy(lag, ps[-12:], "planning_unit_name"), periods=reads.accuracy(lag, ps[-12:], "period"))
    except Busy as e:
        return _busy("Forecast accuracy", e)


# ---- run ----
RUN = """<h1>Run and health<small>load the landing, evaluate every model and every check</small></h1>
<div class="cards"><div class="card stat"><b>{{ pending|length }}</b><span>files placed since the last run</span></div>
<div class="card stat"><b>{{ receipts|length }}</b><span>recent acts</span></div></div>
<form method="post" action="{{ url_for('plan.run_now') }}"><button class="primary" {{ 'disabled' if not may_run }}>Run</button>
<span class="hint">{{ 'as ' + who if may_run else who + ' does not hold run.plan' }}</span></form>
{% if run_log %}<h2>Last run</h2><pre>{{ run_log }}</pre>{% endif %}
{% if pending %}<h2>Waiting for the next run</h2><table><thead><tr><th>File</th></tr></thead><tbody>{% for p in pending %}<tr><td><code>{{ p.name }}</code></td></tr>{% endfor %}</tbody></table>{% endif %}
{% if health %}<h2>Health</h2><table><thead><tr><th>Worklist</th><th>Severity</th><th class="n">Items</th><th>What to do</th><th>Whose</th></tr></thead><tbody>
{% for h in health %}<tr><td>{{ h.name }}</td><td><span class="severity">{{ h.severity }}</span></td><td class="n">{{ h.items }}</td><td>{{ h.what_to_do }}</td><td>{{ h.whose }}</td></tr>{% endfor %}</tbody></table>{% endif %}
<h2>Recent acts</h2><table><thead><tr><th>At</th><th>Act</th><th>By</th><th>Subject</th><th>Placed</th></tr></thead><tbody>
{% for r in receipts %}<tr><td>{{ r.at }}</td><td>{{ r.act }}</td><td>{{ r.by }}</td><td><code>{{ r.subject }}</code></td><td class="{{ 'ok' if r.placed else 'no' }}">{{ '✓' if r.placed else '✕' }}</td></tr>{% endfor %}</tbody></table>"""


def _may_run(who: str) -> bool:
    return roles.may(who, "run.plan")


@plan.get("/run")
def run():
    who = _who() if _principals_ok() else ""
    try:
        h = health(q, HEALTH)
    except Busy:
        h = []
    return _page(RUN, title="Run and health", active="run", may_run=bool(who) and _may_run(who), run_log=session.run_log,
                 pending=ENTRIES.pending(), receipts=receipts.recent(12), health=h)


def _principals_ok() -> bool:
    try:
        return bool(roles.principals())
    except Busy:
        return False


@plan.post("/run")
def run_now():
    who = _who()
    if not _may_run(who):
        session.say(f"{who} may not run the plan", False)
        return redirect(url_for("plan.run"))
    log = Runner().run()
    session.run_log = log
    ok = "✗" not in log
    receipts.act("run", who, "plan", ok, "run completed" if ok else "run stopped — see the log")
    session.say("run completed — the pages read the new plan" if ok else "run stopped; the log says where", ok)
    return redirect(url_for("plan.run"))


def main() -> None:
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[plan])
    chassis_app.serve(app, port=8010, watch=pathlib.Path(__file__).parent)


if __name__ == "__main__":
    main()
