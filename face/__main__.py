"""The plan's pages. Every act is a file placed in the landing by the chassis's writer and a receipt; every number shown
is what the last run said. The checks an entry must pass to be placed live here — the chassis judges them, it does not
know them."""
from __future__ import annotations

import datetime as dt
import math
import pathlib

import duckdb as _duckdb
from collections import defaultdict

from flask import Blueprint, current_app, g, has_request_context, redirect, request, url_for

from calc import finance as calc_finance
from chassis import app as chassis_app, door, receipts, working
from chassis.landing import LogLanding
from chassis.run import Runner, attention, health
from chassis import warehouse as _warehouse
from chassis.warehouse import Busy, q

from . import ENTRY_COLUMNS, HEALTH, MAP_FLOWS, MAP_NODES, FINANCE_COLUMNS, PRICE_LIST_COLUMNS, SHELL, SUBMISSION_COLUMNS, TERMS_COLUMNS, roles, session
from . import reads
from . import dashboard
from . import promotions
from . import forecast as fcst
from . import doors
from . import finance_live
from . import costs
from . import schedule
from . import headcount
from .words import said

plan = Blueprint("plan", __name__)


# ---- one warehouse connection per request, not per question ----
# The chassis opens and closes the file for every query so a run can take it whenever it needs it; on a 250 MB file that
# open is ~50 ms, and a page asks dozens of questions. Within a request the face keeps one read-only connection and
# closes it when the request ends — a run still finds the file free between requests.
class _RequestConnection:
    def __init__(self, con):
        self.con = con

    def execute(self, *a):
        return self.con.execute(*a)

    def close(self):                     # the request's teardown closes it
        pass


class _PerRequest:
    IOException = _duckdb.IOException

    def connect(self, path, read_only=False):
        if not (read_only and has_request_context()):
            return _duckdb.connect(path, read_only=read_only)
        if g.get("_warehouse") is None:
            g._warehouse = _duckdb.connect(path, read_only=True)
        return _RequestConnection(g._warehouse)


_warehouse.duckdb = _PerRequest()


@plan.teardown_app_request
def _close_warehouse(_exc):
    con = g.pop("_warehouse", None)
    if con is not None:
        con.close()
ENTRIES = LogLanding("plan", "layer_entry", ENTRY_COLUMNS)
TERMS_LANDING = LogLanding("plan", "reg_terms", TERMS_COLUMNS)
PRICES_LANDING = LogLanding("history", "price_list", PRICE_LIST_COLUMNS)
SUBMISSIONS = LogLanding("plan", "reg_submission", SUBMISSION_COLUMNS)
FINANCE = LogLanding("plan", "reg_finance_overlay", FINANCE_COLUMNS)
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
    acts = ctx.pop("receipt_acts", None)            # a page showing a receipt names the acts it belongs to
    if acts is not None and ctx.get("last") and (ctx["last"].get("by") != who or not any(ctx["last"].get("act", "").startswith(x) for x in acts)):
        ctx["last"] = None
    return SHELL.page(body, who=who, held=held, principals=principals, flash=session.flash(), **ctx)


def _ctx() -> dict:
    """The context in force: version, fy, customer, material — from the address, or the person's defaults."""
    return SHELL.chosen(_who())


def _version() -> str | None:
    return _ctx()["version"]


def _z(x: float | None, scale: float = 1, d: int = 0) -> float | None:
    """A value that rounds to zero at the digits shown is zero, not minus zero (a run-out leaves -0.0 cells)."""
    return x if x is None or round(x / scale, d) != 0 else 0.0


def _n(x: float | None, d: int = 0) -> str:
    return "" if x is None else f"{_z(x, 1, d) + 0.0:,.{d}f}"


plan.add_app_template_filter(_n, "n")
plan.add_app_template_filter(lambda x: f"{_z(x) + 0.0:+,.0f}" if _z(x) else "0", "signed")
plan.add_app_template_filter(lambda x: "" if x is None else (f"{x / 1e6:,.2f}M" if abs(x) >= 1e6 else f"{_z(x, 1e3) / 1e3 + 0.0:,.0f}k"), "k")
plan.add_app_template_filter(lambda x: "" if x is None else f"${_z(x, 1e6, 1) / 1e6 + 0.0:,.1f}M", "m")
plan.add_app_template_filter(lambda x: "" if x is None else (f"${x / 1e6:,.2f}M" if abs(x) >= 1e6 else f"${_z(x, 1e3) / 1e3 + 0.0:,.0f}k"), "aud")
plan.add_app_template_filter(lambda x: "" if x is None else f"{x:+.1%}", "pct")
plan.add_app_template_filter(lambda x: "" if x is None else f"{x:.1%}", "pct1")
plan.add_app_template_filter(lambda x: "" if x is None else f"{x:+.1%}", "pct1s")
plan.add_app_template_filter(lambda x: "" if x is None else f"{x * 100:+.1f} pp", "pp")
plan.add_app_template_filter(lambda x: "" if x is None else ("up" if x > 0.0005 else "down" if x < -0.0005 else "flat"), "dir")
plan.add_app_template_filter(lambda x: "" if x is None else ("high" if x > 0.02 else "low" if x < -0.02 else ""), "hl")

# a page's own controls; the version, year, customer and material are the context, chosen once in the navigation and kept
# by every form here (DEC-20261113-07)
TOOLBAR = """{% if extra %}<form class="toolbar" method="get">{{ context_fields() }}{{ extra|safe }}</form>{% endif %}"""


def _busy(title: str, e: Busy) -> str:
    return _page(f"<h1>{title}</h1><p class='lede'>{e}</p>", title=title)


# ---- the role's home: what the processes you reach expect of you ----
HOME = """<h1>{{ who }}<small>what the processes you reach expect of you today · <a href="{{ url_for('plan.map') }}">the map of the plan</a></small></h1>
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
            pend = _pending()
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
        if r.get("door") in doors.PAGES:
            return url_for(doors.PAGES[r["door"]]) + f"#{r['kind']}-{r['item_code']}-{r['scope_code']}"
        if r.get("event_id"):
            return url_for("plan.events") + f"#{r['event_id']}"
        if r.get("entry_id"):
            return url_for("plan.entries", version=v, layer=r.get("layer_no") or "", withdrawn=1) + f"#{r['entry_id']}"
        if r.get("ship_to_code"):
            acct = reads.account_of_ship_to(r["ship_to_code"])
            return url_for("plan.demand", version=v, customer=acct) if acct else url_for("plan.demand", version=v)
        if r.get("subject"):
            node = r.get("node"); lvl = r.get("level")
            unit = node if lvl == "planning_unit" else (reads.unit_of_account(node) if lvl == "account" else None)
            return url_for("plan.submissions", version=v, customer=unit) if unit else url_for("plan.submissions", version=v)
    except Exception:
        return None
    return None


def _mine(who: str, held: set[str]) -> list[dict]:
    """What the last run routed to this person, plus the one thing the face itself can see: files placed and not yet run."""
    rows = [{"item": a["row"].get("item") or a["surface"], "name": a["name"], "what_to_do": a["what_to_do"], "severity": a["severity"], "href": _where(a["surface"], a["row"])}
            for a in attention(q, who, HEALTH)]
    if "register.promo_calendar.maintain" in held:
        for f in promotions.waiting():
            rows.append({"item": f"{f['file_id']} from the promotions system: {len(f['events'])} events waiting to be taken in", "name": "promotions sender",
                         "what_to_do": "take the file in on the promotions page", "severity": "ACTION", "href": url_for("plan.events")})
    if "layer.1.enter" in held:
        _, mine = _fcst_accounts(who)
        for r in fcst.waiting(set(mine)):
            left = ", ".join(a["account_code"] for a in r["left"])
            rows.append({"item": f"{r['run_id']} from the forecasting system: waiting to be taken in for {left}", "name": "forecasting system",
                         "what_to_do": "read it against our calculation and take it in for your accounts on the statistical forecast page", "severity": "ACTION",
                         "href": url_for("plan.forecast") + "#sender"})
    if "run.plan" in held:
        for f in _pending():
            rows.append({"item": f"{f.name} placed, not yet in the plan", "name": "landing", "what_to_do": "run the plan to take it in", "severity": "PENDING", "href": url_for("plan.run")})
    return rows


def _pending() -> list[pathlib.Path]:
    """Every file any act has placed since the last run, across the landing's tables."""
    return ENTRIES.pending() + SUBMISSIONS.pending() + promotions.pending() + TERMS_LANDING.pending() + PRICES_LANDING.pending() + fcst.pending() + doors.ACTS.pending() + FINANCE.pending() \
        + [f for scope in SCOPED.values() for f in scope["pending"]() if scope["pending"] is not FINANCE.pending]


def _d(a: float | None, b: float | None) -> float | None:
    return None if not a or not b else a / b - 1


def _views(secs, held: set[str]) -> list[tuple[str, str, str]]:
    """Every page a person reaches in an area: an entry's own page, or each of its tabs they see — (key, label, href)."""
    out = []
    for s in secs:
        if s.tabs:
            out += [(t.key, t.label, url_for(t.endpoint, **t.args)) for t in s.shown_tabs(held)]
        else:
            out.append((s.key, s.label, s.href(held)))
    return out


def _head(who: str, held: set[str]) -> str:
    """The home page of someone who submits the demand plan: the plan as a whole, read from the run — tiles, the year by
    period, the tree by category, the units and their submissions, the ladder and the one act at its end."""
    version = _version(); v = reads.version(version) or {}
    fy = int(_ctx().get("fy") or v.get("fiscal_year") or 0)
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
    actions = [{"label": "Map", "href": url_for("plan.map"), "says": "the whole"}] + [{"label": label, "href": href, "says": a.label}
               for p, areas in SHELL.reach(held) if p.key == "ibp" for a, secs in areas for key, label, href in _views(secs, held)
               if key in ("demand", "submissions", "accuracy", "entries", "gap", "versions", "run")]
    links = {"demand": url_for("plan.demand", version=version), "money": url_for("plan.gap", version=version), "accuracy": url_for("plan.accuracy"),
             "submissions": url_for("plan.submissions", version=version), "versions": url_for("plan.versions")}
    for u in units:
        u["href"] = url_for("plan.submissions", version=version, customer=u["code"])
    # the figure's drill: a node of one structure, its children as small multiples beneath
    # read per week (the 4-4-5 calendar steps a period total every third period); the grain and measure travel with every link
    dim = request.args.get("dim") if request.args.get("dim") in ("customer", "material") else "customer"
    node = request.args.get("node") or "ALL"
    grain = request.args.get("grain") if request.args.get("grain") in ("period", "week") else "period"
    leaf = dim == "material" and reads.is_material(node)             # cases mean one thing at a material and nothing above it
    measure = "cases" if leaf and request.args.get("measure") == "cases" else "net_sales"
    def L(**kw): return url_for("plan.home", **{"dim": dim, "node": node, "grain": grain, "measure": measure, **kw})
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
    return _page(dashboard.HEAD_PAGE, title="Demand", active=None, width="none", uses=("version", "fy"), links=links, drill=drill, fig=fig, version=version, versions=reads.versions(), fy=fy, lag=lag,
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
                             "sections": [{"label": s.label, "href": s.href(held)} for s in secs]} for a, secs in areas]}
                 for p, areas in SHELL.reach(held)]
        return _page(HOME, title="Home", active=None, reach=reach, mine=_mine(who, held))
    except Busy as e:
        return _busy("Home", e)


# ---- the demand plan ----
DEMAND = TOOLBAR + """
<h1>Demand plan<small>{{ version }} · unconstrained · cases by standard material · {{ where }} · {{ d.n_actual }} closed periods as actuals, then the plan · totals by fiscal year with comparatives</small></h1>
{% if editable %}<p class="hint">Cells are open: click one, type the total you want, Enter, give a reason. What is placed is an entry on layer {{ layer }} for the difference; the cell shows the run's number until the next run takes it in.</p>
{% elif can_enter %}<p class="hint">Choose an account as the customer in the context to open the cells for input.</p>{% endif %}
<div class="wide"><table class="plan tree" {% if editable %}data-cells-post="{{ url_for('plan.cell') }}" data-cells-reasons="reasons"{% endif %}><thead>
<tr><th rowspan="2" class="sticky">Material</th><th colspan="{{ d.periods|length }}" style="text-align:center">Periods</th>
{% for c in d.comps %}<th colspan="{{ 1 + (1 if c.py else 0) + (1 if c.ref else 0) }}" style="text-align:center;border-left:1px solid var(--rule)">FY{{ c.fy }}</th>{% endfor %}<th class="n" rowspan="2">Horizon</th></tr>
<tr>{% for pp in d.periods %}<th class="n {{ 'actual' if d.source_of[pp] == 'actual' }}" title="{{ pp }}{{ ' · actual' if d.source_of[pp] == 'actual' }}">{{ pp[2:4] }}·{{ pp[5:] }}</th>{% endfor %}
{% for c in d.comps %}<th class="n" style="border-left:1px solid var(--rule)">Total</th>{% if c.py %}<th class="n" title="same periods, prior fiscal year: shipments where closed, else this view">PY</th>{% endif %}{% if c.ref %}<th class="n" title="{{ d.ref_id }}">{{ d.ref_id }}</th>{% endif %}{% endfor %}</tr></thead><tbody>
{% macro row(r, cls, parent, tog, id, label) %}<tr class="{{ cls }}"{% if parent %} data-parent="{{ parent }}"{% endif %}><td class="sticky">{% if tog %}<button type="button" class="tog" data-id="{{ id }}"></button>{% endif %}{{ label }}{% if cls == 'l2' %} <span class="muted">{{ r.material }}</span>{% endif %}</td>{% for c in r.cells %}{% set pp = d.periods[loop.index0] %}{% set key = r.material ~ '|' ~ pp %}
<td class="n {{ 'actual' if d.source_of[pp] == 'actual' }} {{ 'has-pending' if key in pending }}" {% if editable and cls == 'l2' and d.source_of[pp] != 'actual' %}data-cell='{"version": "{{ version }}", "layer": {{ layer }}, "material": "{{ r.material }}", "account": "{{ account }}", "period": "{{ pp }}"}' data-current="{{ c or 0 }}"{% endif %}>{{ c|n }}{% if key in pending %}<span class="pending" title="placed, not yet run">{{ pending[key]|signed }} pending</span>{% endif %}</td>{% endfor %}
{% for b in r.blocks %}<td class="n" style="border-left:1px solid var(--rule);font-weight:500">{{ b.total|n }}</td>{% if d.comps[loop.index0].py %}<td class="n muted">{{ b.py|n }}</td>{% endif %}{% if d.comps[loop.index0].ref %}<td class="n muted">{{ b.ref|n }}</td>{% endif %}{% endfor %}<td class="n" style="font-weight:600">{{ r.total|n }}</td></tr>{% endmacro %}
{% for c in d.groups %}{{ row(c, 'l0', None, True, c.code, c.material) }}
{% for p in c.children %}{{ row(p, 'l1', c.code, True, p.code, p.material) }}
{% for m in p.children %}{{ row(m, 'l2', p.code, False, None, m.label) }}{% endfor %}{% endfor %}{% endfor %}
{{ row(d.totals, 'total', None, False, None, 'Total') }}
</tbody></table></div>
<p class="hint">Categories and products are sums of the standard materials beneath them and are read-only; open a category, then a product, to reach its materials{% if editable %} — only a material's open periods take input{% endif %}. Shaded periods are closed and read from shipments; the rest is the plan. PY is the same periods a year earlier — shipments where that year is closed, otherwise this view; {{ d.ref_id }} is the reference version where its horizon overlaps.</p>
<h2>Plan by layer and fiscal year</h2>
<table><thead><tr><th>Fiscal year</th><th class="n">1 Baseline</th><th class="n">2 Adjustment</th><th class="n">4 Distribution</th><th class="n">6 Promotions</th><th class="n">7 Innovation</th><th class="n">8 Exit</th><th class="n">Plan</th></tr></thead><tbody>
{% for r in layers %}<tr><td>FY{{ r.fiscal_year }}</td><td class="n">{{ r.l1|n }}</td><td class="n">{{ r.l2|n }}</td><td class="n">{{ r.l4|n }}</td><td class="n">{{ r.l6|n }}</td><td class="n">{{ r.l7|n }}</td><td class="n">{{ r.l8|n }}</td><td class="n">{{ r.cases|n }}</td></tr>{% endfor %}
</tbody></table>
{% if editable %}<script type="application/json" id="reasons">{{ reasons_json|safe }}</script><script src="{{ url_for('static', filename='cells.js') }}"></script>{% endif %}
<style>.wide{overflow-x:auto;margin:0 -1rem;padding:0 1rem}table.plan{width:max-content;min-width:100%;font-size:.82rem}table.plan th,table.plan td{padding:.35rem .5rem}
table.plan .actual{background:var(--soft)}table.plan .sticky{position:sticky;left:0;background:var(--panel);z-index:1}table.plan th.sticky{z-index:2;background:var(--soft)}table.plan tr.l0 td{font-weight:600}</style><style>""" + dashboard.TREE_CSS + """</style>""" + dashboard.TREE_JS


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
        who = _who(); c = _ctx(); version = c["version"]
        customer, material = c.get("customer") or "ALL", c.get("material") or "ALL"
        account = customer if reads.is_account(customer) else None               # cells open at an account; a unit or all reads summed
        v = reads.version(version) or {}
        enterable = [n for n in roles.layers_enterable(who) if n != 1]           # layer 1 is computed on an open version; a typed change is an adjustment
        layer = int(request.args.get("layer") or (enterable[0] if enterable else 0))
        can_enter = bool(enterable) and v.get("status") == "open"
        editable = can_enter and bool(account) and layer in enterable
        reasons = [{"code": r["reason_code"], "says": r["description"]} for r in reads.reasons() if str(layer) in r["layers"].split(",")] or \
                  [{"code": r["reason_code"], "says": r["description"]} for r in reads.reasons()]
        extra = ""
        if can_enter:
            names = {l["layer_no"]: l["layer_name"] for l in reads.layers()}
            extra += ('<label>enter as layer<select name="layer" onchange="this.form.submit()">'
                      + "".join(f'<option value="{n}" {"selected" if n == layer else ""}>{n} {names.get(n, "")}</option>' for n in enterable) + "</select></label>")
        where = " × ".join(reads.node_label(dim, n) for dim, n in (("customer", customer), ("material", material)) if n != "ALL") or "all customers × all materials"
        return _page(DEMAND, title="Demand plan", active="demand", width="100%", versions=reads.versions(), version=version, account=account, where=where,
                     d=reads.demand(version, customer, material), layers=reads.by_layer(version, customer, material), extra=extra,
                     editable=editable, can_enter=can_enter, layer=layer, reasons_json=json.dumps(reasons), pending=_pending_cells(version, account))
    except Busy as e:
        return _busy("Demand plan", e)


# ---- entries ----
ENTRIES_PAGE = TOOLBAR + """
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
                     periods=reads.horizon(reads.default_version() or ""), last=session.last, receipt_acts=("enter", "withdraw"))
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
SUBMISSIONS_PAGE = TOOLBAR + """
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
        who = _who(); c = _ctx(); version = c["version"]; cust = c.get("customer") or "ALL"
        units = reads.units(); matrix = reads.submission_matrix(version)
        # the context's customer opens a unit by account: the unit itself, or an account's unit
        unit = cust if any(u["code"] == cust for u in units) else (reads.unit_of_account(cust) if cust != "ALL" and reads.is_account(cust) else None)
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
        extra = ""
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
        {"check": "who holds the verb here", "ok": holds, "says": f"{who} holds {said(verb)} at {node}" if holds else f"{who} does not hold {said(verb)} at {node}"},
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
MONEY = TOOLBAR + """
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
GAP = TOOLBAR + """
<h1>Gap to reference<small>{% if g.reference %}{{ version }} against {{ g.reference }}{% else %}{{ version }} has no reference{% endif %} · the difference the cycle exists to close</small></h1>
{% if not g.reference %}<p class="lede">{{ version }} is read against nothing — it is itself the reference a later version is read against. Choose a version that names one (a latest view) to see its gap.</p>{% else %}
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


# ---- financial planning: the financial forecast, one tab per measure, and the versions laid over one another ----
def _fy(version: str | None, v: dict) -> tuple[int, list[int]]:
    years = reads.fiscal_years(version) if version else []
    fy = int(_ctx().get("fy") or 0)
    if fy not in years:
        fy = int(v.get("fiscal_year") or 0) if int(v.get("fiscal_year") or 0) in years else (years[0] if years else 0)
    return fy, years


@plan.get("/revenue")
def revenue():
    """The financial forecast: one tab per measure of the register (?measure=volume|price|revenue|cogs|margin) — Finance's
    volume × price = revenue, cost of goods and margin, on a grid with the demand plan beneath every figure, recalculated
    as Finance types (_finance_ctx, finance_cell). Every tab is a view of the same working copy."""
    try:
        version = _version(); v = reads.version(version) or {}
        fy, _ = _fy(version, v)
        c = _ctx()
        page = {**_page_args(request.args), "version": version, "fy": fy, "customer": c.get("customer") or "ALL", "material": c.get("material") or "ALL"}
        measure = page.get("measure") if page.get("measure") in FIN_TABS else "volume"
        page["measure"] = measure
        with finance_live.COPIES.lock(_who()):
            fin = _finance_ctx(version, fy, page)
        fin["entry"] = "Cost of goods" if measure in ("cogs", "margin") else "Revenue"
        return _page(FINANCE_PAGE, title=f"{fin['entry']} · {fin['tab_label']}", active=f"fin_{measure}", width="none", version=version,
                     fy=fy, fin=fin, last=session.last, receipt_acts=("finance",), live_script=working.script())
    except Busy as e:
        return _busy("Revenue", e)


@plan.get("/revenue/versions")
def revenue_versions():
    """Net sales by fiscal year across its periods, per week: invoiced, the latest view and its reference over one another,
    read against the reference only on the periods both value; at the plan or any node of either structure, the level
    below as a split."""
    try:
        version = _version(); v = reads.version(version) or {}
        fy, _ = _fy(version, v)
        # the chart reads the context's customer × material; which structure it is split along is the page's own
        c = _ctx(); cust, mat = c.get("customer") or "ALL", c.get("material") or "ALL"
        dim = request.args.get("dim") if request.args.get("dim") in ("customer", "material") else "customer"
        node = cust if dim == "customer" else mat
        grain = request.args.get("grain") if request.args.get("grain") in ("period", "week") else "period"
        def L(**kw): return url_for("plan.revenue_versions", **{"dim": dim, "grain": grain, **kw})
        def at(n): return {"customer": n, "material": mat} if dim == "customer" else {"customer": cust, "material": n}
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
                split.append({**ch, "href": L(**{dim: ch["code"]}), "lfl": cl, "py_d": _d(cl["year"], cl["py_year"]), "gap_d": _d(cl["view"], cl["ref"])})
        split.sort(key=lambda c: -c["lfl"]["year"])
        level = split[0]["level"] if split else ""
        split_of = {"planning_unit": "unit", "account": "account", "category": "category", "product": "product"}.get(level, level.replace("_", " ") or "level below")
        ref_id = series["ref_id"] if series["ref"] else None              # a reference that does not carry this year is not shown against it
        ref_kind = (reads.version(ref_id) or {}).get("cycle") if ref_id else (f"{series['ref_id']} does not carry FY{fy}" if series["ref_id"] else None)
        other = "material" if dim == "customer" else "customer"
        across = reads.node_label(other, cust if other == "customer" else mat) if (cust if other == "customer" else mat) != "ALL" else None
        drill = {"dim": dim, "label": reads.node_label(dim, node) + (f" × {across}" if across else ""), "across": across,
                 "path": [{**n, "href": L(**{dim: n["code"]})} for n in reads.node_path(dim, node)],
                 "other": L(dim=other)}
        return _page(dashboard.REVENUE_PAGE, title="Revenue · Versions", active="fin_versions", width="none",
                     version=version, versions=reads.versions(), fy=fy,
                     grain=grain, grains=[{"label": g, "on": g == grain, "href": L(grain=g)} for g in ("period", "week")],
                     series=series, chart=dashboard.chart(shown, fy), lfl=lfl, d=d, table=table, split=split, split_of=split_of, drill=drill,
                     ref_id=ref_id, ref_kind=ref_kind)
    except Busy as e:
        return _busy("Revenue", e)


# ---- Finance's plan: volume × price = revenue, with the demand plan beneath every figure ----
# The grid recalculates as Finance types: one figure posted (chassis live.js), applied to the person's working copy by the
# same function the run uses (face/finance_live.py → calc/finance.py), and only the parts of the view it changed sent
# back. Each part below is a macro so the page and the reply render it the same way.
FIN_MACROS = """{% macro fin_tiles(fin) %}<div id="fin-tiles" class="cards tiles"><div class="card stat"><span>Finance's plan · FY{{ fin.fy }}{% if fin.unsaved_n %} · unsaved{% endif %}</span><b>{{ fin.tot.fin_rev|m }}</b><div class="small muted">{{ fin.tot.fin_vol|n }} cases at {{ fin.tot.fin_price }} a case · {{ fin.customer_label }}</div></div>
<div class="card stat"><span>The demand plan beneath</span><b>{{ fin.tot.src_rev|m if fin.tot.src_rev is not none else '—' }}</b><div class="small muted">{% if fin.tot.src_rev is not none %}{{ fin.tot.src_vol|n }} cases at {{ fin.tot.src_price }} a case · where it feeds{% else %}nothing feeds this node — Finance builds it{% endif %}</div></div>
<div class="card stat"><span>Variance, where fed</span><b>{{ fin.tot.var_rev|aud if fin.tot.var_rev is not none else '—' }}</b><div class="small delta {{ fin.tot.var_d|dir }}">{% if fin.tot.var_rev is not none %}{{ fin.tot.var_d|pct }} on the demand plan · {{ fin.tot.var_vol|signed }} cases{% else %}no fed figure to differ from{% endif %}</div></div>
<div class="card stat"><span>Built by Finance</span><b>{{ fin.tot.built_rev|m if fin.tot.built_rev else '—' }}</b><div class="small muted">{{ fin.tot.built_vol|n if fin.tot.built_vol else 'no' }} cases with no demand plan beneath</div></div></div>{% endmacro %}
{% macro fin_status(fin) %}<div id="fin-status">{% if fin.say %}<p class="flash no">{{ fin.say }}</p>{% endif %}{% if fin.unsaved_n %}<p class="hint unsaved-note"><b>{{ fin.unsaved_n }} figure{{ 's' if fin.unsaved_n != 1 }} typed and not saved</b>{% if fin.unsaved_here != fin.unsaved_n %} ({{ fin.unsaved_here }} at {{ fin.customer_label }}){% endif %} — hatched wherever {{ 'they reach' if fin.unsaved_n != 1 else 'it reaches' }}. They are yours alone until saved: Save writes them to the plan with one reason; Discard drops them.</p>{% elif fin.editable %}<p class="hint">Type a figure and press Enter or Tab: everything in this view recalculates at once — totals above, children beneath by the demand plan's shape, revenue, the variance and the year. A figure typed at a parent is written down to its children as you type it. Every tab shows the same figures. Nothing reaches the rest of the plan until you save.</p>{% elif fin.may and fin.open and fin.reading == 'finance' %}<p class="hint">{{ fin.tab_label }} is calculated, never typed: type a volume or a price on its tab, and this tab shows what it made at once.</p>{% endif %}{% if fin.n_waiting %}<p class="hint">{{ fin.n_waiting }} saved file{{ 's' if fin.n_waiting != 1 }} not yet taken in by a run — shown in the grid already.</p>{% endif %}</div>{% endmacro %}
{% macro fin_row(fin, r) %}<tbody id="fin-r-{{ r.code }}">{% for m in fin.measures %}<tr class="{{ 'first' if loop.first }} {{ 'total' if r.current and loop.first }}">
{% if loop.first %}<td rowspan="{{ fin.measures|length }}" class="node">{% if r.href %}<a href="{{ r.href }}" tabindex="-1">{{ r.label }}</a>{% else %}<b>{{ r.label }}</b>{% endif %}<div class="small muted">{{ r.level }}{% if r.built %} · {{ r.built }}{% endif %}</div></td>{% endif %}
<td class="small muted">{{ m.label }}</td>
{% for x in r.cells[m.key] %}<td class="n {{ x.cls }}"{% if x.title %} title="{{ x.title }}"{% endif %}>{% if x.input %}<input class="cell" name="{{ x.input }}" value="{{ x.value }}" inputmode="decimal" data-live='{{ x.live|tojson }}'>{% else %}{{ x.show }}{% endif %}{% if x.moved %}<span class="moved">◆</span>{% endif %}{% if x.src is not none %}<span class="src">{{ x.src }}</span>{% endif %}{% if x.built %}<span class="src">built {{ x.built }}</span>{% endif %}</td>{% endfor %}
</tr>{% endfor %}</tbody>{% endmacro %}
{% macro fin_typed(fin) %}<div id="fin-typed">{% if fin.edits %}<h2>Typed here<span class="count">{{ fin.customer_label }} × the rows above · FY{{ fin.fy }}</span></h2>
<table><thead><tr><th>Node</th><th>Period</th><th>Figure</th><th class="n">Typed</th><th class="n">At the node now</th><th class="n">Demand plan then</th><th class="n">Demand plan now</th><th>Standing</th><th>Reason</th><th>By</th></tr></thead><tbody>
{% for e in fin.edits %}<tr class="{{ 'off' if e.state != 'in_force' }}"><td>{{ e.scope_material }}</td><td>{{ e.period }}</td><td>{{ e.measure }}</td><td class="n">{{ e.typed }}</td><td class="n">{{ e.now }}</td><td class="n">{{ e.then }}</td><td class="n">{{ e.src_now }}{% if e.source_moved %} <span class="moved">◆</span>{% endif %}</td>
<td>{% if e.standing == 'unsaved' %}<span class="state unsaved">unsaved</span>{% elif e.standing == 'held' %}held{% elif e.standing == 'overwritten' %}<span class="state">changed</span> <span class="small muted">by a later figure</span>{% else %}<span class="state">{{ e.standing }}</span>{% endif %}</td><td class="small">{{ e.reason }}</td><td class="small">{{ e.entered_by }}</td></tr>{% endfor %}</tbody></table>{% endif %}</div>{% endmacro %}"""

FINANCE_PAGE = FIN_MACROS + """<h1>{{ fin.entry }}<small>FY{{ fy }} · {{ version }} · {{ fin.tab_label }} · {% if fin.entry == 'Revenue' %}Finance's volume × price = revenue{% else %}the volume typed under Revenue × the standard cost per case = cost of goods; margin = revenue − cost of goods{% endif %}, the demand plan beneath every figure</small></h1>
{{ fin_tiles(fin) }}
<div class="toolbar"><span class="small muted">{{ fin.customer_label }}{% if fin.source_of.get(fin.fc) == 'built' %} · built by Finance{% endif %} ×</span>
<span class="crumbs">{% for n in fin.path %}{% if loop.last %}<b>{{ n.label }}</b>{% else %}<a href="{{ n.href }}">{{ n.label }}</a> ▸ {% endif %}{% endfor %}</span>
<span class="seg">{% for t in fin.readings %}{% if t.on %}<b>{{ t.label }}</b>{% else %}<a href="{{ t.href }}">{{ t.label }}</a>{% endif %}{% endfor %}</span></div>
{% for say in fin.not_built %}<p class="hint notbuilt">{{ say }} Nothing on this tab is estimated: a figure that cannot be calculated yet is left empty.</p>{% endfor %}
<div class="finlive"{% if fin.editable %} data-live-post="{{ url_for('plan.finance_cell') }}" data-live-context='{{ fin.live_context|tojson }}'{% endif %}>
{{ fin_status(fin) }}
<form method="post" action="{{ url_for('plan.finance_cell') }}" id="fin-grid">{% for k, val in fin.post_keep.items() %}<input type="hidden" name="{{ k }}" value="{{ val }}">{% endfor %}
<div class="finwrap"><table class="fin"><thead><tr><th>{{ fin.row_head }}</th><th></th>{% for p in fin.periods %}<th class="n {{ 'closed' if p.closed }}"{% if p.closed %} title="a closed period — what happened is read on the actuals, nothing is planned here"{% endif %}>{{ p.label }}{% if p.closed %}<div class="small muted">closed</div>{% endif %}</th>{% endfor %}<th class="n">FY{{ fy }}</th></tr></thead>
{% for r in fin.rows %}{{ fin_row(fin, r) }}{% else %}<tbody><tr><td colspan="{{ fin.periods|length + 3 }}" class="muted">Nothing in Finance's plan at {{ fin.customer_label }} × {{ fin.path[-1].label }} in FY{{ fy }}.</td></tr></tbody>{% endfor %}
</table></div>{% if fin.editable %}<noscript><p class="hint"><button class="act">Recalculate</button> this page's script is off: every changed figure is applied at once.</p></noscript>{% endif %}</form>
<p class="hint">{% if fin.reading == 'finance' %}The small figure under each is the demand plan it is fed from{% if fin.any_built %}; a built figure has none, and where a node holds both the built part is shown on its own line{% endif %}. ◆ marks a figure whose demand plan has moved since it was typed — the figure keeps its value. A boxed figure was typed at that node; a hatched one is typed and not yet saved.{% elif fin.reading == 'source' %}The demand plan valued, where it feeds Finance's plan. Built figures have no demand plan beneath them.{% else %}Finance's plan less the demand plan, on the fed part only — a built figure has no source to differ from.{% endif %}
{% for r in fin.measures %} <b>{{ r.name }}</b>{% if r.formula %} = {{ r.formula }}{% endif %}; at a total, {{ r.rollup_says }}{% if r.typed %}; typed at a total, {{ r.breakback_says }}{% endif %}.{% endfor %} <a href="{{ url_for('plan.rules') }}#finance">How each figure is calculated</a></p>
{% if fin.may and fin.open and version %}<form method="post" action="{{ url_for('plan.finance_save') }}" class="form-row" id="fin-save">{% for k, val in fin.post_keep.items() %}<input type="hidden" name="{{ k }}" value="{{ val }}">{% endfor %}
<label class="small">reason <select name="reason_code">{% for r in fin.reasons %}<option value="{{ r.reason_code }}" {{ 'selected' if r.reason_code == fin.default_reason }}>{{ r.description }}</option>{% endfor %}</select></label>
<label class="small grow">note <input name="note" placeholder="what Finance knows that the demand plan does not"></label>
<button class="primary" onclick="this.textContent='Saving…'">Save</button><button class="act" formaction="{{ url_for('plan.finance_discard') }}">Discard</button><span class="hint">one reason for every figure not yet saved · Save writes them to {{ version }} and carries them into the plan</span></form>
{% if fin.can_add %}<form method="post" action="{{ url_for('plan.finance_start') }}" class="form-row">{% for k, val in fin.post_keep.items() %}<input type="hidden" name="{{ k }}" value="{{ val }}">{% endfor %}<b class="small">Start a material at {{ fin.customer_label }}</b>
<label class="small">material <select name="add_material"><option value="">—</option>{% for a in fin.add_materials %}<option value="{{ a.code }}">{{ a.code }} · {{ a.label }}</option>{% endfor %}</select></label>
<label class="small">period <select name="add_period">{% for p in fin.open_in_fy %}<option>{{ p }}</option>{% endfor %}</select></label>
<label class="small">cases <input name="add_volume" inputmode="decimal" size="8"></label><label class="small">net per case <input name="add_price" inputmode="decimal" size="8"></label><button class="act">Add to the grid</button></form>{% endif %}
{% elif not fin.may %}<p class="hint">Finance's figures are typed by {{ fin.holders|join(', ') or 'nobody yet' }}.</p>{% elif not fin.open %}<p class="hint">{{ version }} is {{ fin.status }} — nothing is typed on it.</p>{% endif %}
</div>
{% if last and last.act and last.act.startswith('finance') %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else ('!' if c.flag else '✕') }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}
{{ fin_typed(fin) }}
<h2>Saves<span class="count">{{ version }} · each save is one reason; releasing it returns its figures to the demand plan</span></h2>
<table><thead><tr><th>Save</th><th>When</th><th>By</th><th>Reason</th><th>Customers</th><th>Periods</th><th class="n">Figures</th><th class="n">Held</th><th class="n">◆ moved</th><th>Note</th><th></th></tr></thead><tbody>
{% for s in fin.saves %}<tr class="{{ 'off' if s.released }}"><td><code>{{ s.save_id }}</code></td><td class="small">{{ s.entered_on[:16].replace('T', ' ') }}</td><td class="small">{{ s.entered_by }}</td><td class="small">{{ s.reason or s.reason_code }}</td><td>{{ s.customers }}</td><td class="small">{{ s.period_from }}{% if s.period_to != s.period_from %} – {{ s.period_to }}{% endif %}</td>
<td class="n">{{ s.figures }}</td><td class="n">{{ s.held }}</td><td class="n">{{ s.moved or '' }}</td><td class="small">{{ s.note or '' }}</td>
<td class="acts">{% if s.released %}<span class="state">released</span>{% elif fin.may and fin.open %}<form class="inline" method="post" action="{{ url_for('plan.finance_release') }}">{% for k, val in fin.post_keep.items() %}<input type="hidden" name="{{ k }}" value="{{ val }}">{% endfor %}<input type="hidden" name="save_id" value="{{ s.save_id }}"><button class="act" onclick="this.textContent='Releasing…'">release</button></form>{% endif %}</td></tr>
{% else %}<tr><td colspan="11" class="muted">Nothing typed on {{ version }}: Finance's plan is the demand plan valued{% if fin.any_built %}, and the built accounts are empty{% endif %}.</td></tr>{% endfor %}</tbody></table>
<style>.finwrap{overflow-x:auto;margin-bottom:.6rem}table.fin td.n{vertical-align:top;white-space:nowrap}table.fin td.node{vertical-align:top;min-width:11rem}
table.fin tr.first td{border-top:1px solid var(--rule)}table.fin .src{display:block;font-size:.72rem;color:var(--muted)}table.fin td.typed{box-shadow:inset 0 0 0 1px var(--ink)}
table.fin td.unsaved{background:repeating-linear-gradient(135deg,transparent 0 5px,color-mix(in srgb,var(--muted) 14%,transparent) 5px 6px)}table.fin td.unsaved input.cell{font-style:italic}
.state.unsaved,.unsaved-note b{background:repeating-linear-gradient(135deg,transparent 0 5px,color-mix(in srgb,var(--muted) 18%,transparent) 5px 6px)}
table.fin td.closed,table.fin th.closed{color:var(--muted)}.toolbar .seg{display:inline-flex;gap:.6rem;margin-left:auto}.toolbar .seg b{font-weight:600}.notbuilt{border-left:2px solid var(--rule);padding-left:.6rem}table.fin input.cell{width:5.6rem;text-align:right;font-size:.85rem;padding:.15rem .35rem}.finlive.live-busy table.fin{cursor:progress}
.moved{font-size:.7rem;margin-left:.15rem}table.fin td.down{color:var(--muted)}.form-row{display:flex;flex-wrap:wrap;gap:.8rem;align-items:end;margin:.6rem 0}.form-row .grow{flex:1;display:flex;flex-direction:column}
.form-row label{display:flex;flex-direction:column;gap:.2rem}</style>
{% if fin.editable %}{{ live_script }}{% endif %}
"""
# the financial forecast's tabs, one per measure of the register — each a view of the same working copy, showing the
# measure with the lines it is calculated from above it where that makes it readable (caldera ambiguity #20 f)
FIN_TABS = {"volume": ["volume"], "price": ["price"], "revenue": ["revenue"], "cogs": ["volume", "std_cost", "cogs"], "margin": ["revenue", "cogs", "margin"]}
READINGS = [("finance", "Finance plan"), ("source", "Demand plan"), ("variance", "Variance")]
PAGE_KEYS = ("version", "fy", "customer", "material", "reading", "measure")      # where the financial forecast stands
_FIN_MODULE: dict = {}


def _fin_macros():
    """The grid's parts as callables — the same macros the page renders inline, so a reply matches the page."""
    env = current_app.jinja_env
    if _FIN_MODULE.get("env") is not env:
        _FIN_MODULE.update(env=env, module=env.from_string(FIN_MACROS).module)
    return _FIN_MODULE["module"]


def _div(a, b):
    return a / b if a is not None and b not in (None, 0) else None


def _figures(cs: list[dict], rules: dict, measures: list[str]) -> dict | None:
    """Finance's plan, the demand plan beneath and the variance for one node over some periods, each measure rolled up by
    its registered rule (plan.ref_grid_measure) — price is always revenue ÷ volume. A measure with nothing to read is
    None: no standard cost, no cost of goods."""
    if not cs:
        return None
    def agg(cells, m, source=False):
        return calc_finance.aggregate(cells, m, rules, source)
    fed = [c for c in cs if c["source"] == "fed"]
    built = [c for c in cs if c["source"] != "fed"]
    out = {"fin": {m: agg(cs, m) for m in measures},
           "src": {m: agg(fed, m, True) for m in measures} if fed else None,
           "built": {m: agg(built, m) for m in measures} if built and fed else None, "built_only": not fed}
    if fed:
        ff, s = {m: agg(fed, m) for m in measures}, out["src"]
        out["var"], out["var_d"] = {}, {}
        for m in measures:
            a, b = ff[m], s[m]
            if a is None and b is None:
                x = None
            elif rules[m]["rollup"] == "sum":
                x = (a or 0) - (b or 0)
            else:
                x = a - b if a is not None and b is not None else None
            out["var"][m], out["var_d"][m] = x, _div(x, b)
    return out


def _shown_as(m: str) -> str:
    return finance_live.rules()[m]["shown_as"]


def _show(m: str, x) -> str:
    if x is None:
        return ""
    how = _shown_as(m)
    return _n(x) if how == "count" else (f"{x:,.2f}" if how == "rate" else (f"{x / 1e6:,.2f}M" if abs(x) >= 1e6 else f"{_z(x, 1e3) / 1e3 + 0.0:,.1f}k"))


def _show_var(m: str, x, d) -> str:
    if x is None:
        return ""
    how = _shown_as(m)
    s = (f"{_z(x) + 0.0:+,.0f}" if how == "count" else f"{x:+,.2f}" if how == "rate" else (f"{x / 1e6:+,.2f}M" if abs(x) >= 1e6 else f"{_z(x, 1e2) / 1e3 + 0.0:+,.1f}k"))
    return s + (f" ({d:+.1%})" if d is not None and how != "rate" and abs(x) > 0.5 else "")


def _edit_title(e: dict) -> str:
    v = _show(e["measure"], e["value"])
    t = f"typed {v} on {e['entered_on'][:10]} by {e['entered_by']} — {e['reason'] or e['reason_code']}; {e['standing']}"
    if e.get("source_moved"):
        t += f" · the demand plan here was {_show(e['measure'], e['source_at_entry'])} when typed and is {_show(e['measure'], e['source_now']) or 'nothing'} now"
    return t


def _page_args(src) -> dict:
    """Where the revenue page stands, from its query, a form's hidden fields or a live post's context."""
    return {k: src.get(k) for k in PAGE_KEYS if src.get(k) not in (None, "")}


def _once(fn):
    """A read asked twice in one request — the view before and after an edit — is asked once."""
    def call(*args):
        memo = g.setdefault("_fin_reads", {})
        k = (fn.__qualname__, tuple(tuple(a) if isinstance(a, list) else a for a in args))
        if k not in memo:
            memo[k] = fn(*args)
        return memo[k]
    return call


def _finance_ctx(version: str | None, fy: int, page: dict, who: str | None = None, say: str | None = None) -> dict:
    """The grid of one tab: the material node shown and the level beneath it, at one customer node, periods across, the
    tab's lines a row — read from the person's working copy if they have one, else from Finance's plan as the last run
    left it. Every tab reads the same copy; what a line may do is read from the measure register."""
    who = who or _who(); v = _once(reads.version)(version) or {}
    rules = finance_live.rules()
    measure = page.get("measure") if page.get("measure") in FIN_TABS else "volume"
    page = {**page, "measure": measure}
    lines = FIN_TABS[measure]
    MEASURES = [{"key": m, "label": rules[m]["unit"], "name": rules[m]["label"], "typed": bool(rules[m]["breakback"]), "built": rules[m]["built"],
                 "formula": rules[m]["formula_says"], "rollup_says": rules[m]["rollup_says"], "breakback_says": rules[m]["breakback_says"]} for m in lines]
    def L(**kw): return url_for("plan.revenue", **{**page, **kw})
    customers = _once(reads.finance_customer_nodes)()
    fc = page.get("customer") or "ALL"
    fc = fc if fc in {c["code"] for c in customers} else "ALL"
    fm = page.get("material") or "ALL"
    fm = fm if fm == "ALL" or _once(reads.material_node)(fm) else "ALL"
    reading = page.get("reading") if page.get("reading") in dict(READINGS) else "finance"
    may, is_open = _once(roles.may)(who, "overlay.finance.enter"), v.get("status") == "open"
    may_type = {m: bool(rules[m]["verb"]) and _once(roles.may)(who, rules[m]["verb"]) for m in lines}
    editable = bool(version) and may and is_open and reading == "finance" and may_type[measure] and bool(rules[measure]["breakback"])     # a tab takes input in its own measure only
    kids = _once(reads.material_tree_under)(fm)
    nodes = [fm] + list(kids)
    wc = finance_live.working_copy(who, version, FINANCE) if version else None
    grid = wc.grid if wc else (finance_live.base(version, FINANCE)[1] if version else None)
    periods = [{"period": p["period"], "label": f"P{p['fiscal_period']:02d}", "closed": p["period_state"] == "CLOSED"} for p in _once(reads.fy_periods)(fy)]
    opens = set(_once(reads.open_periods)(version)) if version and is_open else set()
    buckets: dict[tuple, list] = defaultdict(list)          # (node, period) → the cells beneath it at this customer node
    if grid is not None:
        A, M = grid.accounts_under.get(fc, set()), grid.materials_under.get(fm, set())
        child_of = {m: ch for ch in kids for m in grid.materials_under.get(ch, ())}
        for p in periods:
            for k in grid.by_period.get((version, p["period"]), ()):
                if k[1] in A and k[2] in M:
                    buckets[(fm, p["period"])].append(k)
                    if k[2] in child_of:
                        buckets[(child_of[k[2]], p["period"])].append(k)
    edits = _once(reads.finance_edits_at)(version, fy, fc, nodes) if version else []
    typed: dict[tuple, dict] = {}
    for e in edits:                       # latest first: the first in force is the one standing at the cell
        if e["state"] == "in_force":
            typed.setdefault((e["scope_material"], e["period"], e["measure"]), e)
    mine = {(t.material, t.period, t.measure): t for t in (wc.typed if wc else []) if t.customer == fc}
    def over(code, period, measure) -> bool:
        """An unsaved figure typed at a node above this one (or at a customer above this one) in the period and measure."""
        under_m = grid.materials_under.get(code, {code}) if grid is not None else set()
        under_a = grid.accounts_under.get(fc, set()) if grid is not None else set()
        return any(t.period == period and t.measure == measure and (t.material, t.customer) != (code, fc)
                   and under_m <= grid.materials_under.get(t.material, {t.material}) and under_a <= grid.accounts_under.get(t.customer, set())
                   for t in (wc.typed if wc else []))
    touched = wc.touched if wc else {}
    fm_label = _once(reads.node_label)("material", fm)
    levels = {"category": "category", "product": "product", "material": "material", "all": "all materials"}
    rows = []
    for code in nodes:
        keys_by_p = {p["period"]: buckets.get((code, p["period"]), []) for p in periods}
        all_keys = [k for ks in keys_by_p.values() for k in ks]
        if code != fm and not all_keys:
            continue
        nb = sum(1 for k in all_keys if grid.cells[k]["source"] != "fed")
        lvl = kids[code]["lvl"] if code != fm else None
        has_kids = code != fm and kids[code]["has_kids"]
        row = {"code": code, "label": kids[code]["label"] if code != fm else fm_label, "current": code == fm, "href": L(material=code) if has_kids else None,
               "level": ("this node" if code == fm else levels.get(lvl, lvl or "")), "built": ("built by Finance" if nb and nb == len(all_keys) else "part built" if nb else ""),
               "cells": {m["key"]: [] for m in MEASURES}}
        for p in periods + [{"period": "FY", "closed": False}]:
            ks = all_keys if p["period"] == "FY" else keys_by_p[p["period"]]
            F = _figures([grid.cells[k] for k in ks], rules, lines)
            for m in MEASURES:
                k = m["key"]; x = {"show": "", "src": None, "built": None, "cls": "closed" if p["closed"] else "", "title": "", "input": None, "moved": False}
                if F:
                    if reading == "finance":
                        x["show"] = _show(k, F["fin"][k])
                        x["src"] = ((_show(k, F["src"][k]) or "—") if rules[k]["source_field"] else None) if F["src"] else ("no demand plan" if k == "volume" else None)
                        if F["built"] and _shown_as(k) != "rate":
                            x["built"] = _show(k, F["built"][k])
                        e = typed.get((code, p["period"], k))
                        if e and over(code, p["period"], k):
                            e = None                   # a figure typed since, above it and not yet saved, has written over it
                        if e:
                            x["cls"] += " typed"; x["title"] = _edit_title(e); x["moved"] = bool(e["source_moved"])
                        t = mine.get((code, p["period"], k))
                        if t:
                            x["cls"] += " typed"; x["moved"] = False
                            x["title"] = f"typed {_show(k, t.value)} at {t.at[11:16]} — not saved"
                        if touched and any(c in touched.get(k, ()) for c in ks):
                            x["cls"] += " unsaved"
                            x["title"] = x["title"] or "changed by a figure typed and not saved"
                        if editable and k == measure and p["period"] in opens:
                            val = F["fin"][k]
                            x["input"] = f"{k[0]}|{code}|{p['period']}"
                            x["value"] = "" if val is None else (f"{val:.0f}" if k == "volume" else f"{val:.2f}")
                            x["live"] = {"node": code, "period": p["period"], "measure": k}
                    elif reading == "source":
                        x["show"] = _show(k, F["src"][k]) if F["src"] else ("built" if k == "volume" else "")
                    else:
                        x["show"] = _show_var(k, F["var"][k], F["var_d"][k]) if F.get("var") else ("built" if k == "volume" else "")
                        if F.get("var") and (F["var"][k] or 0) < 0:
                            x["cls"] += " down"
                        if touched and any(c in touched.get(k, ()) for c in ks):
                            x["cls"] += " unsaved"; x["title"] = "changed by a figure typed and not saved"
                row["cells"][k].append(x)
        rows.append(row)
    T = _figures([grid.cells[k] for p in periods for k in buckets.get((fm, p["period"]), [])], rules, ["volume", "price", "revenue"]) or {} if grid is not None else {}
    fin_t, src_t = T.get("fin") or {}, T.get("src") or {}
    tot = {"fin_rev": fin_t.get("revenue"), "fin_vol": fin_t.get("volume"), "fin_price": _show("price", fin_t.get("price")) or "—",
           "src_rev": src_t.get("revenue"), "src_vol": src_t.get("volume"), "src_price": _show("price", src_t.get("price")) or "—",
           "var_rev": (T.get("var") or {}).get("revenue"), "var_vol": (T.get("var") or {}).get("volume"), "var_d": (T.get("var_d") or {}).get("revenue"),
           "built_rev": (T.get("built") or {}).get("revenue") if T.get("built") else (fin_t.get("revenue") if T.get("built_only") else None),
           "built_vol": (T.get("built") or {}).get("volume") if T.get("built") else (fin_t.get("volume") if T.get("built_only") else None)}
    decl = {d["account_code"]: d["source"] for d in _once(reads.finance_sources)() if d["material_code"] == "ALL" and d["valid"]}
    unsaved_rows = [{"scope_material": t.material, "period": t.period, "measure": t.measure, "typed": _show(t.measure, t.value),
                     "now": _show(t.measure, finance_live.node_value(grid, version, fc, t.material, t.period, t.measure)),
                     "then": _show(t.measure, t.source_at_entry), "src_now": _show(t.measure, t.source_at_entry), "source_moved": False,
                     "standing": "unsaved", "state": "in_force", "reason": "", "entered_by": who}
                    for t in reversed(wc.typed if wc else []) if t.customer == fc and t.material in nodes and t.period in {p["period"] for p in periods}]
    return {"fy": fy, "fc": fc, "fm": fm, "reading": reading, "measure": measure, "tab_label": rules[measure]["label"],
            "not_built": [rules[m]["not_built_says"] for m in lines if not rules[m]["built"] and rules[m]["not_built_says"]][:1], "customers": customers, "customer_label": next((x["label"] for x in customers if x["code"] == fc), fc), "source_of": decl,
            "path": [{**n, "href": L(material=n["code"])} for n in _once(reads.node_path)("material", fm)] or [{"code": "ALL", "label": "All materials", "href": L(material="ALL")}],
            "readings": [{"label": lab, "on": key == reading, "href": L(reading=key)} for key, lab in READINGS],
            "n_waiting": len(FINANCE.pending()), "row_head": fm_label, "periods": periods, "measures": MEASURES, "rows": rows, "tot": tot,
            "any_built": any(r["built"] for r in rows) or any(s == "built" for s in decl.values()),
            "editable": editable, "may": may, "open": is_open, "status": v.get("status", "unknown"), "holders": _once(reads.holders)("overlay.finance.enter"),
            "post_keep": {**page, "version": version or "", "fy": fy}, "live_context": {"page": {**page, "version": version or "", "fy": fy}},
            "unsaved_n": len(wc.typed) if wc else 0, "unsaved_here": sum(1 for t in (wc.typed if wc else []) if grid is not None and grid.accounts_under.get(t.customer, set()) <= grid.accounts_under.get(fc, set())), "say": say,
            "can_add": editable and _once(reads.is_account)(fc), "add_materials": _once(reads.account_materials)(fc) if editable and _once(reads.is_account)(fc) else [],
            "open_in_fy": [p["period"] for p in periods if p["period"] in opens],
            "reasons": _once(reads.finance_reasons)(), "default_reason": "BUILD" if decl.get(fc) == "built" else "MARKET",
            "edits": unsaved_rows + [{**e, "typed": _show(e["measure"], e["value"]), "now": _show(e["measure"], e["now_at_node"]), "then": _show(e["measure"], e["source_at_entry"]),
                                      "src_now": _show(e["measure"], e["source_now"])} for e in edits[:80]],
            "saves": _once(reads.finance_saves)(version) if version else []}


def _fin_parts(version: str, fy: int, page: dict, who: str, say: str | None = None) -> dict[str, str]:
    """The view as its swappable parts, by element id: the tiles, the status line, one part per row, the typed list."""
    fin = _finance_ctx(version, fy, page, who=who, say=say)
    M = _fin_macros()
    parts = {"fin-tiles": str(M.fin_tiles(fin)), "fin-status": str(M.fin_status(fin))}
    for r in fin["rows"]:
        parts[f"fin-r-{r['code']}"] = str(M.fin_row(fin, r))
    parts["fin-typed"] = str(M.fin_typed(fin))
    return parts


def _back(f) -> str:
    return url_for("plan.revenue", **_page_args(f))


def _cell_refusal(who: str, version: str, v: dict, fc: str, node: str, period: str, measure: str, value: float | None, raw) -> str | None:
    """Why a figure cannot go into the working copy — the same rules a save is held to, judged as it is typed."""
    if not roles.may(who, "overlay.finance.enter"):
        return f"{who} does not hold {said('overlay.finance.enter')} — Finance's figures are typed by {', '.join(reads.holders('overlay.finance.enter'))}"
    if v.get("status") != "open":
        return f"{version} is {v.get('status', 'unknown')} — nothing is typed on it"
    if fc not in {c["code"] for c in reads.finance_customer_nodes()}:
        return f"{fc} is not all customers, a unit or an account"
    rule = finance_live.rules().get(measure)
    if not rule or not rule["breakback"]:
        return f"{measure} is not typed" + (f" — {rule['label'].lower()} = {rule['formula_says']}" if rule and rule["formula_says"] else "")
    if not roles.may(who, rule["verb"]):
        return f"{who} does not hold {said(rule['verb'])} — {rule['label'].lower()} is typed by {', '.join(reads.holders(rule['verb']))}"
    if not reads.material_node(node):
        return f"{node} is not a node of the material structure"
    if period not in set(reads.open_periods(version)):
        return f"{period} is closed — figures are typed in open periods only"
    if value is None:
        return f"'{raw}' is not a number"
    if (measure == "volume" and value < 0) or (measure == "price" and value <= 0):
        return "cases are zero or more, a price is above zero"
    if (measure == "volume" and value > FIN_MAX["volume"]) or (measure == "price" and value > FIN_MAX["price"]):
        return f"{raw} is beyond what one figure here can be — at most {FIN_MAX['volume']:,.0f} cases, or a price of {FIN_MAX['price']:,.0f} a case"
    return None


FIN_MAX = {"volume": 100_000_000, "price": 100_000}       # one figure: cases at a node in a period; net per case


@plan.post("/finance/cell")
def finance_cell():
    """One figure typed (the page's script posts each as it is entered), applied to the person's working copy at once; the
    reply is the parts of the view it changed. Without the script the grid posts here as a form, every changed figure is
    applied in order, and the page is drawn again. Nothing is written to the landing."""
    live = working.is_live()
    data = (request.get_json(silent=True) or {}) if live else request.form
    page = _page_args((data.get("page") or {}) if live else data)
    who = _who(); version = page.get("version") or reads.default_version(); v = reads.version(version) or {}
    page["version"] = version
    fy = int(page.get("fy") or v.get("fiscal_year") or 0)
    page["fy"] = fy
    fc = page.get("customer") or "ALL"
    if live:
        figures = [(str(data.get("node") or ""), str(data.get("period") or ""), str(data.get("measure") or ""), data.get("value"))]
    else:
        figures = [(k.split("|")[1], k.split("|")[2], "volume" if k[0] == "v" else "price", val)
                   for k, val in data.items() if k[:2] in ("v|", "p|") and k.count("|") == 2 and str(val).strip()]
    with finance_live.COPIES.lock(who):
        before = _fin_parts(version, fy, page, who) if live else {}
        refused, force, applied = [], [], 0
        for node, period, measure, raw in figures:
            value = _num(raw)
            why = _cell_refusal(who, version, v, fc, node, period, measure, value, raw)
            if why is None:
                wc = finance_live.working_copy(who, version, FINANCE, create=True)
                if finance_live.type_figure(wc, fc, node, period, measure, value) is not None:
                    applied += 1
                    continue
                if not wc.typed:
                    finance_live.discard(who, version)
                at_node = finance_live.node_value(wc.grid, version, fc, node, period, measure) if wc else None
                why = None if at_node is not None else f"nothing at {node} for {fc} in {period} to spread to — start a material at an account first"
            if why:
                refused.append(why); force.append(f"fin-r-{node}")
        if live:
            after = _fin_parts(version, fy, page, who, say="; ".join(refused) or None)
            return working.reply(before, after, always=tuple(["fin-status"] + force))
    if refused:
        session.say("; ".join(refused), False)
    elif applied:
        session.say(f"{applied} figure{'s' if applied != 1 else ''} applied — not yet saved", True)
    return redirect(_back(page))


@plan.post("/finance/start")
def finance_start():
    """Start a material at an account where nothing stands: its first volume and price, into the working copy."""
    f = request.form; who = _who(); page = _page_args(f)
    version = page.get("version") or reads.default_version(); v = reads.version(version) or {}
    fc = page.get("customer") or ""; mat = (f.get("add_material") or "").strip(); period = f.get("add_period") or ""
    av, ap = _num(f.get("add_volume")), _num(f.get("add_price"))
    why = None
    if not reads.is_account(fc):
        why = "a material is started at an account, not above one"
    elif not mat or av is None or ap is None:
        why = f"{mat or 'a material'} needs both cases and a net price per case to start"
    else:
        why = _cell_refusal(who, version, v, fc, mat, period, "volume", av, f.get("add_volume")) or _cell_refusal(who, version, v, fc, mat, period, "price", ap, f.get("add_price"))
    if why is None:
        with finance_live.COPIES.lock(who):
            wc = finance_live.working_copy(who, version, FINANCE, create=True)
            finance_live.type_figure(wc, fc, mat, period, "volume", av)
            finance_live.type_figure(wc, fc, mat, period, "price", ap)
        session.say(f"{mat} started at {fc} in {period} — not yet saved", True)
    else:
        session.say(why, False)
    return redirect(_back(page))


@plan.post("/finance/discard")
def finance_discard():
    """Drop the working copy: the grid is the plan as last saved again."""
    who = _who(); page = _page_args(request.form); version = page.get("version") or reads.default_version()
    with finance_live.COPIES.lock(who):
        wc = finance_live.working_copy(who, version, FINANCE)
        n = len(wc.typed) if wc else 0
        finance_live.discard(who, version)
    session.say(f"{n} unsaved figure{'s' if n != 1 else ''} discarded — the grid is the plan as last saved" if n else "nothing unsaved to discard", True)
    return redirect(_back(page))


@plan.post("/finance/save")
def finance_save():
    """One save: every figure in the person's working copy, under one reason, as one file — each figure as typed and
    where, and the cells it wrote at account × material × period, which are what stand — then released: the run scoped to
    Finance's part of the plan (the whole run when another file is waiting). Nothing here touches the demand stack."""
    f = request.form; who = _who(); verb = "overlay.finance.enter"; page = _page_args(f)
    version = page.get("version") or reads.default_version(); v = reads.version(version) or {}
    reason = f.get("reason_code", ""); note = (f.get("note") or "").strip()
    reasons = {r["reason_code"]: r for r in reads.finance_reasons()}
    with finance_live.COPIES.lock(who):        # a figure still being applied lands before the copy is read
        wc = finance_live.working_copy(who, version, FINANCE)
        n = len(wc.typed) if wc else 0
        may = roles.may(who, verb)
        checks = [
            {"check": "who may type", "ok": may, "says": f"{who} holds {said(verb)}" if may else f"{who} does not hold {said(verb)} — Finance's figures are typed by {', '.join(reads.holders(verb))}"},
            {"check": "version open", "ok": v.get("status") == "open", "says": f"{version} is {v.get('status', 'unknown')}"},
            {"check": "something to save", "ok": n > 0, "says": f"{n} figure{'s' if n != 1 else ''} typed and not saved" if n else "nothing typed since the last save"},
            {"check": "a reason we know", "ok": reason in reasons, "says": reasons[reason]["description"] if reason in reasons else f"{reason or 'no reason'} is not one of Finance's reasons"},
            {"check": "a note where the reason needs one", "ok": bool(note) or not (reasons.get(reason) or {}).get("note_required"),
             "says": note or ("this reason needs a note saying what" if (reasons.get(reason) or {}).get("note_required") else "not needed for this reason")},
        ]
        placed = receipts.judge(checks)
        stamp = dt.datetime.now(); save_id = f"FS-{stamp.strftime('%Y%m%d-%H%M%S-%f')}"
        if placed:
            FINANCE.place(finance_live.rows_for_save(wc, save_id, stamp, who, reason, note), who)
            finance_live.discard(who, version)
    session.last = receipts.write("finance.save", who, save_id, checks, placed)
    if not placed:
        session.say("save refused: " + "; ".join(c["says"] for c in checks if not c["ok"]), False)
        return redirect(_back(page))
    if _run_plan(who, "finance"):
        session.say(f"{save_id} saved — {n} figure{'s' if n != 1 else ''} written to {version} and carried into the plan", True)
        return redirect(_back(page))
    return redirect(url_for("plan.run"))


@plan.post("/finance/release")
def finance_release():
    """Release a save whole: its figures return to the demand plan (or, where built, are gone) — and carried into the plan
    at once, by the same run a save makes."""
    f = request.form; who = _who(); sid = f.get("save_id", ""); verb = "overlay.finance.enter"; page = _page_args(f)
    version = page.get("version") or reads.default_version(); v = reads.version(version) or {}
    s = reads.finance_save(sid)
    may = roles.may(who, verb)
    checks = [
        {"check": "who may release", "ok": may, "says": f"{who} holds {said(verb)}" if may else f"{who} does not hold {said(verb)}"},
        {"check": "save on file", "ok": bool(s and s["version_id"] == version), "says": f"{sid} on {version}" if s and s["version_id"] == version else f"{sid} is not on {version}"},
        {"check": "not already released", "ok": bool(s and not s["released"]), "says": "stands" if s and not s["released"] else "already released"},
        {"check": "version open", "ok": v.get("status") == "open", "says": f"{version} is {v.get('status', 'unknown')}"},
    ]
    placed = receipts.judge(checks)
    if placed:
        FINANCE.place([{"edit_id": f"FR-{dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')}", "action": "release", "withdraws": sid, "version_id": version,
                        "entered_by": who, "entered_on": dt.datetime.now().isoformat(timespec="microseconds")}], who)
    session.last = receipts.write("finance.release", who, sid, checks, placed)
    if not placed:
        session.say("release refused: " + "; ".join(c["says"] for c in checks if not c["ok"]), False)
        return redirect(_back(page))
    if _run_plan(who, "finance"):
        session.say(f"{sid} released — its figures have returned to the demand plan", True)
        return redirect(_back(page))
    return redirect(url_for("plan.run"))


# ---- where each number comes from: the slot register ----
SLOTS = """<h1>Where each number comes from<small>the financial plan is one chain; each step is filled by the model behind it or by a Finance assumption, declared per step — what reads a step never knows which</small></h1>
<table><thead><tr><th></th><th>Step</th><th>From the operational model</th><th>As a Finance assumption</th><th>Declared</th><th>Today</th></tr></thead><tbody>
{% for s in slots %}<tr class="{{ '' if s.built else 'off' }}"><td class="n">{{ s.ord }}</td><td><b>{% if s.href %}<a href="{{ s.href }}">{{ s.slot }}</a>{% else %}{{ s.slot }}{% endif %}</b></td>
<td class="small {{ '' if s.declared == 'model' else 'muted' }}">{{ s.from_model }}</td><td class="small {{ '' if s.declared == 'assumption' else 'muted' }}">{{ s.as_assumption }}</td>
<td>{% if s.declared == 'model' %}the model{% elif s.declared == 'assumption' %}an assumption{% else %}<span class="state">not yet filled</span>{% endif %}</td>
<td class="small">{{ s.today or '' }}{% if s.says %}<div class="muted">{{ s.says }}</div>{% endif %}</td></tr>{% endfor %}</tbody></table>
<p class="hint">A business early in its planning runs the right-hand column — a rate on last year, a standard per material, weeks of cover — and each move replaces one assumption with its model; nothing downstream changes, because downstream reads the step. Where both exist, the assumption is read against the model.</p>
<h2 id="fed">Fed or built<span class="count">Finance's volume and price, declared per account × material · FY{{ fy }} on {{ version }}</span></h2>
<table><thead><tr><th>Account</th><th>Materials</th><th>Source</th><th>Declared</th><th class="n">Finance's plan</th><th class="n">Demand plan beneath</th><th>Note</th></tr></thead><tbody>
{% for d in sources %}<tr><td>{{ d.account_code }} <span class="small muted">{{ d.account_name }}</span></td><td>{% if d.material_code == 'ALL' %}<span class="small muted">the account's default</span>{% else %}{{ d.material_code }} <span class="small muted">{{ d.material_name }}</span>{% endif %}</td>
<td>{% if d.source == 'built' %}<b>built by Finance</b>{% else %}fed by the demand plan{% endif %}</td><td class="small">{{ d.declared_by }} · {{ d.declared_on }}</td>
<td class="n">{{ d.plan|aud if d.plan is not none else '' }}</td><td class="n">{{ d.beneath|aud if d.beneath is not none else ('none' if d.source == 'built' else '') }}</td><td class="small">{{ d.note or '' }}</td></tr>{% endfor %}</tbody></table>
<p class="hint">Fed: the demand plan valued is the source and Finance types over it. Built: nothing feeds — Finance keeps the volume and the price itself, and the grid shows no figure beneath. The account's row is its default; a material row is an exception. <a href="{{ url_for('plan.revenue') }}">Revenue</a> reads both, with the demand plan under every fed figure.</p>"""
SLOT_RUNG = {"cogs": "standard", "inventory": "inventory", "capex": "capex", "balance": "balance"}


@plan.get("/slots")
def slots():
    try:
        version = reads.default_version()
        today, fy = {}, 0
        if version:
            fy = int((reads.version(version) or {}).get("fiscal_year") or 0)
            vol = q("select sum(cases) c from plan.revenue_bridge where version_id = ? and fiscal_year = ?", version, fy)[0]["c"]
            today["volume"] = f"{vol:,.0f} cases in FY{fy} on {version}" if vol else None
            ti = q("select count(*) n from plan.terms")[0]["n"]
            pl = q("select count(distinct price_list) n from history.price_list")[0]["n"]
            today["price"] = f"{pl} price lists, {ti} terms instruments"
            ev = q("select count(*) n from plan.promo_event")[0]["n"]
            today["promotions"] = f"{ev} events in the calendar"
            sch = q("select count(distinct entity_code || cost_centre_code || account_code) n, sum(amount) a from plan.opex_schedule where version_id = ? and fiscal_year = ?", version, fy)[0]
            today["opex"] = f"{sch['n']} lines, ${sch['a'] / 1e6:,.1f}M planned in FY{fy}'s open periods on {version}" if sch["n"] else None
            lab = q("select sum(amount) a, count(distinct cost_centre_code) n from plan.labour_cost where version_id = ? and fiscal_year = ?", version, fy)[0]
            today["labour"] = f"${lab['a'] / 1e6:,.1f}M in FY{fy}'s open periods across {lab['n']} cost centres on {version}" if lab["n"] else None
        rows = []
        for s_ in reads.slots():
            href = url_for("plan.rung", slug=SLOT_RUNG[s_["slot_key"]]) if s_["page"] == "plan.rung" and s_["slot_key"] in SLOT_RUNG else (url_for(s_["page"]) if s_["page"] else None)
            rows.append({**s_, "href": href, "today": today.get(s_["slot_key"]) if s_["built"] else None})
        by = {}
        for r in (reads.finance_by_source(version, fy) if version else []):
            by.setdefault(r["account_code"], {})[r["source"]] = r
        sources = []
        for d in reads.finance_sources():
            if d["material_code"] == "ALL":
                x = by.get(d["account_code"], {}).get(d["source"]) or {}
                sources.append({**d, "plan": x.get("net_sales"), "beneath": x.get("source_net_sales")})
            else:
                r = q("""select sum(net_sales) ns from plan.finance_plan where version_id = ? and fiscal_year = ? and account_code = ? and material_code = ?""",
                      version, fy, d["account_code"], d["material_code"])[0] if version else {}
                sources.append({**d, "plan": r.get("ns"), "beneath": None})
        return _page(SLOTS, title="Where each number comes from", active="slots", slots=rows, sources=sources, fy=fy, version=version)
    except Busy as e:
        return _busy("Where each number comes from", e)


# ---- how each figure is calculated: the measure register ----
RULES = """<h1>How each figure is calculated<small>every grid a person types into, its figures and the rule behind each — the calculation reads how a figure adds up and how a figure typed at a total spreads from this table, so what it says here is what the grid does</small></h1>
{% for g in grids %}<h2 id="{{ g.grid }}"><a href="{{ g.href }}">{{ g.label }}</a><span class="count">{{ g.rows|length }} figure{{ 's' if g.rows|length != 1 }}{% if g.tabbed %} · {{ g.tabbed }} with a tab of {{ 'its' if g.tabbed == 1 else 'their' }} own{% endif %}</span></h2>
<table class="rules"><thead><tr><th>Figure</th><th>How it is set</th><th>At a total</th><th>Typed at a total</th><th>Typed by</th></tr></thead><tbody>
{% for r in g.rows %}<tr id="{{ g.grid }}-{{ r.measure }}" class="{{ '' if r.built else 'off' }}"><td><b>{{ r.label }}</b><div class="small muted">{{ r.unit }}</div></td>
<td>{% if r.formula_says %}<b>{{ r.label|lower }} = {{ r.formula_says }}</b><div class="small">{{ r.set_says }}</div>{% else %}<span class="small">{{ r.set_says }}</span>{% endif %}{% if not r.built %}<div class="small muted">{{ r.not_built_says }}</div>{% endif %}</td>
<td class="small">{{ r.rollup_says }}</td><td class="small">{{ r.breakback_says }}</td>
<td class="small">{% if r.verb %}{{ r.holders|join(', ') or 'nobody yet' }}{% elif r.set_by == 'from a source' %}<span class="muted">kept at its source</span>{% else %}<span class="muted">nobody — calculated</span>{% endif %}</td></tr>{% endfor %}</tbody></table>{% endfor %}
<p class="hint">How a figure adds up at a total and how a figure typed at a total spreads are settings: the calculation reads them from this table, so a changed row changes what the grid does. The formulas are written into the calculation and checked against the words above every time the build is tested — no formula is worked out from this page. A figure typed at a total is written down to every figure beneath it the moment it is typed; the total is then their sum, and the last figure typed wins. A greyed row is named and not yet calculable. Where each figure's source is declared: <a href="{{ url_for('plan.slots') }}">Where each number comes from</a>.</p>
<style>table.rules td{vertical-align:top}table.rules td:nth-child(2){min-width:18rem}</style>"""


@plan.get("/rules")
def rules():
    try:
        grids: dict[str, dict] = {}
        for r in reads.grid_measures():
            g = grids.setdefault(r["grid"], {"grid": r["grid"], "label": r["grid_label"], "href": url_for(r["grid_page"]), "rows": []})
            g["rows"].append({**r, "holders": reads.holders(r["verb"]) if r["verb"] else []})
            g["tabbed"] = sum(1 for x in g["rows"] if x["grid"] == "finance" and x["measure"] in FIN_TABS)
        return _page(RULES, title="How each figure is calculated", active="rules", grids=list(grids.values()))
    except Busy as e:
        return _busy("How each figure is calculated", e)


# ---- the structures as loaded: a view, never an editor ----
STRUCTURES = """<h1>Structures as loaded<small>what the plan was given, from which system and when, and what changed since the load before — read here, maintained in the client's systems</small></h1>
<div class="cards">{% for s in loads %}<div class="card"><b>{{ s.structure_name }}</b><div class="small muted">{{ s.source_system }}</div>
<div style="font-size:1.6rem;margin:.4rem 0 .1rem">{{ s.members|n }}</div><div class="small">{{ s.says }}</div>
<div class="small" style="margin-top:.5rem">loaded {{ s.latest }}<br><span class="muted">the load before {{ s.previous }}</span></div>
<div class="small" style="margin-top:.4rem">{% if s.n_new or s.n_changed or s.n_gone %}<a href="#changes-{{ s.structure }}">{{ s.n_new }} new · {{ s.n_changed }} changed · {{ s.n_gone }} gone</a>{% else %}no change since the load before{% endif %}</div></div>{% endfor %}</div>
<h2 id="unfit">Not yet fit to plan<span class="count">{{ unfit|length }} gap{{ '' if unfit|length == 1 else 's' }} · a member missing what the plan needs — fixed where the structure is kept, by its owner</span></h2>
{% if unfit %}<table><thead><tr><th>Structure</th><th>Member</th><th>Name</th><th>Lacks</th><th>Status</th><th>Ask</th></tr></thead><tbody>
{% for u in unfit %}<tr><td>{{ u.structure }}</td><td><code>{{ u.member_code }}</code></td><td>{{ u.member_name }}</td><td>{{ u.lacks }}</td><td class="small">{{ u.note or '' }}</td><td class="small">{{ u.owners or 'nobody holds it yet' }}</td></tr>{% endfor %}</tbody></table>
{% else %}<p class="muted">Every member carries what the plan needs.</p>{% endif %}
<h2 id="provisional">Provisional<span class="count">held in the plan ahead of the client's master — the client's master is never edited from here</span></h2>
{% if provisional %}<table><thead><tr><th>Their code</th><th>As sent</th><th>Placed under</th><th class="n">Cases sent</th><th>By</th><th>At</th><th>Why</th></tr></thead><tbody>
{% for p in provisional %}<tr><td><code>{{ p.item_code }}</code></td><td class="small">{{ p.description or '' }}</td><td>{{ p.target_code }} <span class="muted small">{{ p.target_name or '' }}</span></td><td class="n">{{ p.cases|n if p.cases else '' }}</td><td>{{ p.acted_by }}</td><td class="small">{{ p.acted_at }}</td><td class="small">{{ p.reason or '' }}</td></tr>{% endfor %}</tbody></table>
<p class="hint">Placed, not yet planned: a provisional member has a place in our structure and no price or route until the client's master carries it.</p>
{% else %}<p class="muted">Nothing is provisional.</p>{% endif %}
<h2 id="doors">Open disagreements by door<span class="count">where what arrived and the plan's structures disagree, and nobody has decided</span></h2>
<table><thead><tr><th>Door</th><th>Waiting</th><th class="n">Items</th><th>Decided by</th></tr></thead><tbody>
{% for d in disagreements %}<tr><td>{{ d.door }}</td><td><a href="{{ d.href }}">{{ d.name }}</a></td><td class="n">{{ d['items'] }}</td><td class="small">{{ d.whose or '' }}</td></tr>{% endfor %}</tbody></table>
{% for s in loads %}{% set rows = changes|selectattr('structure', 'equalto', s.structure)|list %}{% if rows %}<h2 id="changes-{{ s.structure }}">{{ s.structure_name }}: since the load before<span class="count">{{ s.previous }} → {{ s.latest }}</span></h2>
<table><thead><tr><th>Member</th><th>Name</th><th>Change</th><th>What</th></tr></thead><tbody>
{% for c in rows %}<tr class="{{ 'added' if c.change == 'new' else ('off' if c.change == 'gone' else '') }}"><td><code>{{ c.member_code }}</code></td><td>{{ c.member_name }}</td><td>{{ c.change }}</td><td class="small">{{ c.what or '' }}</td></tr>{% endfor %}</tbody></table>{% endif %}{% endfor %}
<p class="hint">Nothing on this page is editable. The plan reads each structure as it is loaded and says what it needs; creating, cleansing and governing the records is done where they are kept. Ask the owner named — the plan reads the next load.</p>"""


@plan.get("/structures")
def structures():
    try:
        h = {r["surface"]: r for r in health(q, HEALTH)}
        doors_ = [("the promotions system", "plan.worklist_promo_mapping_review", url_for("plan.mapping")),
                  ("the promotions system", "plan.worklist_promo_held", url_for("plan.events") + "#held"),
                  ("the forecasting system", "plan.worklist_forecast_queue", url_for("plan.forecast", accounts="all") + "#queue")]
        dis = [{"door": d, "name": h[s]["name"], "items": h[s]["items"], "whose": h[s]["whose"], "href": href} for d, s, href in doors_ if s in h]
        return _page(STRUCTURES, title="Structures as loaded", active="structures", loads=reads.structure_loads(), changes=reads.structure_changes(),
                     unfit=reads.structure_unfit(), provisional=reads.provisional(), disagreements=dis)
    except Busy as e:
        return _busy("Structures as loaded", e)


# ---- the map: drawn from the register beside the process register, with each node's state from the last run ----
MAP = """<h1>The plan, end to end<small>what sends, what the plan holds, what it makes and what is read — every box opens the page that owns it and says what waits there after the last run</small></h1>
<div class="card fig mapfig">{{ svg|safe }}</div>
<p class="hint">A heavy line from the left is a door: something made elsewhere taken into the plan, read against its own structures, every disagreement waiting for a person. A dashed box is named and not yet built. The boxes and lines are a register beside the menu, so a new door is a new line here.</p>
<style>.mapfig{padding:1rem;overflow-x:auto}.mapfig svg{width:100%;min-width:1000px;height:auto;display:block}
.map .node rect{fill:var(--panel);stroke:var(--ink);stroke-width:1}.map .node.off rect{fill:none;stroke:var(--muted);stroke-dasharray:4 3}
.map .node:hover rect{stroke-width:2}.map .node text{fill:var(--ink);font-size:13px}.map .node .says{fill:var(--muted);font-size:11px}
.map .node .state{font-size:11px;font-weight:600}.map .node.off text{fill:var(--muted)}.map .node .state.quiet{fill:var(--muted);font-weight:400}
.map .flow{fill:none;stroke:var(--muted);stroke-width:1}.map .flow.door{stroke:var(--ink);stroke-width:2.2}
.map .flowlabel{fill:var(--muted);font-size:10px;paint-order:stroke;stroke:var(--panel);stroke-width:3px}.map .band{fill:var(--muted);font-size:11px;letter-spacing:.08em;text-transform:uppercase}</style>"""
BANDS = [("sends", "What sends"), ("plan", "What the plan holds"), ("made", "What it makes"), ("read", "What is read")]


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _node_state(n, items: dict, pend: dict) -> tuple[str, bool]:
    """What a node says after the last run: items waiting, files not yet in the plan, or not built. (text, waiting?)"""
    if not n.built:
        return "named, not yet built", False
    bits = []
    waiting = sum(items.get(s, 0) for s in n.surfaces)
    if waiting:
        bits.append(f"{waiting} waiting")
    if pend.get(n.key):
        bits.append(pend[n.key])
    return (" · ".join(bits), True) if bits else ("nothing waiting", False)


def _map_svg(items: dict, pend: dict) -> str:
    W, NW, NH, GAP, TOP = 1280, 210, 62, 14, 40
    xs = {b: 20 + i * ((W - 40 - NW) / (len(BANDS) - 1)) for i, (b, _) in enumerate(BANDS)}
    pos, cols = {}, {b: [n for n in MAP_NODES if n.band == b] for b, _ in BANDS}
    H = TOP + max(len(c) for c in cols.values()) * (NH + GAP) + 10
    for b, ns in cols.items():
        off = TOP + ((H - TOP - 10) - len(ns) * (NH + GAP)) / 2
        for i, n in enumerate(ns):
            pos[n.key] = (xs[b], off + i * (NH + GAP))
    out = [f'<svg class="map" viewBox="0 0 {W} {H:.0f}" role="img" aria-label="the plan, end to end">']
    for b, label in BANDS:
        out.append(f'<text class="band" x="{xs[b]:.0f}" y="18">{_esc(label)}</text>')
    band = {n.key: n.band for n in MAP_NODES}
    for a, z, what in MAP_FLOWS:
        (x1, y1), (x2, y2) = pos[a], pos[z]
        x1 += NW; y1 += NH / 2; y2 += NH / 2
        mx = (x1 + x2) / 2
        door = band[a] == "sends"
        out.append(f'<path class="flow{" door" if door else ""}" d="M{x1:.0f},{y1:.0f} C{mx:.0f},{y1:.0f} {mx:.0f},{y2:.0f} {x2:.0f},{y2:.0f}"/>')
        if what:
            out.append(f'<text class="flowlabel" x="{mx:.0f}" y="{(y1 + y2) / 2 - 4:.0f}" text-anchor="middle">{_esc(what)}</text>')
    for n in MAP_NODES:
        x, y = pos[n.key]
        href = url_for(n.endpoint, **n.args) + (f"#{n.anchor}" if n.anchor else "") if n.endpoint else ""
        state, hot = _node_state(n, items, pend)
        out.append(f'<a href="{_esc(href)}" class="node{"" if n.built else " off"}"><title>{_esc(n.label)} — {_esc(state)}</title>'
                   f'<rect x="{x:.0f}" y="{y:.0f}" width="{NW}" height="{NH}" rx="6"/>'
                   f'<text x="{x + 12:.0f}" y="{y + 20:.0f}" font-weight="600">{_esc(n.label)}</text>'
                   f'<text class="says" x="{x + 12:.0f}" y="{y + 36:.0f}">{_esc(n.says)}</text>'
                   f'<text class="state{"" if hot else " quiet"}" x="{x + 12:.0f}" y="{y + 52:.0f}">{_esc(state)}</text></a>')
    out.append("</svg>")
    return "".join(out)


@plan.get("/map", endpoint="map")
def plan_map():
    try:
        items = {h["surface"]: int(h["items"] or 0) for h in health(q, HEALTH)}
    except Busy:
        items = {}
    def files(n: int) -> str:
        return f"{n} file{'s' if n != 1 else ''} not yet in the plan" if n else ""
    pend = {"tpm": f"{len(promotions.waiting())} file{'s' if len(promotions.waiting()) != 1 else ''} waiting to be taken in" if promotions.waiting() else "",
            "fcs": f"{len(fcst.waiting())} run{'s' if len(fcst.waiting()) != 1 else ''} waiting for an account" if fcst.waiting() else "",
            "layers": files(len(ENTRIES.pending())), "calendar": files(len(promotions.pending())),
            "baseline": files(len(fcst.pending()) + len(doors.ACTS.pending())), "submissions": files(len(SUBMISSIONS.pending())),
            "rates": files(len(TERMS_LANDING.pending()) + len(PRICES_LANDING.pending())), "finance": files(len(FINANCE.pending()))}
    try:
        unfit = q("select count(distinct member_code) n from plan.structure_unfit")[0]["n"]
        pend["structures"] = f"{unfit} member{'s' if unfit != 1 else ''} not yet fit to plan" if unfit else ""
    except Busy:
        pass
    return _page(MAP, title="Map", active="map", width="none", svg=_map_svg(items, pend))


# ---- the rungs named but not yet built ----
RUNGS = {
    "standard": ("Standard by plant", "The standard cost of every material at every plant for the version's standard year, derived from the routes, the BOM and the cost inputs; a new plant through to a new standard and the transition."),
    "landed": ("Landed cost", "The distributor's standard: supplier price × FX + freight + duty by source; purchase price, FX and freight rate as the three variances."),
    "pnl": ("P&L plan", "The P&L read across every step of the chain: every line of the commercial P&L by cause — volume, price, mix, promotion, cost — at standard, with the planned variances beneath."),
    "balance": ("Balance sheet plan", "Every line rolled from opening actuals by one declared movement source, working capital first by its timing policy; three identities run as a check on every version."),
    "capex": ("Projects and depreciation", "Projects entered, approved and phased, and depreciated; the maintenance deferral that raises unplanned downtime into the capacity analysis. Waits on four questions about how capital is planned here."),
    "nonop": ("Interest, tax and other", "The non-operating lines of the P&L — interest, tax, other income and expense — each a schedule of its own or a line per period with a declared method."),
    "cash": ("Cash", "Cash by period, rolled from the opening balance through the P&L and the movements in working capital, capital and financing."),
    "assumptions": ("Assumptions", "The one set of assumptions every plan is valued with — exchange rate, inflation, wage and energy indices — by version and period, each with what reads it."),
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


# ---- promotions: one calendar, two doors ----
EVENTS = """<h1>Promotions<small>{{ version }} · one calendar, two doors — the promotions system sends the events of the accounts it keeps, in its own codes; every other account's events are typed here</small></h1>
<div class="cards"><div class="card stat"><b>{{ cal|length }}</b><span>events in the calendar · {{ n_sender }} sent, {{ n_plan }} typed</span></div>
<div class="card stat"><b>{{ held_events|length }}</b><span>held — waiting for a mapping</span></div>
<div class="card stat"><b>{{ refused|length }}</b><span>refused at the door</span></div>
<div class="card stat"><b>{{ waiting }}</b><span>file{{ '' if waiting == 1 else 's' }} from the promotions system waiting</span></div></div>
<p class="small muted">Where each account's promotions are kept: {% for a in accounts %}{{ a.account_code }} {{ 'promotions system' if a.promotions_master == 'TPM' else 'typed here' }}{{ ' · ' if not loop.last }}{% endfor %}.
The mix by family: {% for f, n in families %}{{ f.replace('_', ' ') }} {{ n }}{{ ' · ' if not loop.last }}{% endfor %}. <a href="{{ url_for('plan.calendar') }}">The calendar by week</a>.</p>
<h2 id="sender">From the promotions system<span class="count">each file is taken in by an act; a re-sent event replaces the earlier one, a cancelled one is removed</span></h2>
<table><thead><tr><th>File</th><th class="n">Events</th><th class="n">Funding lines</th><th>State</th><th></th></tr></thead><tbody>
{% for f in files %}<tr><td><code>{{ f.file_id }}</code></td><td class="n">{{ f.events|length if f.events else '' }}</td><td class="n">{{ f.funding|length if f.funding else '' }}</td>
<td>{% if f.taken_in_at %}taken in {{ f.taken_in_at }}{% else %}<span class="severity">waiting</span>{% endif %}</td>
<td>{% if not f.taken_in_at and may %}<form class="inline" method="post" action="{{ url_for('plan.take_in') }}"><input type="hidden" name="file_id" value="{{ f.file_id }}"><button class="act">Take in</button></form>{% endif %}</td></tr>{% endfor %}
</tbody></table>
<h2 id="calendar">The calendar<span class="count">every event the plan carries, by window — the promotions system's codes beside ours</span></h2>
<table><thead><tr><th>Event</th><th>Source</th><th>Account</th><th>Promo group</th><th>Window</th><th>Mechanic</th><th class="n">Uplift</th><th class="n">Dip</th><th>Response</th>
<th class="n">Price reduction / case</th><th class="n">Scan / case</th><th class="n">Lump sums</th><th>Status</th><th>Their codes</th><th>Funding not yet priced</th></tr></thead><tbody>
{% for e in cal %}<tr id="{{ e.event_id }}"><td><a href="{{ url_for('plan.calendar', customer=e.account_code, event=e.event_id) }}">{{ e.event_id }}</a></td><td>{{ 'promotions system' if e.source == 'sender' else 'typed' }}</td><td>{{ e.account_code }}</td><td>{{ e.promo_group_code }}</td>
<td>{{ e.window_start }} – {{ e.window_end }}{% if e.off_week %} <span class="state" title="{{ e.off_week_says }}">off week</span>{% endif %}</td><td>{{ e.mechanic }} <span class="muted small">{{ e.mechanic_family.replace('_', ' ') }}</span></td><td class="n">{{ e.uplift_pct|pct1 }}</td><td class="n">{{ e.dip_pct|pct1 }}</td>
<td class="small">{{ e.response_source }}{% if e.note %} — {{ e.note }}{% endif %}</td><td class="n">{{ e.tpr_per_case|n(2) }}</td><td class="n">{{ e.scan_funding_per_case|n(2) }}</td>
<td class="n" title="fixed fee {{ e.fixed_fee|n }} · retail media {{ e.media_fee|n }} · co-op drawdown {{ e.envelope_drawdown|n }}">{{ e.lump_sums|n }}{% if e.media_fee %}<div class="small muted">media {{ e.media_fee|n }}</div>{% endif %}{% if e.envelope_drawdown %}<div class="small muted">co-op {{ e.envelope_drawdown|n }}</div>{% endif %}</td>
<td>{{ e.status }}</td><td class="small muted">{{ e.local_codes or '' }}</td><td class="small">{{ e.unpriced_funding or '' }}</td></tr>{% endfor %}
</tbody></table>
<h2 id="effect">What each event does<span class="count">gross uplift, the dip after, taken from neighbours, net incremental — and its return on the net</span></h2>
<table><thead><tr><th>Event</th><th>Account · group</th><th class="n">Gross uplift</th><th class="n">Dip</th><th class="n">From neighbours</th><th class="n">Net incremental</th>
<th class="n">Net sales, gross uplift</th><th class="n">From neighbours</th><th class="n">Net incremental</th><th class="n">Given on other cases</th><th class="n">Lump sums</th><th class="n">Return</th><th>Neighbours declared</th></tr></thead><tbody>
{% for e in cal %}<tr><td>{{ e.event_id }}</td><td>{{ e.account_code }} · {{ e.promo_group_code }}</td><td class="n">{{ e.uplift_cases|n }}</td><td class="n">{{ e.dip_cases|n }}</td><td class="n">{{ e.neighbour_cases|n if e.neighbours else '' }}</td>
<td class="n"><b>{{ e.net_incremental_cases|n }}</b></td><td class="n">{{ e.uplift_net_sales|n }}</td><td class="n">{{ e.neighbour_net_sales|n if e.neighbours else '' }}</td><td class="n"><b>{{ e.net_incremental_net_sales|n }}</b></td>
<td class="n">{{ (-e.given_on_other_cases)|n if e.given_on_other_cases else '' }}</td><td class="n">{{ (-e.lump_sums)|n if e.lump_sums else '' }}</td><td class="n"><b>{{ e.net_return|n }}</b></td>
<td class="small">{% if e.neighbours %}{{ e.neighbours }}{% else %}<span class="muted">none declared</span>{% endif %}</td></tr>{% endfor %}
</tbody></table>
<p class="hint">Cases, then net sales at the list and terms in force. A neighbour line moves cases only — the neighbour carries none of the event's price or funding and is priced at its own list and terms. The return is the net incremental net sales, less the price reduction and scan funding the event gives on every other case sold in its window at the promoted scope (the baseline cases sell at the reduced price too), less its lump sums. A blank under neighbours means none declared, not none assumed; competitors' and other accounts' events are not modelled.</p>
<h2 id="neighbours">Neighbour lines<span class="count">declared on an event, never estimated — a rate on a neighbouring range's baseline in the event's window</span></h2>
{% if nbs %}<table><thead><tr><th>Event</th><th>Neighbour</th><th>Effect</th><th class="n">Rate on its baseline</th><th class="n">Materials</th><th>By</th><th>At</th><th>Note</th></tr></thead><tbody>
{% for n in nbs %}<tr class="{{ '' if n.event_in_calendar else 'off' }}"><td>{{ n.event_id }}</td><td>{{ n.scope_material }}</td><td>{{ n.effect_type }}</td><td class="n">{{ n.rate|pct1s }}</td><td class="n">{{ n.materials }}</td><td>{{ n.entered_by }}</td><td class="small">{{ n.entered_at }}</td><td class="small">{{ n.note or '' }}</td></tr>{% endfor %}
</tbody></table>{% else %}<p class="muted">No neighbour line is declared.</p>{% endif %}
{% if may %}<form class="entry" method="post" action="{{ url_for('plan.neighbour_new') }}" style="margin-top:1rem">
<label>event<select name="event_id">{% for e in cal %}{% if e.owner == who %}<option value="{{ e.event_id }}">{{ e.event_id }} · {{ e.account_code }} · {{ e.promo_group_code }} · {{ e.window_start }}</option>{% endif %}{% endfor %}</select></label>
<label>neighbour (a promo group or a material of ours)<input name="scope_material" list="nb_scopes" required placeholder="PG_VALLEY_825"><datalist id="nb_scopes">{% for g in groups %}<option value="{{ g.promo_group_code }}">{{ g.promo_group_name }}</option>{% endfor %}</datalist></label>
<label>effect<select name="effect_type"><option value="cannibalisation">cannibalisation — takes from it</option><option value="halo">halo — lends to it</option></select></label>
<label>rate on its baseline in the window (%)<input name="rate_pct" type="number" step="0.1" required placeholder="-12 takes 12%; 0 removes the line"></label>
<label class="wide">note<textarea name="note" rows="2" placeholder="why the ranges interact"></textarea></label>
<div class="actions"><button class="primary">Declare neighbour line</button><span class="hint">on events you own, from either door — recorded as ours, not the sender's; in the plan after the next run</span></div></form>{% endif %}
<h2 id="held">Held<span class="count">sent, not in the calendar until every code is mapped — what each waits for and what it would bring</span></h2>
{% if held_events %}<table><thead><tr><th>Event</th><th>Their codes</th><th>Ours so far</th><th>Window</th><th>Waits for</th><th class="n">Cases it would bring</th><th class="n">Net sales it would bring</th><th class="n">Lump sums</th></tr></thead><tbody>
{% for h in held_events %}<tr id="{{ h.event_id }}"><td>{{ h.event_id }}</td><td class="small">{{ h.local_account }} · {{ h.local_product_group }} · {{ h.local_tactic }} · {{ h.local_status }}</td>
<td class="small">{{ h.account_code or '?' }} · {{ h.promo_group_code or '?' }}</td><td>{{ h.window_start }} – {{ h.window_end }}</td><td class="small">{{ h.waits_for }}</td>
<td class="n">{{ h.would_bring_cases|n }}</td><td class="n">{{ h.would_bring_net_sales|n }}</td><td class="n">{{ h.would_bring_lump_sums|n }}</td></tr>{% endfor %}
</tbody></table>{% if may_map %}<p class="hint"><a href="{{ url_for('plan.mapping') }}">Review the codes they wait for</a> — they enter on the next run after.</p>{% endif %}
{% else %}<p class="muted">Nothing held.</p>{% endif %}
<h2 id="refused">Refused<span class="count">came through the wrong door — stays on file, out of the calendar</span></h2>
{% if refused %}<table><thead><tr><th>Event</th><th>From</th><th>Account</th><th>Window</th><th>Why</th></tr></thead><tbody>
{% for r in refused %}<tr id="{{ r.event_id }}"><td>{{ r.event_id }}</td><td>{{ 'promotions system' if r.source == 'sender' else 'typed' }}</td><td>{{ r.account_code }}{% if r.local_account %} <span class="muted small">{{ r.local_account }}</span>{% endif %}</td>
<td>{{ r.window_start }} – {{ r.window_end }}</td><td>{{ r.refused_because }}</td></tr>{% endfor %}</tbody></table>
{% else %}<p class="muted">Nothing refused.</p>{% endif %}
{% if cancelled %}<h2>Cancelled by the promotions system</h2><table><thead><tr><th>Event</th><th>Their codes</th><th>Window</th><th>File</th></tr></thead><tbody>
{% for c in cancelled %}<tr><td>{{ c.event_id }}</td><td class="small">{{ c.local_account }} · {{ c.local_product_group }}</td><td>{{ c.window_start }} – {{ c.window_end }}</td><td><code>{{ c.sender_file }}</code></td></tr>{% endfor %}</tbody></table>{% endif %}
{% if pending %}<p class="hint">{{ pending|length }} file{{ '' if pending|length == 1 else 's' }} placed since the last run — the calendar shows them after the run.</p>{% endif %}
{% if may %}<h2 id="new">New event<span class="count">for an account whose promotions are typed here — the window defaults to the account's promotional week; the plan supplies the response from the mechanic unless you override it, with a note</span></h2>
<form class="entry" method="post" action="{{ url_for('plan.event_new') }}" id="newevent">
<label>account<select name="account_code" id="ne_account">{% for a in accounts %}<option value="{{ a.account_code }}" data-week="{{ a.promo_week_start or '' }}" data-next="{{ next_start[a.account_code] }}">{{ a.account_code }} · {{ a.account_name }}{{ ' (promotions system)' if a.promotions_master == 'TPM' }}{{ ' · weeks start ' + a.promo_week_start if a.promo_week_start }}</option>{% endfor %}</select></label>
<label>promo group<select name="promo_group_code">{% for g in groups %}<option value="{{ g.promo_group_code }}">{{ g.promo_group_code }} · {{ g.promo_group_name }}</option>{% endfor %}</select></label>
<label>shopper window from<input name="window_start" id="ne_start" type="date" required></label>
<label>promotional weeks<input name="weeks" id="ne_weeks" type="number" min="1" step="1" value="2"></label>
<label>to<input name="window_end" id="ne_end" type="date" required></label>
<label>mechanic<select name="mechanic">{% for m in mechanics %}<option value="{{ m.mechanic }}">{{ m.mechanic }} · {{ m.family.replace('_', ' ') }} · uplift {{ m.default_uplift_pct|pct1 }}, dip {{ m.default_dip_pct|pct1 }}</option>{% endfor %}</select></label>
<label>status<select name="status"><option>agreed</option><option>proposed</option></select></label>
<label>price reduction per case<input name="tpr_per_case" type="number" step="0.01" min="0" value="0"></label>
<label>scan funding per case<input name="scan_funding_per_case" type="number" step="0.01" min="0" value="0"></label>
<label>fixed fee — catalogue, display<input name="fixed_fee" type="number" step="1" min="0" value="0"></label>
<label>retail media<input name="media_fee" type="number" step="1" min="0" value="0"></label>
<label>drawn from the co-op envelope<input name="envelope_drawdown" type="number" step="1" min="0" value="0"></label>
<label>uplift (blank: the mechanic's)<input name="uplift_pct" type="number" step="0.01" min="0" placeholder="e.g. 0.6 for +60%"></label>
<label>dip (blank: the mechanic's)<input name="dip_pct" type="number" step="0.01" min="0" placeholder="e.g. 0.15"></label>
<label class="wide">note<textarea name="note" rows="2" placeholder="required when the response is overridden"></textarea></label>
<div class="actions"><button class="primary">Place event</button><span class="hint">on {{ version }} by {{ who }} as at today — in the calendar after the next run; a window off the account's promotional week is placed and flagged</span></div></form>
<script>(()=>{const a=document.getElementById('ne_account'),s=document.getElementById('ne_start'),w=document.getElementById('ne_weeks'),e=document.getElementById('ne_end');
const end=()=>{if(!s.value)return;const d=new Date(s.value+'T00:00:00Z');d.setUTCDate(d.getUTCDate()+7*Math.max(1,+w.value||1)-1);e.value=d.toISOString().slice(0,10)};
const pick=()=>{const o=a.selectedOptions[0];if(o&&o.dataset.next){s.value=o.dataset.next;end()}};a.addEventListener('change',pick);s.addEventListener('change',end);w.addEventListener('input',end);pick()})()</script>{% endif %}
{% if last %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else ('!' if c.flag else '✕') }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}"""

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _next_promo_start(day: str | None, after: dt.date) -> dt.date:
    """The next day on or after `after` that starts the account's promotional week; with no promotional week, the next Monday."""
    want = WEEKDAYS.index(day) if day in WEEKDAYS else 0
    return after + dt.timedelta(days=(want - after.weekday()) % 7)


@plan.get("/events")
def events():
    try:
        who = _who(); version = reads.default_version()
        cal = reads.events(); accts = reads.accounts_master()
        fam: dict[str, int] = {}
        for e in cal:
            fam[e["mechanic_family"]] = fam.get(e["mechanic_family"], 0) + 1
        after = max(dt.date.today(), reads.open_period_start() or dt.date.today())
        next_start = {a["account_code"]: _next_promo_start(a["promo_week_start"], after).isoformat() for a in accts}
        return _page(EVENTS, title="Promotions", active="events", width="none", version=version, cal=cal,
                     n_sender=sum(1 for e in cal if e["source"] == "sender"), n_plan=sum(1 for e in cal if e["source"] == "plan"),
                     held_events=reads.events_held(), refused=reads.events_refused(), cancelled=reads.events_cancelled(),
                     files=promotions.sender_files(), waiting=len(promotions.waiting()), accounts=accts,
                     groups=reads.promo_groups(), mechanics=reads.mechanics(), pending=promotions.pending(), nbs=reads.neighbours(),
                     families=sorted(fam.items(), key=lambda x: -x[1]), next_start=next_start,
                     may=roles.may(who, "register.promo_calendar.maintain"),
                     may_map=roles.may(who, "mapping.accept") or roles.may(who, "mapping.alter"), last=session.last, receipt_acts=("take_in", "neighbour", "event"))
    except Busy as e:
        return _busy("Promotions", e)


def _date(x: str | None) -> dt.date | None:
    try:
        return dt.date.fromisoformat(x or "")
    except ValueError:
        return None


def _num(x, blank=None) -> float | None:
    """A typed number: thousands separators allowed (the page shows figures that way); not-a-number, infinity and
    anything beyond a trillion are not numbers here."""
    if x is None or str(x).strip() == "":
        return blank
    try:
        v = float(str(x).strip().replace(",", ""))
    except ValueError:
        return None
    return v if math.isfinite(v) and abs(v) <= 1e12 else None


def _window_checks(start: dt.date | None, end: dt.date | None, version: str) -> dict:
    v = reads.version(version) or {}
    hz = reads.horizon(version)
    lo = q("select min(week_start) d from dims.dim_week where period = ?", hz[0])[0]["d"] if hz else None
    hi = q("select max(week_end) d from dims.dim_week where period = ?", hz[-1])[0]["d"] if hz else None
    ok = bool(start and end and lo and start <= end and start >= lo and end <= hi)
    return {"check": "window in horizon", "ok": ok,
            "says": f"{start} – {end} within {v.get('horizon_start')} – {v.get('horizon_end')}" if ok else "window missing, reversed or outside the version's horizon"}


@plan.post("/events/take_in")
def take_in():
    """A file from the promotions system into the landing, then the first pass over the codes nobody has mapped."""
    who = _who(); fid = request.form["file_id"]; version = reads.default_version()
    f = next((x for x in promotions.sender_files() if x["file_id"] == fid), None)
    may = roles.may(who, "register.promo_calendar.maintain")
    checks = [
        {"check": "who may take it in", "ok": may, "says": f"{who} holds {said('register.promo_calendar.maintain')}" if may else f"{who} does not hold {said('register.promo_calendar.maintain')}"},
        {"check": "file waiting", "ok": bool(f and f["events"] and not f["taken_in_at"]),
         "says": f"{fid}: {len(f['events'])} events, {len(f['funding'])} funding lines" if f and f["events"] and not f["taken_in_at"] else f"{fid} is not waiting" + (f" — taken in {f['taken_in_at']}" if f and f["taken_in_at"] else "")},
        {"check": "version open", "ok": bool(version), "says": f"into {version}" if version else "no open version"},
        *door.declared(promotions.DECLARATIONS, f or {}, (f or {}).get("events", [])),
    ]
    placed = receipts.judge(checks)
    if placed:
        promotions.take_in(f, version, who)
        n, says, ran = promotions.first_pass(promotions.unmapped(promotions.codes_in(f["events"], f["funding"])), who)
        checks.append({"check": "first pass on new codes", "ok": ran, "flag": True, "says": says})
    session.last = receipts.write("take_in", who, fid, checks, placed)
    session.say(f"{fid} taken in — {checks[-1]['says']}; the calendar reads it after the next run" if placed
                else "take-in refused: " + "; ".join(c["says"] for c in checks if not c["ok"] and not c.get("flag")), placed)
    return redirect(url_for("plan.events") + "#sender")


CALENDAR = """<h1>Promotions calendar<small>{{ version }} · our trading weeks as the grid, each event as a bar on its true dates · {{ where }}</small></h1>
<form class="toolbar" method="get">{{ context_fields() }}<label>promo group<select name="group" onchange="this.form.submit()"><option value="">every group</option>{% for g in groups %}<option value="{{ g }}" {{ 'selected' if g == group }}>{{ g }}</option>{% endfor %}</select></label></form>
<p class="lede">Our weeks run Monday to Sunday, every week in one period. A customer's promotional week need not: {% for a in weeks_of %}{{ a.account_code }} from {{ a.promo_week_start }}{{ ', ' if not loop.last }}{% else %}none of these accounts keeps one{% endfor %}{% if no_week %}; {{ no_week|join(', ') }} keep{{ 's' if no_week|length == 1 }} none{% endif %}. So a grocer's event starts mid-week and straddles two of our weeks — the plan cuts it by days, never snaps it.</p>
{% if not rows %}<p class="muted">No event in the calendar for {{ where }}.</p>{% else %}
<div class="cal" style="--n:{{ weeks|length }}">
<div class="calrow head"><div class="lab"></div><div class="lane">{% for pp in periods %}<span class="per" style="left:{{ pp.left }}%;width:{{ pp.width }}%">{{ pp.period }}</span>{% endfor %}</div></div>
<div class="calrow head wk"><div class="lab small muted">week starting</div><div class="lane">{% for w in weeks %}{% if loop.index0 % 2 == 0 %}<span class="wk" style="left:{{ w.left }}%">{{ w.week_start.strftime('%d %b') }}</span>{% endif %}{% endfor %}</div></div>
{% for r in rows %}{% if r.account_head %}<div class="calrow acct"><div class="lab"><b>{{ r.account_code }}</b> <span class="small muted">{{ r.account_name }}{% if r.promo_week_start %} · promotional week from {{ r.promo_week_start }}{% endif %}</span></div><div class="lane"></div></div>{% endif %}
<div class="calrow {{ 'sel' if r.event_id == sel }}"><div class="lab small"><a href="{{ r.href }}">{{ r.event_id }}</a> <span class="muted">{{ r.promo_group_code }}</span></div>
<div class="lane">{% for t in r.ticks %}<i class="pw" style="left:{{ t }}%"></i>{% endfor %}
<a class="bar fam-{{ r.mechanic_family }}{{ ' offweek' if r.off_week }}" href="{{ r.href }}" style="left:{{ r.left }}%;width:{{ r.width }}%" title="{{ r.event_id }} · {{ r.mechanic }} · {{ r.window_start }} – {{ r.window_end }}{{ ' · ' + r.off_week_says if r.off_week }}">{{ r.mechanic.replace('_', ' ') }}</a>
{% if r.dip_width %}<span class="dipbar" style="left:{{ r.left + r.width }}%;width:{{ r.dip_width }}%" title="the dip after the window"></span>{% endif %}</div></div>{% endfor %}
</div>
<p class="hint">Solid rules are our weeks (Monday); the dotted rules in a grocer's row are its promotional weeks. The hatched tail after a bar is the dip in the seven days after the window. An outlined bar off the grocer's rules is off the account's promotional week — placed, flagged. Open an event for the split it produces.</p>{% endif %}
{% if ev %}<h2 id="split">{{ ev.event_id }} on our grid<span class="count">{{ ev.account_code }} · {{ ev.promo_group_code }} · {{ ev.mechanic.replace('_', ' ') }} · {{ ev.window_start.strftime('%A %d %b') }} – {{ ev.window_end.strftime('%A %d %b %Y') }} · {{ ev.window_days }} days</span></h2>
{% if ev.off_week %}<p class="flash bad">{{ ev.off_week_says }} — placed, flagged; the grid cuts it by days as it stands.</p>{% endif %}
<table><thead><tr><th>Trading week</th><th>Period</th><th class="n">Days of the window</th><th class="n">Uplift, cases</th><th class="n">Days of the dip</th><th class="n">Dip, cases</th>{% if split_nb %}<th class="n">Neighbours, cases</th>{% endif %}</tr></thead><tbody>
{% for w in split %}<tr><td>{{ w.week_start.strftime('%a %d %b') }} – {{ w.week_end.strftime('%a %d %b') }}</td><td>{{ w.period }}</td><td class="n">{{ w.window_days|n if w.window_days else '' }}</td><td class="n">{{ w.uplift_cases|n if w.uplift_cases else '' }}</td>
<td class="n">{{ w.dip_days|n if w.dip_days else '' }}</td><td class="n">{{ w.dip_cases|n if w.dip_cases else '' }}</td>{% if split_nb %}<td class="n">{{ w.neighbour_cases|n if w.neighbour_cases else '' }}</td>{% endif %}</tr>{% endfor %}
<tr class="total"><td>Total</td><td>{{ split_periods|join(', ') }}</td><td class="n">{{ split|sum(attribute='window_days')|n }}</td><td class="n">{{ split|sum(attribute='uplift_cases')|n }}</td><td class="n">{{ split|sum(attribute='dip_days')|n }}</td><td class="n">{{ split|sum(attribute='dip_cases')|n }}</td>{% if split_nb %}<td class="n">{{ split|sum(attribute='neighbour_cases')|n }}</td>{% endif %}</tr>
</tbody></table>
<p class="hint">The same event lands in {{ split|selectattr('window_days')|list|length }} of our weeks{% if split_periods|length > 1 %} and {{ split_periods|length }} periods{% endif %}, each share in proportion to its days — the uplift on the baseline of every material in the group at every ship-to of the account, day-weighted.</p>{% endif %}
<style>.cal{background:var(--panel);border:1px solid var(--rule);border-radius:var(--radius);box-shadow:var(--shadow);padding:.6rem .8rem;overflow-x:auto}
.calrow{display:grid;grid-template-columns:15rem minmax(36rem,1fr);align-items:center;min-height:1.9rem}.calrow+.calrow{border-top:1px solid var(--rule)}.calrow.head{border-top:0;min-height:1.4rem}
.calrow .lab{padding-right:.6rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.calrow .lab a{text-decoration:none}.calrow.sel{background:var(--hover)}
.lane{position:relative;height:100%;min-height:1.9rem;background-image:linear-gradient(to right,var(--rule) 1px,transparent 1px);background-size:calc(100% / var(--n)) 100%}
.pw{position:absolute;top:0;bottom:0;border-left:1px dotted var(--faint)}
.calrow.head .lane,.calrow.acct .lane{background-image:none}.calrow.acct{background:var(--soft)}
.per{position:absolute;top:0;font-size:.72rem;font-weight:600;color:var(--muted);border-left:1px solid var(--faint);padding-left:.3rem;white-space:nowrap;overflow:hidden}
.wk{position:absolute;top:0;font-size:.66rem;color:var(--muted);white-space:nowrap;padding-left:.15rem}
.bar{position:absolute;top:.3rem;bottom:.3rem;border:1.5px solid var(--series-1);background:var(--panel);border-radius:4px;font-size:.68rem;line-height:1.1;padding:.1rem .3rem;overflow:hidden;white-space:nowrap;text-decoration:none;color:var(--ink)}
.bar.fam-price{background:rgba(var(--ink-rgb),.10)}.bar.offweek{border-style:dashed}.bar:hover{background:var(--hover)}
.dipbar{position:absolute;top:.55rem;bottom:.55rem;background:repeating-linear-gradient(45deg,var(--series-3) 0 2px,transparent 2px 5px);border-radius:0 3px 3px 0}</style>"""


def _pct(d: dt.date, lo: dt.date, days: int) -> float:
    return round((d - lo).days / days * 100, 3)


@plan.get("/calendar")
def calendar():
    """The calendar as a picture: our weeks as the grid, each event a bar on its true dates, filterable by account (and
    promo group); an event opened shows the split it produces — days and cases in each trading week it touches."""
    try:
        version = reads.default_version()
        accts = reads.accounts_master(); by_code = {a["account_code"]: a for a in accts}
        cust = _ctx().get("customer") or "ALL"                                 # the context's customer: the accounts beneath it
        account = by_code.get(cust)
        under = None if cust == "ALL" else reads.accounts_under(cust)
        group = request.args.get("group") or ""
        cal = reads.events()
        shown = [e for e in cal if (under is None or e["account_code"] in under) and (not group or e["promo_group_code"] == group)]
        rows, weeks, periods, days, lo = [], [], [], 1, None
        if shown:
            first = min(e["window_start"] for e in shown); last = max(e["window_end"] for e in shown) + dt.timedelta(days=7)
            weeks = reads.weeks_between(first, last)
            lo, hi = weeks[0]["week_start"], weeks[-1]["week_end"] + dt.timedelta(days=1)
            days = (hi - lo).days
            for w in weeks:
                w["left"] = _pct(w["week_start"], lo, days)
            for pp in sorted({w["period"] for w in weeks}):
                ws = [w for w in weeks if w["period"] == pp]
                periods.append({"period": pp, "left": _pct(ws[0]["week_start"], lo, days), "width": round(len(ws) * 7 / days * 100, 3)})
            prev = None
            for e in sorted(shown, key=lambda e: (e["account_code"], e["window_start"])):
                a = by_code.get(e["account_code"], {})
                day = a.get("promo_week_start")
                off = (WEEKDAYS.index(day) - lo.weekday()) % 7 if day in WEEKDAYS else 0
                ticks = [_pct(lo + dt.timedelta(days=off + 7 * k), lo, days) for k in range(len(weeks))] if day in WEEKDAYS else []
                rows.append({**e, "account_head": e["account_code"] != prev, "account_name": a.get("account_name"), "promo_week_start": day, "ticks": ticks,
                             "left": _pct(e["window_start"], lo, days), "width": round(((e["window_end"] - e["window_start"]).days + 1) / days * 100, 3),
                             "dip_width": round(7 / days * 100, 3) if e["dip_pct"] else 0,
                             "href": url_for("plan.calendar", group=group or None, event=e["event_id"]) + "#split"})
                prev = e["account_code"]
        sel = request.args.get("event")
        ev = next((e for e in cal if e["event_id"] == sel), None)
        split = reads.event_split(sel) if ev else []
        in_view = [by_code[c] for c in sorted({e["account_code"] for e in shown})] if shown else ([account] if account else [])
        return _page(CALENDAR, title="Promotions calendar", active="calendar", width="none", version=version, accounts=accts, account=account,
                     where=reads.node_label("customer", cust),
                     groups=sorted({e["promo_group_code"] for e in cal}), group=group, rows=rows, weeks=weeks, periods=periods, days=days,
                     weeks_of=[a for a in in_view if a.get("promo_week_start")], no_week=[a["account_code"] for a in in_view if not a.get("promo_week_start")],
                     sel=sel, ev=ev, split=split, split_nb=any(w["neighbour_cases"] for w in split),
                     split_periods=sorted({w["period"] for w in split if w["window_days"]}))
    except Busy as e:
        return _busy("Promotions calendar", e)


def _week_check(acct: dict, start: dt.date | None, end: dt.date | None) -> dict:
    """Flagged, never refused: the dates are the author's to state; the grid cuts the window by days either way."""
    day = acct.get("promo_week_start")
    if not day or not (start and end):
        return {"check": "on the account's promotional week", "ok": True, "flag": True, "says": f"{acct.get('account_code') or 'the account'} keeps no promotional week"}
    days = (end - start).days + 1
    ok = start.strftime("%A") == day and days % 7 == 0
    return {"check": "on the account's promotional week", "ok": ok, "flag": True,
            "says": f"{days // 7} whole {acct['account_code']} promotional week{'s' if days // 7 != 1 else ''} from {day}" if ok
                    else f"starts {start.strftime('%A')}, {days} days — {acct['account_code']} promotional weeks start {day}; placed, flagged"}


def _envelope_check(account: str | None, draw: float | None, start: dt.date | None, version: str) -> dict:
    """A drawdown spends the account's co-op envelope: there must be one in force at the window's start; drawing past what
    remains is told, not refused (the agreement is the customer's and Finance's to settle)."""
    if not draw:
        return {"check": "co-op envelope", "ok": True, "says": "draws nothing from a co-op envelope"}
    env = next((e for e in reads.envelopes(version) if e["account_code"] == account and start and e["valid_from"] <= start
                and (e["valid_to"] is None or start <= e["valid_to"])), None)
    if env is None:
        return {"check": "co-op envelope", "ok": False, "says": f"{account} has no co-op envelope in force at {start} — nothing to draw on"}
    left = env["remaining"] - draw
    return {"check": "co-op envelope", "ok": left >= 0, "flag": True,
            "says": f"draws {draw:,.0f} of {env['remaining']:,.0f} remaining in {env['instrument_code']}" if left >= 0
                    else f"draws {draw:,.0f} with {env['remaining']:,.0f} remaining in {env['instrument_code']} — over the envelope by {-left:,.0f}; placed, flagged"}


@plan.post("/events/neighbour")
def neighbour_new():
    """A neighbour line on an event the person owns, from either door: recorded as ours (the sender's file is never
    expected to carry it). A rate of zero takes an existing line out."""
    f = request.form; who = _who(); version = reads.default_version() or ""
    ev = reads.event(f.get("event_id", ""))
    scope = (f.get("scope_material") or "").strip()
    rate = _num(f.get("rate_pct"))
    rate = None if rate is None else rate / 100
    effect = f.get("effect_type")
    groups = {g["promo_group_code"] for g in reads.promo_groups()}
    resolves = scope in groups or reads.is_material(scope)
    may = roles.may(who, "register.promo_calendar.maintain")
    existing = next((n for n in reads.neighbours() if ev and n["event_id"] == ev["event_id"] and n["scope_material"] == scope), None)
    checks = [
        {"check": "who may declare", "ok": may and bool(ev and ev["owner"] == who),
         "says": f"{who} owns {ev['event_id']}" if may and ev and ev["owner"] == who else (f"{ev['event_id']} is owned by {ev['owner']}" if ev else "no such event in the calendar")},
        {"check": "event in the calendar", "ok": ev is not None, "says": f"{ev['event_id']} at {ev['account_code']} on {ev['promo_group_code']}, {ev['window_start']} – {ev['window_end']}" if ev else "the event is not in the calendar"},
        {"check": "neighbour is ours and resolves", "ok": resolves and bool(ev) and scope != (ev or {}).get("promo_group_code"),
         "says": f"{scope} is a range of ours outside the promoted group" if resolves and ev and scope != ev["promo_group_code"] else f"{scope or 'nothing'} is not a promo group or material of ours outside the promoted group"},
        {"check": "rate fits the effect", "ok": rate is not None and -1 <= rate <= 1 and (rate == 0 and existing is not None or (effect == "cannibalisation" and rate < 0) or (effect == "halo" and rate > 0)),
         "says": ("removes the line" if rate == 0 else f"{effect} {rate:+.1%} of the neighbour's baseline in the window") if rate is not None else "not a number"},
    ]
    placed = receipts.judge(checks)
    nid = f"NB-F-{dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
    if placed:
        promotions.NEIGHBOURS.place([{"neighbour_id": nid, "version_id": ev["version_id"], "event_id": ev["event_id"], "scope_material": scope,
                                      "effect_type": effect if rate else (existing or {}).get("effect_type", effect), "rate": rate,
                                      "entered_by": who, "entered_at": dt.datetime.now().isoformat(timespec="seconds"), "note": (f.get("note") or "").strip()}], who)
    session.last = receipts.write("neighbour", who, f"{f.get('event_id')}:{scope}", checks, placed)
    session.say(f"neighbour line on {ev['event_id']} placed — the event reads net of it after the next run" if placed
                else "neighbour line refused: " + "; ".join(c["says"] for c in checks if not c["ok"]), placed)
    return redirect(url_for("plan.events") + "#neighbours")


@plan.post("/events/new")
def event_new():
    """An event typed in the plan: the plan's checks, then the act — a file in the landing and a receipt."""
    f = request.form; who = _who(); version = reads.default_version() or ""
    v = reads.version(version)
    acct = reads.account(f.get("account_code", "")) or {}
    mech = next((m for m in reads.mechanics() if m["mechanic"] == f.get("mechanic")), None)
    groups = {g["promo_group_code"] for g in reads.promo_groups()}
    start, end = _date(f.get("window_start")), _date(f.get("window_end"))
    tpr, scan, fee = _num(f.get("tpr_per_case"), 0.0), _num(f.get("scan_funding_per_case"), 0.0), _num(f.get("fixed_fee"), 0.0)
    media, draw = _num(f.get("media_fee"), 0.0), _num(f.get("envelope_drawdown"), 0.0)
    up, dip = _num(f.get("uplift_pct")), _num(f.get("dip_pct"))
    up_given, dip_given = str(f.get("uplift_pct") or "").strip() != "", str(f.get("dip_pct") or "").strip() != ""
    overridden = bool(mech) and ((up_given and up != mech["default_uplift_pct"]) or (dip_given and dip != mech["default_dip_pct"]))
    note = (f.get("note") or "").strip()
    may = roles.may(who, "register.promo_calendar.maintain")
    numbers = all(x is not None and x >= 0 for x in (tpr, scan, fee, media, draw)) and (not up_given or (up is not None and up >= 0)) and (not dip_given or (dip is not None and dip >= 0))
    checks = [
        {"check": "version open", "ok": bool(v and v["status"] == "open"), "says": f"{version} is {v['status'] if v else 'unknown'}"},
        {"check": "who may enter", "ok": may, "says": f"{who} holds {said('register.promo_calendar.maintain')}" if may else f"{who} does not hold {said('register.promo_calendar.maintain')}"},
        {"check": "account's promotions typed here", "ok": acct.get("promotions_master") == "PLAN",
         "says": f"{acct.get('account_code')} promotions are typed in the plan" if acct.get("promotions_master") == "PLAN"
                 else (f"{acct.get('account_code')} promotions come from the promotions system — enter them there" if acct else "unknown account")},
        {"check": "promo group known", "ok": f.get("promo_group_code") in groups, "says": f"{f.get('promo_group_code')} is a promo group" if f.get("promo_group_code") in groups else f"{f.get('promo_group_code')} is not a promo group"},
        _window_checks(start, end, version),
        {"check": "mechanic known", "ok": mech is not None, "says": f"{mech['mechanic']} ({mech['family']})" if mech else f"{f.get('mechanic')} is not a mechanic on the register"},
        {"check": "funding are numbers", "ok": numbers, "says": "price reduction, scan funding, fee and any response are numbers, none below zero" if numbers else "a funding or response value is not a number, or below zero"},
        {"check": "status", "ok": f.get("status") in ("agreed", "proposed"), "says": f"{f.get('status')} — " + ("in the calendar after the next run" if f.get("status") == "agreed" else "a candidate, held out of the calendar")},
        {"check": "override carries a note", "ok": not overridden or bool(note),
         "says": ("response overridden: " + note) if overridden and note else ("response overridden without a note — say why" if overridden else
                 (f"response from the mechanic: uplift {mech['default_uplift_pct']:.0%}, dip {mech['default_dip_pct']:.0%}" if mech else "no mechanic"))},
        _envelope_check(acct.get("account_code"), draw, start, version),
        _week_check(acct, start, end),
        {"check": "scan funding charged", "ok": not scan or bool(acct.get("supplies_scan_data")), "flag": True,
         "says": "no scan funding" if not scan else (f"{acct.get('account_code')} supplies scan data" if acct.get("supplies_scan_data") else f"{acct.get('account_code')} supplies no scan data — the scan funding is carried and not charged")},
    ]
    placed = receipts.judge(checks)
    eid = f"EV-F-{dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
    if placed:
        promotions.TYPED.place([{"event_id": eid, "version_id": version, "account_code": acct["account_code"], "promo_group_code": f["promo_group_code"],
                                 "window_start": start.isoformat(), "window_end": end.isoformat(), "mechanic": mech["mechanic"],
                                 "uplift_pct": up if up_given else "", "dip_pct": dip if dip_given else "", "tpr_per_case": tpr,
                                 "scan_funding_per_case": scan, "fixed_fee": fee, "media_fee": media, "envelope_drawdown": draw,
                                 "status": f["status"], "owner": who, "baseline_version": version,
                                 "note": note, "entered_on": dt.date.today().isoformat()}], who)
    session.last = receipts.write("event", who, eid, checks, placed)
    session.say(f"{eid} placed at {acct.get('account_code')} — in the calendar after the next run" if placed
                else "event refused: " + "; ".join(c["says"] for c in checks if not c["ok"] and not c.get("flag")), placed)
    return redirect(url_for("plan.events") + ("#calendar" if placed else "#new"))


# ---- the mapping review ----
MAPPING = """<h1>Mapping review<small>the promotions system's codes onto ours — accept the proposal, or map it to another of ours with a reason; an event waits until every code it uses is accepted or mapped</small></h1>
{% if pending %}<p class="hint">{{ pending }} act{{ '' if pending == 1 else 's' }} placed since the last run — this list shows {{ 'it' if pending == 1 else 'them' }} after the run.</p>{% endif %}
<h2 id="waiting">Waiting for a decision<span class="count">{{ door_items|length }} code{{ '' if door_items|length == 1 else 's' }} · lowest confidence first · a decision stands for every later file</span></h2>
""" + door.QUEUE + """
{% if missing and may_alter %}<form method="post" action="{{ url_for('plan.mapping_propose') }}"><button class="act">Propose for the {{ missing }} code{{ '' if missing == 1 else 's' }} not mapped</button>
<span class="hint">the first pass, for codes it has never proposed</span></form>{% endif %}
<h2 id="force">In force<span class="count">the latest decision per code</span></h2>
""" + door.DECIDED + """
{% if last %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else ('!' if c.flag else '✕') }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}"""


@plan.get("/mapping")
def mapping():
    try:
        who = _who(); review = reads.mapping_review()
        return _page(MAPPING, title="Mapping review", active="mapping", width="none", **doors.page_context("TPM", who, review),
                     door_decided=doors.decided("TPM"), missing=sum(1 for r in review if r["review_state"] == "missing"),
                     pending=len(doors.ACTS.pending()), may_alter=roles.may(who, "mapping.alter"), last=session.last, receipt_acts=("mapping", "tpm."))
    except Busy as e:
        return _busy("Mapping review", e)


STRUCTURE = """<h1>Their structure to ours<small>how the promotions system's codes land on the plan's structure — five subjects, each code to one of ours, and what ours is</small></h1>
<div class="card note"><table class="pairs"><thead><tr><th>The promotions system keeps</th><th></th><th>The plan reads it as</th><th>Which places the event</th></tr></thead><tbody>
<tr><td><b>Planning account</b> — who the event is negotiated with</td><td>→</td><td><b>Account</b></td><td>at every ship-to of the account, in its planning unit; its promotions kept in one place only</td></tr>
<tr><td><b>Product group</b> — the range on promotion</td><td>→</td><td><b>Promo group</b></td><td>on every material in the group: the cases are planned at the material</td></tr>
<tr><td><b>Tactic</b> — what the shopper sees</td><td>→</td><td><b>Mechanic</b>, in one of seven families</td><td>the volume shape: uplift in the window, dip after</td></tr>
<tr><td><b>Fund type</b> — what the supplier pays and how</td><td>→</td><td><b>Funding type</b></td><td>a line of the gross-to-net: per case on invoice or off, or a lump sum on the event — or carried, not yet priced</td></tr>
<tr><td><b>Status</b> — their word for the event's state</td><td>→</td><td><b>Status</b></td><td>whether it is in the calendar</td></tr></tbody></table></div>
{% if example %}<h2>One event, both ways<span class="count">{{ example.event_id }} as sent, and as the plan reads it</span></h2>
<table><thead><tr><th>Subject</th><th>Their code</th><th>Their description</th><th></th><th>Ours</th><th>What ours is</th></tr></thead><tbody>
{% for x in example.lines %}<tr><td>{{ x.say }}</td><td><code>{{ x.local_code }}</code></td><td>{{ x.local_description or '' }}</td><td>→</td><td>{{ x.target_code or '—' }}</td><td class="small">{{ x.what }}</td></tr>{% endfor %}
</tbody></table>{% endif %}
{% for subj in order %}<h2 id="{{ subj }}">{{ say[subj]|capitalize }} → {{ ours_say[subj] }}<span class="count">{{ by[subj]|length }} code{{ '' if by[subj]|length == 1 else 's' }}</span></h2>
<table><thead><tr><th>Their code</th><th>Their description</th><th></th><th>Ours</th><th>What ours is</th><th>State</th></tr></thead><tbody>
{% for m in by[subj] %}<tr class="{{ '' if m.in_force else 'added' }}"><td><code>{{ m.local_code }}</code></td><td>{{ m.local_description or '' }}</td><td>→</td>
<td>{% if m.target_code %}{{ m.target_code }} <span class="muted small">{{ m.target_name or '' }}</span>{% else %}<span class="muted">not mapped</span>{% endif %}</td>
<td class="small">{{ m.what }}</td><td>{% if m.in_force %}{{ m.review_state }}{% else %}<a href="{{ url_for('plan.mapping') }}#{{ m.subject }}-{{ m.local_code }}-ALL"><span class="state">{{ 'proposed' if m.review_state == 'proposed' else 'waiting' }}</span></a>{% endif %}</td></tr>{% endfor %}
</tbody></table>{% endfor %}
<p class="hint">Rows marked at the left edge are not yet in force: a proposal waiting for review, or a code seen in a file and not mapped — every event that uses one is held until it is. Our lists are fixed; a reviewer places a code on one of ours, never adds to them.</p>
<style>table.pairs{box-shadow:none;background:transparent;border:0}table.pairs td,table.pairs th{background:transparent;border-bottom:1px solid var(--rule)}</style>"""

OURS_SAY = {"customer": "account", "material": "promo group", "mechanic": "mechanic", "funding_type": "funding type", "status": "status"}


def _what(subject: str, o: dict | None) -> str:
    """What one of ours is, in the plan's structure, in a line."""
    if not o:
        return ""
    if subject == "customer":
        return (f"{o['name']} · {o['channel']} · planned in {o['planning_unit_name']} · promotions "
                + ("from the promotions system" if o["promotions_master"] == "TPM" else "typed in the plan")
                + (f" · promotional week from {o['promo_week_start']}" if o.get("promo_week_start") else ""))
    if subject == "material":
        names = (o["material_names"] or "").split("; ")
        return f"{o['materials']} material{'s' if o['materials'] != 1 else ''}: " + "; ".join(names[:4]) + (f"; and {len(names) - 4} more" if len(names) > 4 else "")
    if subject == "mechanic":
        return f"{o['family'].replace('_', ' ')} · default uplift {o['default_uplift_pct']:.0%}, dip {o['default_dip_pct']:.0%}"
    if subject == "funding_type":
        col = {"tpr_per_case": "price reduction per case, on invoice", "scan_funding_per_case": "scan funding per case, off invoice",
               "fixed_fee": "a fixed fee on the event", "media_fee": "retail media, a lump sum on the event",
               "envelope_drawdown": "drawn from the account's co-op envelope, a lump sum on the event"}.get(o.get("event_column") or "")
        return ("priced as " + col) if o["priced"] and col else "carried on the event and shown, not yet priced"
    if subject == "status":
        return "in the calendar" if o["enters_calendar"] in (True, "Y") else "out of the calendar"
    return ""


@plan.get("/mapping/structure")
def mapping_structure():
    try:
        st = reads.mapping_structure()
        for subj, rows in st.items():
            for m in rows:
                m["what"] = _what(subj, m["ours"])
        example = None
        sent = next((e for e in reads.events() if e["source"] == "sender" and e["local_codes"]), None)
        if sent:
            raw = q("select local_account, local_product_group, local_tactic, local_status, account_code, promo_group_code, mechanic, status from plan.promo_sender_event where event_id = ?", sent["event_id"])[0]
            fund = q("select local_fund_type, funding_type from plan.promo_funding where event_id = ? order by line_no", sent["event_id"])
            pairs = [("customer", raw["local_account"], raw["account_code"]), ("material", raw["local_product_group"], raw["promo_group_code"]),
                     ("mechanic", raw["local_tactic"], raw["mechanic"]), ("status", raw["local_status"], raw["status"])] + \
                    [("funding_type", f_["local_fund_type"], f_["funding_type"]) for f_ in fund]
            lines = []
            for subj, code, target in pairs:
                m = next((x for x in st.get(subj, []) if x["local_code"] == code), {})
                lines.append({"say": promotions.SAY[subj], "local_code": code, "local_description": m.get("local_description"), "target_code": target, "what": m.get("what", "")})
            example = {"event_id": sent["event_id"], "lines": lines}
        return _page(STRUCTURE, title="Their structure to ours", active="structure", width="none", by={k: st.get(k, []) for k in promotions.SUBJECTS},
                     order=promotions.SUBJECTS, say=promotions.SAY, ours_say=OURS_SAY, example=example)
    except Busy as e:
        return _busy("Their structure to ours", e)


@plan.post("/door/<key>/decide")
def door_decide(key: str):
    """One decision about one item at any door, from the shared queue: checked against the kind's resolutions and who
    may decide it, placed as one act in the doors' register, receipted. The latest act per item is in force."""
    f = request.form; who = _who()
    nxt = f.get("next") or "/"
    nxt = nxt if nxt.startswith("/") and not nxt.startswith("//") else "/"
    d = doors.DOORS.get(key)
    if d is None:
        session.say(f"no door {key}", False)
        return redirect(nxt)
    kind, item, scope = f.get("kind", ""), f.get("item_code", ""), f.get("scope_code", "") or "ALL"
    r = d.decide(who=who, kind=kind, item_code=item, scope_code=scope, resolution=f.get("resolution", ""), target=f.get("target_code", ""),
                 reason=f.get("reason", ""), waiting=doors.waiting(key, kind, item, scope), ours=doors.ours, may=doors.may)
    session.last = r["receipt"]
    session.say(r["says"], r["placed"])
    return redirect(nxt + "#waiting" if key == "TPM" else nxt + "#queue")


@plan.post("/mapping/propose")
def mapping_propose():
    """The first pass again, for codes on the review list that nobody has proposed — when it could not run at take-in."""
    who = _who()
    codes = {s: {} for s in promotions.SUBJECTS}
    for r in reads.mapping_review():
        if r["review_state"] == "missing":
            codes[r["subject"]][r["local_code"]] = r["local_description"] or ""
    codes = promotions.unmapped(codes)
    may = roles.may(who, "mapping.alter")
    checks = [{"check": "who may propose", "ok": may, "says": f"{who} holds {said('mapping.alter')}" if may else f"{who} does not hold {said('mapping.alter')}"}]
    if may:
        n, says, ran = promotions.first_pass(codes, who)
        checks.append({"check": "first pass", "ok": ran, "flag": True, "says": says})
    placed = receipts.judge(checks)
    session.last = receipts.write("mapping.propose", who, "first pass", checks, placed)
    session.say(checks[-1]["says"], placed and checks[-1]["ok"])
    return redirect(url_for("plan.mapping"))


FORECAST = """<h1>Statistical forecast<small>{{ version }} · the baseline each account's plan stands on, where it is made, and where the forecasting system's structures and ours disagree</small></h1>
{% if mine %}<p class="small">{% if showing_all %}All accounts · <a href="{{ url_for('plan.forecast') }}">only yours ({{ mine|join(', ') }})</a>{% else %}Your accounts: {{ mine|join(', ') }} · <a href="{{ url_for('plan.forecast', accounts='all') }}">all accounts</a>{% endif %} — each planner takes in the run for their own accounts and decides what disagrees there.</p>{% endif %}
{% if pending %}<p class="hint">{{ pending }} file{{ '' if pending == 1 else 's' }} placed since the last run — this page shows {{ 'it' if pending == 1 else 'them' }} after the run.</p>{% endif %}
{% if run %}<div class="cards"><div class="card stat"><span>run{{ 's' if in_force_ids|length > 1 }} in force</span><b>{{ in_force_ids|join(' · ') }}</b><div class="small muted">{{ runs_in_force|length }} account{{ '' if runs_in_force|length == 1 else 's' }}{% if in_force_ids|length > 1 %} · not every account has taken the latest{% endif %}</div></div>
<div class="card stat"><span>series in the plan</span><b>{{ states.in.series|n if states.in else 0 }}</b><div class="small muted">{{ states.in.cases|k if states.in else 0 }} cases over {{ run.horizon_weeks }} weeks</div></div>
<div class="card stat"><span>against our calculation</span><b>{{ total.departure|pct1s }}</b><div class="small muted">{{ total.landed|k }} sent · {{ total.ours|k }} ours, same series and weeks</div></div>
<div class="card stat"><span>waiting for a decision</span><b>{{ door_items|length }}</b><div class="small muted">{{ held_cases|k }} cases held out · {{ gap_cases|k }} on our calculation</div></div></div>
<h2 id="inforce">In force, account by account<span class="count">the file arrives once; each account's planner takes in their own series, and the latest taken in for an account is the one its plan reads</span></h2>
<table><thead><tr><th>Account</th><th>Run in force</th><th>Made</th><th>History to</th><th>Taken in by</th><th>At</th></tr></thead><tbody>
{% for r in runs_in_force %}<tr><td>{{ r.account_code }}</td><td>{{ r.run_id }}</td><td>{{ r.made_on }}</td><td>{{ r.last_history_week }}</td><td>{{ r.taken_in_by }}</td><td class="small">{{ r.taken_in_at }}</td></tr>{% endfor %}</tbody></table>
<h2>What the run says it is<span class="count">{{ run.run_id }}, the latest in force here</span></h2>
<table><tbody><tr><th>What the numbers are</th><td>{{ 'baseline only — promotions removed; the plan adds them from the calendar' if run.content == 'baseline_only' else run.content }}</td></tr>
<tr><th>Fitted on</th><td>{{ run.history_basis }}, to week {{ run.last_history_week }}</td></tr>
<tr><th>Method</th><td>{{ run.method_note }}</td></tr>
<tr><th>Reach</th><td>{{ run.horizon_weeks }} weeks, {{ run.first_week }} to {{ run.last_day }}; past that the plan continues on our own calculation</td></tr>
<tr><th>Grain</th><td>{{ run.grain }}; the plan spreads each series to the account's ship-tos by its own history shape</td></tr>
<tr><th>Not sent with this run</th><td class="muted">the model chosen per series, its components, the fitted values and the interval — what follows is what the plan can read without them</td></tr></tbody></table>
{% else %}<p class="muted">No run from the forecasting system has been taken in for these accounts: their baseline is our own calculation.</p>{% endif %}
<h2 id="sources">Where each account's baseline is made<span class="count">cases over the weeks of each account's run in force</span></h2>
<table><thead><tr><th>Account</th><th>Baseline</th><th>Run in force</th><th class="n">Series sent</th><th class="n">From the run</th><th class="n">Our calculation, same series</th><th class="n">Departure</th><th class="n">On our calculation meanwhile</th></tr></thead><tbody>
{% for a in sources %}<tr><td>{{ a.account_name }} <span class="muted">{{ a.account_code }}</span></td><td>{{ 'forecasting system' if a.baseline_source == 'FORECAST' else 'calculated in the plan' }}</td><td>{{ a.run_id or '' }}</td>
<td class="n">{{ a.series|n if a.series else '' }}</td><td class="n">{{ a.landed|n if a.landed else '' }}</td><td class="n">{{ a.ours|n if a.ours else '' }}</td>
<td class="n delta {{ a.departure|dir }}">{{ a.departure|pct1s if a.departure is not none else '' }}</td><td class="n">{{ a.gap|n if a.gap else '' }}</td></tr>{% endfor %}</tbody></table>
<p class="hint">Our calculation is kept for every account as the reference: the same fiscal week averaged over the history, promotion weeks and the week after removed, carried forward at the category's growth. It is crude on purpose — a series the run cannot beat is worth a question.</p>
<h2 id="queue">Waiting for a decision<span class="count">{{ door_items|length }} item{{ '' if door_items|length == 1 else 's' }} · one per series, never per week · a decision stands for later runs</span></h2>
""" + door.QUEUE + """
{% if door_items %}<p class="hint">In the run, not in the plan: it has cases and nowhere to put them — say it is the same as one of our materials (its cases join that material), place it under one of our products (recorded; it stays outside the plan until the structure carries it, because it has no price), or leave it out. In the plan, not in the run: the plan stands on our calculation — keep it, or set it to zero on purpose.</p>{% endif %}
<h2 id="decided">Decided<span class="count">the latest decision per item, in force for this run and the next</span></h2>
""" + door.DECIDED + """
<h2 id="sender">From the forecasting system<span class="count">runs in its outbox, account by account · read each against our calculation before taking it in</span></h2>
{% if runs %}<table><thead><tr><th>Run</th><th>Made</th><th>What the numbers are</th><th>Account</th><th class="n">Series</th><th class="n">Cases sent</th><th class="n">Our calculation, same weeks</th><th class="n">Departure</th><th>State</th><th></th></tr></thead><tbody>
{% for r in runs %}{% for a in r.shown %}<tr>{% if loop.first %}<td rowspan="{{ r.shown|length }}">{{ r.run_id }}</td><td rowspan="{{ r.shown|length }}">{{ r.header.made_on }}</td><td rowspan="{{ r.shown|length }}">{{ 'baseline only' if r.header.content == 'baseline_only' else 'promotions left in (' ~ r.header.content ~ ')' }}</td>{% endif %}
<td>{{ a.account_code }}</td><td class="n">{{ a.n_series }}</td><td class="n">{{ a.cases|n }}</td><td class="n">{{ a.ours|n if a.ours else '' }}</td><td class="n delta {{ a.departure|dir }}">{{ a.departure|pct1s if a.departure is not none else '' }}</td>
<td>{{ 'taken in ' ~ a.taken_in_at ~ ' by ' ~ a.taken_in_by if a.taken_in_at else 'waiting' }}</td>
<td>{% if not a.taken_in_at and a.may %}<form class="inline" method="post" action="{{ url_for('plan.forecast_take_in') }}"><input type="hidden" name="run_id" value="{{ r.run_id }}"><input type="hidden" name="account_code" value="{{ a.account_code }}"><button class="act">Take in for {{ a.account_code }}</button></form>{% elif not a.taken_in_at %}<span class="small muted">{{ a.whose }}</span>{% endif %}</td></tr>{% endfor %}{% endfor %}</tbody></table>
{% else %}<p class="muted">Nothing in the outbox.</p>{% endif %}
{% if run %}<h2 id="departs">Where the run departs most from our calculation<span class="count">material × account over the run's weeks · open one to read it by period</span></h2>
<table><thead><tr><th>Material</th><th>Account</th><th class="n">From the run</th><th class="n">Our calculation</th><th class="n">Difference</th><th class="n">Departure</th></tr></thead><tbody>
{% for d in departures %}<tr><td><a href="{{ url_for('plan.forecast', series_material=d.material_code, series_account=d.account_code) }}#series">{{ d.material_name }}</a> <span class="muted">{{ d.material_code }}</span></td><td>{{ d.account_code }}</td>
<td class="n">{{ d.landed|n }}</td><td class="n">{{ d.ours|n if d.ours else '' }}</td><td class="n">{{ d.diff|signed }}</td><td class="n delta {{ d.departure|dir }}">{{ d.departure|pct1s if d.departure is not none else '' }}</td></tr>{% endfor %}</tbody></table>{% endif %}
{% if series %}<h2 id="series">{{ series_name }}<span class="count">{{ series_material }} at {{ series_account }} · cases by period over the run's weeks</span></h2>
<table><thead><tr><th>Period</th><th class="n">Weeks</th><th class="n">From the run</th><th class="n">Our calculation</th><th class="n">Departure</th><th class="n">Shipped, same period last year</th></tr></thead><tbody>
{% for p in series %}<tr><td>{{ p.period }}</td><td class="n">{{ p.weeks }}</td><td class="n">{{ p.landed|n if p.landed else '' }}</td><td class="n">{{ p.ours|n if p.ours else '' }}</td>
<td class="n delta {{ p.departure|dir }}">{{ p.departure|pct1s if p.departure is not none else '' }}</td><td class="n">{{ p.last_year|n if p.last_year else '' }}</td></tr>{% endfor %}</tbody></table>
<p class="hint">Last year's figure is what was shipped, promotions included; the two forecasts are baseline only.</p>{% endif %}
{% if last %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else ('!' if c.flag else '✕') }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}"""


def _fcst_accounts(who: str) -> tuple[list[str], list[str]]:
    """The accounts whose baseline comes from the forecasting system, and those of them this person takes in and decides for."""
    accts = [r["account_code"] for r in q("select account_code from dims.dim_account where baseline_source = 'FORECAST' order by 1")]
    return accts, [a for a in accts if roles.may(who, "layer.1.enter", a, dimension="customer")]


@plan.get("/forecast")
def forecast():
    """The statistical forecast, opening on the person's own accounts: their runs in force, their sources, their
    departures, their items; every account on request."""
    try:
        who = _who(); version = reads.default_version()
        fc_accts, mine = _fcst_accounts(who)
        showing_all = request.args.get("accounts") == "all" or not mine
        shown = set(fc_accts) if showing_all else set(mine)
        runs_in_force = [r for r in (reads.forecast_runs(version) if version else []) if r["account_code"] in shown]
        run = max(runs_in_force, key=lambda r: (r["taken_in_at"], r["run_id"])) if runs_in_force else None
        sources = [a for a in (reads.forecast_sources(version) if version else []) if showing_all or a["account_code"] in shown]
        reach = lambda i: {x.strip() for x in str(i.get("reaches") or i.get("scope_code") or "").split(",")}
        queue = [i for i in reads.forecast_queue() if showing_all or reach(i) & shown]
        landed = sum(a["landed"] or 0 for a in sources); ours = sum(a["ours"] or 0 for a in sources)
        mat, acct = request.args.get("series_material"), request.args.get("series_account")
        series = reads.forecast_series(version, mat, acct) if run and mat and acct else []
        names = {m["material_code"]: m["material_name"] for m in reads.materials()}
        holders = {a: ", ".join(p for p in reads.holders("layer.1.enter") if roles.may(p, "layer.1.enter", a, dimension="customer")) for a in fc_accts}
        runs = []
        for r in fcst.sender_runs():
            h = r["header"]; first = _date(h.get("first_week")); n = int(_num(h.get("horizon_weeks")) or 0)
            last = first + dt.timedelta(days=7 * n - 1) if first and n else None
            show = []
            for a in r["accounts"]:
                if a["account_code"] not in shown:
                    continue
                ours_a = reads.reference_cases(version, a["account_code"], first, last, a["materials"]) if version and first and last else None
                show.append({**a, "ours": ours_a, "departure": _d(a["cases"], ours_a), "whose": holders.get(a["account_code"], ""),
                             "may": roles.may(who, "layer.1.enter", a["account_code"], dimension="customer")})
            if show:
                runs.append({**r, "shown": show})
        door_ctx = doors.page_context("FCS", who, queue, url_for("plan.forecast", accounts="all") if showing_all and mine else "")
        return _page(FORECAST, title="Statistical forecast", active="forecast", width="none", version=version, run=run, runs_in_force=runs_in_force,
                     in_force_ids=sorted({r["run_id"] for r in runs_in_force}), sources=sources, mine=mine, showing_all=showing_all,
                     states={r["state"]: r for r in reads.forecast_states(version, sorted(shown))} if version else {},
                     total={"landed": landed, "ours": ours, "departure": _d(landed, ours)},
                     held_cases=sum(i["cases"] for i in queue if i["kind"] == "theirs_not_ours"), gap_cases=sum(i["cases"] for i in queue if i["kind"] == "ours_not_theirs"),
                     door_decided=[d for d in _fcst_decided(version) if showing_all or d["scope_code"] == "ALL" or d["scope_code"] in shown],
                     runs=runs, **door_ctx,
                     departures=reads.forecast_departures(version, sorted(shown)) if run else [], series=series, series_material=mat, series_account=acct,
                     series_name=names.get(mat, mat), pending=len(fcst.pending()) + len(doors.ACTS.pending()), last=session.last, receipt_acts=("forecast", "fcs."))
    except Busy as e:
        return _busy("Statistical forecast", e)


def _fcst_decided(version: str | None) -> list[dict]:
    """The forecast door's decisions in force, each with the cases it covers in the run in force (theirs) or on our calculation (ours)."""
    out = []
    for r in (reads.forecast_resolutions(version) if version else []):
        note = ([f"covers {r['cases']:,.0f} cases"] if r.get("cases") else []) + (["outside the plan until the structure carries it"] if r["resolution"] == "place_under" else [])
        out.append({**r, "scope_code": r["account_code"], "item_description": r.get("description"), "note": " · ".join(note)})
    return out


@plan.post("/forecast/take_in")
def forecast_take_in():
    """One account's series from a run into the landing, by the planner whose scope reaches the account (or anyone above
    them) — if the run says its numbers are baseline only and the account takes its baseline from the forecasting system."""
    f = request.form; who = _who(); rid = f.get("run_id", ""); acct = f.get("account_code", ""); version = reads.default_version(); verb = "layer.1.enter"
    r = next((x for x in fcst.sender_runs() if x["run_id"] == rid), None)
    a = next((x for x in (r or {}).get("accounts", []) if x["account_code"] == acct), None)
    h = (r or {}).get("header", {}); rows = [x for x in (r or {}).get("series", []) if x.get("account_code") == acct]
    may = roles.may(who, verb, acct, dimension="customer") if acct else False
    source = (reads.account(acct) or {}).get("baseline_source") if acct else None
    checks = [
        {"check": "who may take it in", "ok": may, "says": f"{who} holds {said(verb)} at {acct}" if may else f"{who} does not hold {said(verb)} at {acct or 'that account'} — the account's planner takes its run in"},
        {"check": "run waiting for the account", "ok": bool(a and not a["taken_in_at"]),
         "says": f"{rid} for {acct}: {a['n_series']} series, {len(rows)} rows" if a and not a["taken_in_at"] else (f"{rid} was taken in for {acct} at {a['taken_in_at']}" if a else f"{rid} sends nothing for {acct or 'that account'}")},
        {"check": "account takes the forecast", "ok": source == "FORECAST", "says": f"{acct}'s baseline comes from the forecasting system" if source == "FORECAST" else f"{acct or 'that account'}'s baseline is calculated in the plan"},
        {"check": "version open", "ok": bool(version), "says": f"into {version}" if version else "no open version"},
        *door.declared(fcst.DECLARATIONS, h, rows),
    ]
    placed = receipts.judge(checks)
    if placed:
        fcst.take_in(r, acct, version, who)
    session.last = receipts.write("forecast.take_in", who, f"{rid}:{acct}", checks, placed)
    session.say(f"{rid} taken in for {acct} — it replaces {acct}'s run in force after the next run of the plan" if placed
                else "take-in refused: " + "; ".join(c["says"] for c in checks if not c["ok"]), placed)
    return redirect(url_for("plan.forecast") + "#sender")


MAINTAINED = """<p class="hint">{% if may_edit %}You maintain {{ what }}: an amendment is a new row from a date — the row in force is never edited — and takes effect on the next run.{% else %}You read {{ what }}; they are maintained by {{ holders|join(', ') or 'nobody yet' }}. Ask them for a change.{% endif %}</p>"""

TERMS = """<h1>Terms<small>the instruments in force, by account — effective-dated; an amendment is a new row from its date</small></h1>
""" + MAINTAINED + """
{% if envelopes %}<h2 id="envelopes">Co-op envelopes<span class="count">{{ version }} · committed for the year, drawn by the events in the calendar, remaining</span></h2>
<table><thead><tr><th>Envelope</th><th>Account</th><th>Year</th><th class="n">Committed</th><th class="n">Drawn</th><th class="n">Remaining</th><th>Drawn by</th></tr></thead><tbody>
{% for e in envelopes %}<tr><td>{{ e.instrument_code }}</td><td>{{ e.account_code }}</td><td>{{ e.valid_from }} – {{ e.valid_to or 'open' }}</td><td class="n">{{ e.committed|n }}</td><td class="n">{{ e.drawn|n }}</td>
<td class="n">{{ e.remaining|n }}{% if e.remaining < 0 %} <span class="state">over</span>{% endif %}</td><td class="small">{{ e.drawn_by or '' }}</td></tr>{% endfor %}</tbody></table>
<p class="hint">The money is counted once, at the event: a drawdown is a lump sum on the event in the gross-to-net; the envelope itself values nothing.</p>{% endif %}
{% for a in groups %}<h2>{{ a.account_name }}<span class="count">{{ a.account_code }} · {{ a.rows|length }} row{{ '' if a.rows|length == 1 else 's' }}</span></h2>
<table><thead><tr><th>Instrument</th><th>Kind</th><th>Driver basis</th><th class="n">Rate</th><th>Flow position</th><th>Conditionality</th><th>Settlement</th><th>Material scope</th><th>Valid from</th><th>Valid to</th><th>Note</th>{% if may_edit %}<th>Amend from a date</th>{% endif %}</tr></thead><tbody>
{% for r in a.rows %}<tr class="{{ 'retired' if r.valid_to and r.valid_to < today }}{{ ' added' if r.amended_by_file }}"><td>{{ r.instrument_code }}</td><td>{{ r.instrument_kind }}</td><td>{{ r.driver_basis }}</td>
<td class="n">{{ r.rate|n if r.driver_basis == 'lump_sum' else r.rate|pct1 }}</td><td>{{ r.flow_position }}</td><td>{{ r.conditionality }}</td><td>{{ r.settlement_timing }}</td><td>{{ r.scope_material or '' }}</td><td>{{ r.valid_from }}</td><td>{{ r.valid_to or '' }}</td><td class="small">{{ r.note or '' }}</td>
{% if may_edit %}<td class="acts">{% if not r.valid_to or r.valid_to >= today %}<form class="inline" method="post" action="{{ url_for('plan.terms_amend') }}"><input type="hidden" name="instrument_code" value="{{ r.instrument_code }}"><input type="hidden" name="row_from" value="{{ r.valid_from }}">
<input name="rate" type="number" step="any" required placeholder="{{ 'amount' if r.driver_basis == 'lump_sum' else 'rate, e.g. 0.02' }}" style="width:7rem"> <input name="valid_from" type="date" required value="{{ next_from }}"> <input name="note" required placeholder="why" size="14"> <button class="act">Amend</button></form>{% endif %}</td>{% endif %}</tr>{% endfor %}
</tbody></table>{% endfor %}
{% if last %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else ('!' if c.flag else '✕') }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}"""


@plan.get("/terms")
def terms():
    try:
        who = _who(); version = reads.default_version()
        names = {a["account_code"]: a["account_name"] for a in q("select account_code, account_name from dims.dim_account")}
        groups: dict[str, dict] = {}
        for r in reads.terms():
            g = groups.setdefault(r["account_code"], {"account_code": r["account_code"], "account_name": names.get(r["account_code"], r["account_code"]), "rows": []})
            g["rows"].append(r)
        verb = "register.terms.maintain"
        return _page(TERMS, title="Terms", active="terms", groups=sorted(groups.values(), key=lambda g: g["account_name"]), version=version,
                     envelopes=reads.envelopes(version) if version else [], may_edit=roles.may(who, verb), holders=reads.holders(verb), verb=verb,
                     what="the terms register", today=dt.date.today(), next_from=_next_monday().isoformat(), last=session.last, receipt_acts=("terms",))
    except Busy as e:
        return _busy("Terms", e)


def _next_monday() -> dt.date:
    """The earliest date an amendment can usefully start: a rate is read at each week's start, so the next Monday on or
    after both today and the first open period."""
    after = max(dt.date.today(), reads.open_period_start() or dt.date.today())
    return after + dt.timedelta(days=(7 - after.weekday()) % 7)


def _from_checks(start: dt.date | None) -> list[dict]:
    first = reads.open_period_start()
    ok = bool(start and first and start >= first)
    monday = bool(start and start.weekday() == 0)
    return [{"check": "from an open period", "ok": ok, "says": f"from {start}, on or after {first}" if ok else f"{start or 'no date'} — nothing is placed before the first open period ({first})"},
            {"check": "from a week's start", "ok": monday, "flag": True,
             "says": f"{start} is a Monday" if monday else (f"{start} is a {start.strftime('%A')} — read from the week starting {start + dt.timedelta(days=(7 - start.weekday()) % 7)}" if start else "no date")}]


@plan.post("/terms/amend")
def terms_amend():
    """Finance amends an instrument from a date: a new row in the register's layout, every attribute carried from the row
    being amended, the new rate and a note. The row in force is never edited; the next run reads the new row from its date."""
    f = request.form; who = _who(); verb = "register.terms.maintain"
    row = next((r for r in reads.terms() if r["instrument_code"] == f.get("instrument_code") and str(r["valid_from"]) == f.get("row_from")), None)
    rate, start, note = _num(f.get("rate")), _date(f.get("valid_from")), (f.get("note") or "").strip()
    may = roles.may(who, verb)
    within = bool(row and start and start >= row["valid_from"] and (row["valid_to"] is None or start <= row["valid_to"]))
    checks = [
        {"check": "who may amend", "ok": may, "says": f"{who} holds {said(verb)}" if may else f"{who} does not hold {said(verb)} — terms are maintained by {', '.join(reads.holders(verb))}"},
        {"check": "instrument on file", "ok": row is not None, "says": f"{row['instrument_code']} ({row['instrument_kind']}) from {row['valid_from']}" if row else "no such instrument row"},
        {"check": "rate is a number", "ok": rate is not None and rate >= 0 and (row is None or row["driver_basis"] == "lump_sum" or rate < 1),
         "says": (f"{rate:,.0f}" if row and row["driver_basis"] == "lump_sum" else f"{rate:.2%}") if rate is not None and rate >= 0 else "not a number, or below zero"},
        *_from_checks(start),
        {"check": "within the row's validity", "ok": within, "says": f"{start} falls within {row['valid_from']} – {row['valid_to'] or 'open'}" if within else "the date is outside the row being amended"},
        {"check": "a note says why", "ok": bool(note), "says": note or "an amendment says why"},
    ]
    placed = receipts.judge(checks)
    if placed:
        TERMS_LANDING.place([{**{k: row[k] for k in ("account_code", "instrument_code", "instrument_kind", "driver_basis", "flow_position", "conditionality",
                                                    "settlement_timing", "scope_material")},
                              "rate": rate, "valid_from": start.isoformat(), "valid_to": row["valid_to"].isoformat() if row["valid_to"] else "", "note": note}], who)
    session.last = receipts.write("terms.amend", who, f.get("instrument_code", ""), checks, placed)
    session.say(f"{row['instrument_code']} amended from {start} — in the plan after the next run" if placed
                else "amendment refused: " + "; ".join(c["says"] for c in checks if not c["ok"] and not c.get("flag")), placed)
    return redirect(url_for("plan.terms"))


PRICE_LISTS = """<h1>Price lists<small>list price per case in the list's currency, effective-dated; an increase is a dated event</small></h1>
""" + MAINTAINED + """
{% if may_edit %}<h2 id="change">Change a price<span class="count">a new row from a date — the price in force stays on file</span></h2>
<form class="entry" method="post" action="{{ url_for('plan.price_change') }}">
<label>price list<select name="price_list">{% for pl in lists %}<option value="{{ pl.price_list }}">{{ pl.price_list }} · {{ pl.currency }}</option>{% endfor %}</select></label>
<label>material<input name="material_code" list="pl_materials" required placeholder="a material on the list"><datalist id="pl_materials">{% for m in materials %}<option value="{{ m }}">{% endfor %}</datalist></label>
<label>price per case<input name="price_per_case" type="number" step="0.01" min="0" required></label>
<label>from<input name="valid_from" type="date" required value="{{ next_from }}"></label>
<label class="wide">event — the increase or change it belongs to<input name="event" required placeholder="PI-2027-02 cost pass-through"></label>
<div class="actions"><button class="primary">Place price change</button><span class="hint">by {{ who }} — read from the week it starts in, after the next run</span></div></form>{% endif %}
{% for pl in lists %}<h2>{{ pl.price_list }}<span class="count">{{ pl.currency }} · {{ pl.materials|length }} materials · on it: {% for a in pl.accounts %}{{ a.account_name }}{{ ', ' if not loop.last }}{% else %}no account{% endfor %}</span></h2>
{% if pl.events %}<table><thead><tr><th>Increase event</th><th>Effective</th><th class="n">Materials repriced</th><th class="n">Average change</th></tr></thead><tbody>
{% for e in pl.events %}<tr><td>{{ e.event }}</td><td>{{ e.effective }}</td><td class="n">{{ e.n }}</td><td class="n">{{ e.avg|pct1s }}</td></tr>{% endfor %}
</tbody></table>{% endif %}
<table><thead><tr><th>Material</th><th class="n">Price before</th><th>Valid</th><th class="n">Price in force</th><th>Valid</th><th class="n">Change</th><th>Event</th></tr></thead><tbody>
{% for m in pl.materials %}{% set c = m.current %}{% set p = m.prior %}<tr class="{{ 'added' if c.placed_by_finance }}"><td>{{ m.material_name }} <span class="muted">{{ m.material_code }}</span></td>
<td class="n">{{ p.price_per_case|n(2) if p else '' }}</td><td>{% if p %}{{ p.valid_from }} to {{ p.valid_to or 'open' }}{% endif %}</td>
<td class="n">{{ c.price_per_case|n(2) }}</td><td>{{ c.valid_from }} to {{ c.valid_to or 'open' }}</td>
<td class="n">{{ m.change|pct1s if m.change is not none else '' }}</td><td>{{ c.price_event or '' }}</td></tr>{% endfor %}
</tbody></table>{% endfor %}
{% if last %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else ('!' if c.flag else '✕') }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}"""


@plan.get("/price_lists")
def price_lists():
    try:
        who = _who(); verb = "register.price_list.maintain"; lists = reads.price_lists()
        return _page(PRICE_LISTS, title="Price lists", active="pricelists", lists=lists, may_edit=roles.may(who, verb), holders=reads.holders(verb), verb=verb,
                     what="the price lists", next_from=_next_monday().isoformat(), last=session.last, receipt_acts=("price",),
                     materials=sorted({m["material_code"] for pl in lists for m in pl["materials"]}))
    except Busy as e:
        return _busy("Price lists", e)


@plan.post("/price_lists/change")
def price_change():
    """Finance changes a list price from a date: a new effective-dated row in the price list's layout. The price in force
    is never edited; the next run reads the new row from the week it starts in."""
    f = request.form; who = _who(); verb = "register.price_list.maintain"
    pl, mat = f.get("price_list", ""), (f.get("material_code") or "").strip()
    price, start, label = _num(f.get("price_per_case")), _date(f.get("valid_from")), (f.get("event") or "").strip()
    on = next((x for x in reads.price_lists() if x["price_list"] == pl), None)
    cur = next((m["current"] for m in (on or {}).get("materials", []) if m["material_code"] == mat), None)
    may = roles.may(who, verb)
    chg = None if not (cur and price) else price / cur["price_per_case"] - 1
    checks = [
        {"check": "who may change a price", "ok": may, "says": f"{who} holds {said(verb)}" if may else f"{who} does not hold {said(verb)} — price lists are maintained by {', '.join(reads.holders(verb))}"},
        {"check": "material on the list", "ok": cur is not None, "says": f"{mat} is on {pl} at {cur['price_per_case']:,.2f} {cur['currency']}" if cur else f"{mat or 'nothing'} is not on {pl}"},
        {"check": "price is a number", "ok": price is not None and price > 0, "says": f"{price:,.2f}" + (f" ({chg:+.1%})" if chg is not None else "") if price else "not a number, or not above zero"},
        *_from_checks(start),
        {"check": "change is modest", "ok": chg is None or abs(chg) <= 0.25, "flag": True, "says": "within ±25% of the price in force" if chg is None or abs(chg) <= 0.25 else f"{chg:+.1%} against the price in force — placed, flagged"},
        {"check": "an event names it", "ok": bool(label), "says": label or "a change belongs to an increase or a correction — name it"},
    ]
    placed = receipts.judge(checks)
    if placed:
        PRICES_LANDING.place([{"price_list": pl, "material_code": mat, "currency": cur["currency"], "price_per_case": price,
                               "valid_from": start.isoformat(), "valid_to": "", "event": label}], who)
    session.last = receipts.write("price.change", who, f"{pl}:{mat}", checks, placed)
    session.say(f"{mat} on {pl} at {price:,.2f} from {start} — in the plan after the next run" if placed
                else "price change refused: " + "; ".join(c["says"] for c in checks if not c["ok"] and not c.get("flag")), placed)
    return redirect(url_for("plan.price_lists"))


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
<span class="hint">{{ 'as ' + who if may_run else who + ' may not run the plan' }}</span></form>
{% if run_log %}<h2>Last run</h2><pre>{{ run_log }}</pre>{% endif %}
{% if pending %}<h2>Waiting for the next run</h2><table><thead><tr><th>File</th></tr></thead><tbody>{% for p in pending %}<tr><td><code>{{ p.name }}</code></td></tr>{% endfor %}</tbody></table>{% endif %}
{% if health %}<h2>Health</h2><table><thead><tr><th>Worklist</th><th>Severity</th><th class="n">Items</th><th>What to do</th><th>Whose</th></tr></thead><tbody>
{% for h in health %}<tr><td>{{ h.name }}</td><td><span class="severity">{{ h.severity }}</span></td><td class="n">{{ h['items'] }}</td><td>{{ h.what_to_do }}</td><td>{{ h.whose }}</td></tr>{% endfor %}</tbody></table>{% endif %}
<h2>Recent acts</h2><table><thead><tr><th>At</th><th>Act</th><th>By</th><th>Subject</th><th>Placed</th></tr></thead><tbody>
{% for r in receipts %}<tr><td>{{ r.at }}</td><td>{{ r.act }}</td><td>{{ r.by }}</td><td><code>{{ r.subject }}</code></td><td class="{{ 'ok' if r.placed else 'no' }}">{{ '✓' if r.placed else '✕' }}</td></tr>{% endfor %}</tbody></table>"""


def _may_run(who: str) -> bool:
    return roles.may(who, "run.plan")


# A run scoped to what Finance's figures can reach: its two registers loaded, the financial forecast and what reads it
# evaluated. Nothing else in the plan reads a Finance figure, so nothing is left behind by stopping here.
FINANCE_RUN = [["uv", "run", "python", "-m", "ingest.pipeline", "--only", "reg_finance_overlay", "reg_finance_source"],
               ["uv", "run", "sqlmesh", "plan", "prod", "--restate-model", "plan.finance_edit+", "--restate-model", "plan.finance_source+",
                "--auto-apply", "--no-prompts"]]


# A release scoped to one act's reach: the commands, what that act's own files waiting are, what the run is called and what
# it says when done. The cost side adds its own (face/schedule.py).
SCOPED: dict[str, dict] = {
    "finance": {"commands": FINANCE_RUN, "pending": FINANCE.pending, "what": "revenue",
                "says": "run completed — Revenue reads Finance's figures; nothing else in the plan reads them"},
}


def _run_plan(who: str, scope: str = "") -> bool:
    """The run, from wherever it was asked for: the landing loaded, the models and checks evaluated, a receipt. Asked for
    from a page with a scoped release (the financial forecast, the opex schedule) it runs that far and no further —
    unless something else is waiting too, when stopping short would leave that file looking taken in: then it is the
    whole run."""
    sc = SCOPED.get(scope)
    scoped = bool(sc) and len(_pending()) - len(sc["pending"]()) == 0
    _close_warehouse(None)              # the run writes the file: this request lets go of its read first
    log = Runner(sc["commands"] if scoped else None).run()
    session.run_log = log
    ok = "✗" not in log
    what = sc["what"] if scoped else "plan"
    receipts.act("run", who, what, ok, "run completed" if ok else "run stopped — see the log")
    session.say((sc["says"] if scoped else "run completed — the pages read the new plan") if ok else "run stopped; the log says where", ok)
    return ok


@plan.get("/run")
def run():
    who = _who() if _principals_ok() else ""
    try:
        h = health(q, HEALTH)
    except Busy:
        h = []
    return _page(RUN, title="Run and health", active="run", may_run=bool(who) and _may_run(who), run_log=session.run_log,
                 pending=_pending(), receipts=receipts.recent(12), health=h)


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
    ok = _run_plan(who, request.form.get("scope") or "")
    nxt = request.form.get("next") or ""
    return redirect(nxt if ok and nxt.startswith("/") and not nxt.startswith("//") else url_for("plan.run"))


# the cost side's pages, in their own module, on this blueprint
costs.register(plan, _page, _who, _ctx, _busy, session, roles)
schedule.register(plan, _page, _who, _ctx, _busy, session, roles, _run_plan, SCOPED)
headcount.register(plan, _page, _who, _ctx, _busy, session, roles)


def main() -> None:
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[plan])
    chassis_app.serve(app, port=8010, watch=pathlib.Path(__file__).parent)


if __name__ == "__main__":
    main()
