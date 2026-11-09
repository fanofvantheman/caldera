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

from . import ENTRY_COLUMNS, HEALTH, SHELL, roles, session
from . import reads

plan = Blueprint("plan", __name__)
ENTRIES = LogLanding("plan", "layer_entry", ENTRY_COLUMNS)
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

VERSION_PICKER = """<form class="toolbar" method="get"><label>version<select name="version" onchange="this.form.submit()">
{% for v in versions %}<option value="{{ v.version_id }}" {{ 'selected' if v.version_id == version }}>{{ v.version_id }} · {{ v.status }}</option>{% endfor %}</select></label>{{ extra|safe }}</form>"""


def _busy(title: str, e: Busy) -> str:
    return _page(f"<h1>{title}</h1><p class='lede'>{e}</p>", title=title)


# ---- the role's home: what the processes you reach expect of you ----
HOME = """<h1>{{ who }}<small>what the processes you reach expect of you today</small></h1>
<h2 id="attention">My attention<span class="count">{{ mine|length }} item{{ '' if mine|length == 1 else 's' }} the last run routed to you</span></h2>
{% if mine %}<table><thead><tr><th>Activity</th><th>Context</th><th>What to do</th><th>Status</th></tr></thead><tbody>
{% for m in mine %}<tr><td>{{ m.item }}</td><td>{{ m.name }}</td><td class="small muted">{{ m.what_to_do }}</td><td><span class="severity">{{ m.severity }}</span></td></tr>{% endfor %}
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


def _mine(who: str, held: set[str]) -> list[dict]:
    """What the last run routed to this person, plus the one thing the face itself can see: files placed and not yet run."""
    rows = [{"item": a["row"].get("item") or a["surface"], "name": a["name"], "what_to_do": a["what_to_do"], "severity": a["severity"]}
            for a in attention(q, who, HEALTH)]
    if "run.plan" in held:
        for f in ENTRIES.pending():
            rows.append({"item": f"{f.name} placed, not yet in the plan", "name": "landing", "what_to_do": "run the plan to take it in", "severity": "PENDING"})
    return rows


@plan.get("/")
def home():
    try:
        who = _who(); held = roles.actions_held(who)
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
<div class="wide"><table class="plan"><thead>
<tr><th rowspan="2" class="sticky">Material</th><th colspan="{{ d.periods|length }}" style="text-align:center">Periods</th>
{% for c in d.comps %}<th colspan="{{ 1 + (1 if c.py else 0) + (1 if c.ref else 0) }}" style="text-align:center;border-left:1px solid var(--rule)">FY{{ c.fy }}</th>{% endfor %}<th class="n" rowspan="2">Horizon</th></tr>
<tr>{% for pp in d.periods %}<th class="n {{ 'actual' if d.source_of[pp] == 'actual' }}" title="{{ pp }}{{ ' · actual' if d.source_of[pp] == 'actual' }}">{{ pp[2:4] }}·{{ pp[5:] }}</th>{% endfor %}
{% for c in d.comps %}<th class="n" style="border-left:1px solid var(--rule)">Total</th>{% if c.py %}<th class="n" title="same periods, prior fiscal year: shipments where closed, else this view">PY</th>{% endif %}{% if c.ref %}<th class="n" title="{{ d.ref_id }}">{{ d.ref_id }}</th>{% endif %}{% endfor %}</tr></thead><tbody>
{% for r in d.rows + [d.totals] %}<tr class="{{ 'total' if r.material == 'Total' }}"><td class="sticky">{{ r.material }}</td>{% for c in r.cells %}<td class="n {{ 'actual' if d.source_of[d.periods[loop.index0]] == 'actual' }}">{{ c|n }}</td>{% endfor %}
{% for b in r.blocks %}<td class="n" style="border-left:1px solid var(--rule);font-weight:500">{{ b.total|n }}</td>{% if d.comps[loop.index0].py %}<td class="n muted">{{ b.py|n }}</td>{% endif %}{% if d.comps[loop.index0].ref %}<td class="n muted">{{ b.ref|n }}</td>{% endif %}{% endfor %}<td class="n" style="font-weight:600">{{ r.total|n }}</td></tr>{% endfor %}
</tbody></table></div>
<p class="hint">Shaded periods are closed and read from shipments; the rest is the plan. PY is the same periods a year earlier — shipments where that year is closed, otherwise this view; {{ d.ref_id }} is the reference version where its horizon overlaps.</p>
<h2>Plan by layer and fiscal year</h2>
<table><thead><tr><th>Fiscal year</th><th class="n">1 Baseline</th><th class="n">2 Adjustment</th><th class="n">4 Distribution</th><th class="n">6 Promotions</th><th class="n">7 Innovation</th><th class="n">8 Exit</th><th class="n">Plan</th></tr></thead><tbody>
{% for r in layers %}<tr><td>FY{{ r.fiscal_year }}</td><td class="n">{{ r.l1|n }}</td><td class="n">{{ r.l2|n }}</td><td class="n">{{ r.l4|n }}</td><td class="n">{{ r.l6|n }}</td><td class="n">{{ r.l7|n }}</td><td class="n">{{ r.l8|n }}</td><td class="n">{{ r.cases|n }}</td></tr>{% endfor %}
</tbody></table>
<style>.wide{overflow-x:auto;margin:0 -1rem;padding:0 1rem}table.plan{width:max-content;min-width:100%;font-size:.82rem}table.plan th,table.plan td{padding:.35rem .5rem}
table.plan .actual{background:var(--soft)}table.plan .sticky{position:sticky;left:0;background:var(--panel);z-index:1}table.plan th.sticky{z-index:2;background:var(--soft)}</style>"""


@plan.get("/demand")
def demand():
    try:
        version = _version(); account = request.args.get("account") or None
        accounts = reads.accounts()
        extra = ('<label>account<select name="account" onchange="this.form.submit()"><option value="">all</option>'
                 + "".join(f'<option value="{a["account_code"]}" {"selected" if a["account_code"] == account else ""}>{a["account_code"]}</option>' for a in accounts) + "</select></label>")
        return _page(DEMAND, title="Demand plan", active="demand", width="100%", versions=reads.versions(), version=version, account=account,
                     d=reads.demand(version, account), layers=reads.by_layer(version, account), extra=extra)
    except Busy as e:
        return _busy("Demand plan", e)


# ---- entries ----
ENTRIES_PAGE = VERSION_PICKER + """
<h1>{{ title }}<small>{{ version }} · {{ lede }}</small></h1>
<table><thead><tr><th>Layer</th><th>Entry</th><th>By</th><th>On</th><th>Reason</th><th>Material</th><th>Customer</th><th>Window</th><th class="n">Value</th><th>Spread</th><th>Note</th><th></th></tr></thead><tbody>
{% for e in rows %}<tr class="{{ 'off' if e.withdrawn and e.withdrawn_by_owner }}">
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


@plan.route("/new", methods=["GET", "POST"])
def entry_new():
    try:
        who = _who()
        if request.method == "POST":
            f = request.form; layer = int(f["layer_no"]); version = f["version_id"]
            v = reads.version(version); hz = reads.horizon(version)
            reason = next((r for r in reads.reasons() if r["reason_code"] == f["reason_code"]), None)
            try:
                value = float(f["value"])
            except ValueError:
                value = None
            checks = [
                {"check": "version open", "ok": bool(v and v["status"] == "open"), "says": f"{version} is {v['status'] if v else 'unknown'}"},
                {"check": "who may enter", "ok": roles.may(who, f"layer.{layer}.enter"), "says": f"{who} holds layer {layer} enter" if roles.may(who, f"layer.{layer}.enter") else f"{who} does not hold layer {layer} enter"},
                {"check": "material scope resolves", "ok": reads.material_scope_resolves(f["scope_material"]), "says": f"{f['scope_material']} reaches leaf materials" if reads.material_scope_resolves(f["scope_material"]) else f"{f['scope_material']} is not a node of the product structure or a promo group"},
                {"check": "customer scope resolves", "ok": reads.customer_scope_resolves(f["scope_customer"]), "says": f"{f['scope_customer']} reaches ship-tos" if reads.customer_scope_resolves(f["scope_customer"]) else f"{f['scope_customer']} is not a node of the customer structure"},
                {"check": "window in horizon", "ok": f["period_from"] in hz and f["period_to"] in hz and f["period_from"] <= f["period_to"],
                 "says": f"{f['period_from']} – {f['period_to']} within {v['horizon_start']} – {v['horizon_end']}" if v and f["period_from"] in hz and f["period_to"] in hz and f["period_from"] <= f["period_to"] else "window outside the version's horizon or reversed"},
                {"check": "reason offered on layer", "ok": bool(reason and str(layer) in reason["layers"].split(",")), "flag": True,
                 "says": f"{f['reason_code']} is offered on layer {layer}" if reason and str(layer) in reason["layers"].split(",") else f"{f['reason_code']} is not a reason this layer usually gives — placed, flagged"},
                {"check": "value is a number", "ok": value is not None, "says": "a number" if value is not None else "not a number"},
                {"check": "vocabulary", "ok": f["value_kind"] in KINDS and f["spread_rule"] in SPREADS and f["effect_type"] in EFFECTS, "says": "kind, spread and effect are known"},
            ]
            placed = receipts.judge(checks)
            eid = f"LE-F-{dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
            if placed:
                ENTRIES.place([{"entry_id": eid, "action": "enter", "withdraws": "", "version_id": version, "layer_no": layer, "entered_by": who,
                                "entered_on": dt.date.today().isoformat(), "reason_code": f["reason_code"], "effect_type": f["effect_type"],
                                "scope_material": f["scope_material"], "scope_customer": f["scope_customer"], "period_from": f["period_from"],
                                "period_to": f["period_to"], "value_kind": f["value_kind"], "value": value, "spread_rule": f["spread_rule"], "note": f.get("note", "")}], who)
            session.last = receipts.write("enter", who, eid, checks, placed)
            session.say(f"{eid} placed on {version} layer {layer} — it is in the plan after the next run" if placed else "entry refused: " + "; ".join(c["says"] for c in checks if not c["ok"]), placed)
            return redirect(url_for("plan.entry_new"))
        enterable = set(roles.layers_enterable(who))
        return _page(NEW, title="New entry", active="new", versions=reads.open_versions(),
                     layers=[l for l in reads.layers() if l["layer_no"] in enterable], reasons=reads.reasons(), effects=EFFECTS, kinds=KINDS, spreads=SPREADS,
                     materials=reads.material_scopes(), customers=reads.customer_scopes(),
                     periods=reads.horizon(reads.default_version() or ""), last=session.last)
    except Busy as e:
        return _busy("New entry", e)


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


# ---- the rungs named but not yet built ----
RUNGS = {
    "standard": ("Standard by plant", "The standard cost of every material at every plant for the version's standard year, derived from the routes, the BOM and the cost inputs; a new plant through to a new standard and the transition."),
    "landed": ("Landed cost", "The distributor's standard: supplier price × FX + freight + duty by source; purchase price, FX and freight rate as the three variances."),
    "pnl": ("P&L plan", "Every line of the commercial P&L by cause — volume, price, mix, promotion, cost — at standard, with the planned variances beneath."),
    "balance": ("Balance sheet plan", "Every line rolled from opening actuals by one declared movement source; three identities run as a guard on every version."),
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


@plan.get("/terms")
def terms():
    try:
        cols = ["instrument_code", "account_code", "instrument_kind", "driver_basis", "rate", "flow_position", "conditionality", "settlement_timing", "scope_material", "valid_from", "valid_to", "note"]
        return _page("<h1>Terms<small>the instruments in force, by account</small></h1>" + _table(reads.terms(), cols), title="Terms", active="terms")
    except Busy as e:
        return _busy("Terms", e)


@plan.get("/versions")
def versions():
    try:
        cols = ["version_id", "version_kind", "cycle", "fiscal_year", "horizon_start", "horizon_end", "calendar_variant", "standard_version", "reference_version", "status", "owner", "named_on"]
        return _page("<h1>Versions<small>named, owned, frozen or open — the plan is a stack of entries on a version</small></h1>" + _table(reads.versions(), cols), title="Versions", active="versions")
    except Busy as e:
        return _busy("Versions", e)


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
