"""The opex schedule as a person types into it: entity × the plan's cost centre × account × period, each line a driver and
a rate, each month calculated as driver × rate until someone types it.

A person's unsaved acts — a month, a rate, a driver, a reset — sit in a working copy in this process (chassis.working),
never seen by anyone else, dropped by Discard, lost on a restart. Every view is the schedule computed by the run's own
function (`calc.schedule.compute`) over the inputs the run reads (`read_inputs`), the acts on file, the acts saved and
waiting for the run, and the person's own: so the page before a save and `plan.opex_schedule` after it agree. Save writes
one file and releases it by a run scoped to the schedule.

Registered on the plan's blueprint by `register(...)`, called once from `face/__main__.py`."""
from __future__ import annotations

import csv
import datetime as dt
import math
import threading
from collections import defaultdict
from dataclasses import dataclass, field

from chassis import CONFIG, receipts, working
from chassis.landing import LogLanding
from chassis.warehouse import Busy, q
from chassis.working import Copies
from flask import current_app, redirect, request, url_for

from calc.schedule import compute, lines_of, read_inputs, rules_from, total

from . import costs
from .words import said

COLUMNS = ["edit_id", "save_id", "version_id", "entity_code", "cost_centre_code", "account_code", "action", "period", "value", "driver",
           "calc_at_entry", "reason_code", "note", "entered_by", "entered_on"]
LANDING = LogLanding("plan", "reg_schedule_edit", COLUMNS)
LABOUR_MODEL = True                  # the labour lines are filled by the labour model (plan.labour_cost)
RUN = [["uv", "run", "python", "-m", "ingest.pipeline", "--only", "reg_schedule_edit"],
       ["uv", "run", "sqlmesh", "plan", "prod", "--restate-model", "plan.schedule_edit+", "--auto-apply", "--no-prompts"]]
COPIES = Copies()
_CACHE: dict = {}
_LOCK = threading.RLock()


# ---- what every view is computed from ----
def rules() -> dict:
    """The schedule's rows of the measure register, as the last run left them."""
    stamp = CONFIG.db.stat().st_mtime if CONFIG.db.exists() else 0
    with _LOCK:
        if _CACHE.get("_rules_stamp") != stamp:
            _CACHE.update(_rules_stamp=stamp, _rules=rules_from(q("select * from plan.ref_grid_measure order by grid, ord")))
        return _CACHE["_rules"]


def _verb(measure: str) -> str | None:
    """Who types a figure is the register's word: a month's amount under its verb, a line's rate — and so its driver —
    under the rate's. No verb: nobody types it."""
    return rules()[measure]["verb"]


def _stamp() -> tuple:
    return (CONFIG.db.stat().st_mtime if CONFIG.db.exists() else 0, tuple(p.name for p in LANDING.pending()))


def _num(x):
    """A typed amount or rate: thousands separators allowed (the grid shows months that way); not-a-number and infinity
    are not numbers."""
    if x is None or (isinstance(x, str) and not x.strip()):
        return None
    try:
        v = float(str(x).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


MAX_MONTH, MAX_RATE = 1_000_000_000, 1_000_000           # one month of one line; a line's rate


def _acts_from(rows: list[dict]) -> list[dict]:
    return [{**r, "period": r.get("period") or None, "value": _num(r.get("value")), "calc_at_entry": _num(r.get("calc_at_entry")),
             "driver": r.get("driver") or None, "entered_on": str(r.get("entered_on") or "")} for r in rows]


def base(version: str, fresh: bool = False) -> dict:
    """The schedule as the last run left it, with the saves waiting for the run: inputs, rules, acts on file, cells.
    Shared, read once per run; never written."""
    stamp = _stamp()
    with _LOCK:
        hit = _CACHE.get(version)
        if hit and hit["stamp"] == stamp and not fresh:
            return hit
        inp = read_inputs(lambda sql: q(sql), lambda n: n, version, labour=LABOUR_MODEL)
        acts = _acts_from(q("select * from plan.schedule_edit where version_id = ? order by entered_on, edit_id", version))
        for path in LANDING.pending():
            with open(path, newline="") as fh:
                acts += _acts_from([r for r in csv.DictReader(fh) if r.get("version_id") == version])
        acts.sort(key=lambda a: (a["entered_on"], a["edit_id"]))
        _CACHE[version] = {"stamp": stamp, "inp": inp, "rules": rules(), "acts": acts, "cells": compute(inp, acts, rules())}
        return _CACHE[version]


@dataclass
class WorkingCopy:
    version: str
    acts: list[dict] = field(default_factory=list)
    n: int = 0


def working_copy(who: str, version: str, create: bool = False) -> WorkingCopy | None:
    wc = COPIES.get(who, ("schedule", version))
    if wc is None and create:
        wc = COPIES.open(who, ("schedule", version), lambda: WorkingCopy(version))
    return wc


def cells_for(who: str, version: str) -> tuple[dict, dict, WorkingCopy | None]:
    """(the person's view, the schedule as saved, their working copy)."""
    b = base(version)
    wc = working_copy(who, version)
    if not wc or not wc.acts:
        return b["cells"], b["cells"], wc
    return compute(b["inp"], b["acts"] + wc.acts, b["rules"]), b["cells"], wc


def act(wc: WorkingCopy, who: str, line: tuple, action: str, period: str | None = None, value: float | None = None,
        driver: str | None = None, calc: float | None = None) -> None:
    wc.n += 1
    wc.acts.append({"edit_id": f"W-{wc.n:04d}", "entity_code": line[0], "cost_centre_code": line[1], "account_code": line[2], "action": action,
                    "period": period, "value": value, "driver": driver, "calc_at_entry": calc, "entered_by": who,
                    "entered_on": dt.datetime.now().isoformat(timespec="microseconds")})


def rows_for_save(wc: WorkingCopy, save_id: str, stamp: dt.datetime, who: str, reason: str, note: str) -> list[dict]:
    on = stamp.isoformat(timespec="microseconds")
    return [{"edit_id": f"{save_id.replace('SS-', 'SE-')}-{i:03d}", "save_id": save_id, "version_id": wc.version, "entity_code": a["entity_code"],
             "cost_centre_code": a["cost_centre_code"], "account_code": a["account_code"], "action": a["action"], "period": a["period"] or "",
             "value": "" if a["value"] is None else repr(a["value"]), "driver": a["driver"] or "",
             "calc_at_entry": "" if a["calc_at_entry"] is None else repr(a["calc_at_entry"]), "reason_code": reason, "note": note,
             "entered_by": who, "entered_on": on} for i, a in enumerate(wc.acts, start=1)]


# ---- the page ----
def line_id(line: tuple) -> str:
    return "~".join(line)


def line_of(s: str) -> tuple | None:
    parts = (s or "").split("~")
    return tuple(parts) if len(parts) == 3 else None


MACROS = """{% macro money(x) %}{{ '' if x is none else '{:,.0f}'.format(x) }}{% endmacro %}
{% macro rate_shown(x, d) %}{{ '' if x is none else ('{:,.0f}'.format(x) if d == 'none' else ('{:.4f}'.format(x) if d == 'last_year' else '{:,.4f}'.format(x))) }}{% endmacro %}
{% macro sch_status(s) %}<div id="sch-status" class="hint">{% if s.say %}<b class="no">{{ s.say }}</b> · {% endif %}{% if s.unsaved %}<b class="state unsaved">{{ s.unsaved }} change{{ '' if s.unsaved == 1 else 's' }} typed and not saved</b> — Save to keep them, Discard to drop them{% elif s.editable %}Type a month, or a line's rate; Enter or Tab recalculates at once.{% endif %}</div>{% endmacro %}
{% macro sch_row(s, l) %}<tr id="sch-l-{{ l.id }}" class="line">
<td class="sticky"><span>{{ l.account_code }} {{ l.account_name }}</span> <span class="small muted">{{ l.entity_code }}</span>{% if l.n_typed and l.may_month %} <a class="small" tabindex="-1" href="{{ url_for('plan.schedule_reset', line=l.id, **s.keep) }}">reset…</a>{% endif %}</td>
<td class="small">{% if l.driver == 'labour_model' %}the labour model{% elif s.may_method and s.open %}<select name="d|{{ l.id }}" onchange="this.form.submit()">{% for d in s.drivers %}<option value="{{ d.driver }}" {{ 'selected' if d.driver == l.driver }}>{{ d.driver_label }}</option>{% endfor %}</select>{% else %}{{ s.driver_label.get(l.driver, l.driver) }}{% endif %}</td>
<td class="n {{ 'typed' if l.rate_typed }} {{ 'unsaved' if l.rate_unsaved }}">{% if l.driver == 'labour_model' %}<span class="muted">—</span>{% elif s.may_method and s.open %}<input class="cell" name="r|{{ l.id }}" value="{{ rate_shown(l.rate, l.driver) if l.rate_typed else '' }}" placeholder="{{ rate_shown(l.rate_calc, l.driver) }}" data-live='{"cell": "r|{{ l.id }}"}' inputmode="decimal">{% else %}{{ rate_shown(l.rate, l.driver) }}{% endif %}<span class="src">{{ 'from the headcount' if l.driver == 'labour_model' else ('calculated ' ~ rate_shown(l.rate_calc, l.driver) if l.rate_calc is not none else 'no history') }}</span></td>
{% for p in s.closed %}<td class="n closed">{{ money(l.actual.get(p)) }}</td>{% endfor %}
{% for p in s.planned %}{% set c = l.cells.get(p) %}<td class="n {{ c.state if c }} {{ 'unsaved' if c and c.unsaved }}">{% if c %}{% if l.may_month and s.open and c.state != 'model' %}<input class="cell" name="m|{{ l.id }}|{{ p }}" value="{{ money(c.amount) }}" data-live='{"cell": "m|{{ l.id }}|{{ p }}"}' inputmode="decimal">{% else %}{{ money(c.amount) }}{% endif %}{% if c.state == 'typed' %}<span class="src">calc {{ money(c.amount_calc) }}{% if c.amount_calc is not none %} · {{ '{:+,.0f}'.format(c.amount - c.amount_calc) }}{% endif %}{% if c.moved %} <b title="the calculated amount has moved since this month was typed (it was {{ money(c.typed_calc) }})">◆</b>{% endif %}</span>{% endif %}{% endif %}</td>{% endfor %}
<td class="n tot">{{ money(l.fy) }}</td></tr>{% endmacro %}
{% macro sch_group(s, g) %}<tr id="sch-g-{{ g.code }}" class="grp"><td class="sticky"><b>{{ g.name }}</b> <span class="small muted">{{ g.code }}</span></td><td></td><td></td>
{% for p in s.closed %}<td class="n closed"><b>{{ money(g.by.get(p)) }}</b></td>{% endfor %}{% for p in s.planned %}<td class="n"><b>{{ money(g.by.get(p)) }}</b></td>{% endfor %}<td class="n tot"><b>{{ money(g.fy) }}</b></td></tr>{% endmacro %}
{% macro sch_total(s) %}<tr id="sch-t" class="total"><td class="sticky">Total shown</td><td></td><td></td>{% for p in s.closed %}<td class="n closed">{{ money(s.tot.get(p)) }}</td>{% endfor %}{% for p in s.planned %}<td class="n">{{ money(s.tot.get(p)) }}</td>{% endfor %}<td class="n tot">{{ money(s.tot_fy) }}</td></tr>{% endmacro %}"""

PAGE = MACROS + """<h1>Opex schedule<small>FY{{ fy }} · {{ version }} · {{ s.where }} · every line a driver and a rate; every month driver × rate until it is typed</small></h1>
<form class="toolbar" method="get">{{ context_fields() }}<label>entity<select name="entity" onchange="this.form.submit()"><option value="">both</option>{% for e in s.entities %}<option value="{{ e.entity_code }}" {{ 'selected' if e.entity_code == s.entity }}>{{ e.entity_name }}</option>{% endfor %}</select></label>
<label>cost centre<select name="cc" onchange="this.form.submit()">{% for c in s.centres %}<option value="{{ c.code }}" {{ 'selected' if c.code == s.cc }}>{{ '· ' * c.depth }}{{ c.name }}</option>{% endfor %}</select></label></form>
<p class="hint">{{ entity_note }}</p>
{% if s.withheld %}<p class="hint">The labour lines of {{ s.withheld|length }} cost centres planned by name are individual pay, read by {{ s.pay_holders|join(', ') or 'nobody yet' }}: they are left out here and out of every total shown.</p>{% endif %}
{% if not s.open %}<p class="hint">{{ version }} is {{ s.status }}: the schedule is kept on the open latest view, for the twelve periods after the last closed one.</p>{% endif %}
<div class="schlive"{% if s.editable %} data-live-post="{{ url_for('plan.schedule_cell') }}" data-live-context='{{ s.live_context|tojson }}'{% endif %}>
{{ sch_status(s) }}
<form method="post" action="{{ url_for('plan.schedule_cell') }}" id="sch-grid">{% for k, v in s.keep.items() %}<input type="hidden" name="{{ k }}" value="{{ v }}">{% endfor %}
<div class="schwrap"><table class="sch"><thead><tr><th class="sticky">Line</th><th>Driver</th><th class="n">Rate</th>{% for p in s.closed %}<th class="n closed" title="actual">{{ p[2:4] }}·{{ p[5:] }}</th>{% endfor %}{% for p in s.planned %}<th class="n">{{ p[2:4] }}·{{ p[5:] }}</th>{% endfor %}<th class="n">FY{{ fy }}</th></tr></thead>
{% for g in s.groups %}<tbody>{{ sch_group(s, g) }}{% for l in g.lines %}{{ sch_row(s, l) }}{% endfor %}</tbody>{% else %}<tbody><tr><td colspan="{{ 4 + s.closed|length + s.planned|length }}" class="muted">No line in this selection.</td></tr></tbody>{% endfor %}
<tbody>{{ sch_total(s) }}</tbody></table></div>
{% if s.editable %}<noscript><p class="hint"><button class="act">Recalculate</button> this page's script is off: every changed figure is applied at once.</p></noscript>{% endif %}</form>
<p class="hint">Shaded periods are closed: the ledgers' actuals through the mapping. The rest is the plan, for the twelve periods after the last closed one{% if s.beyond %}; FY{{ fy }}'s later periods are past the schedule's horizon{% endif %}. Under each rate, the rate calculated from the last twelve closed periods ({{ s.window[0] }}–{{ s.window[-1] }}); a rate typed over it is boxed. A boxed month was typed: it holds, the calculated amount beneath it with the difference; ◆ marks one whose calculated amount has moved since it was typed. Hatched: typed and not yet saved.
{% for r in s.measures %} <b>{{ r.label }}</b>{% if r.formula_says %} = {{ r.formula_says }}{% endif %}.{% endfor %} <a href="{{ url_for('plan.rules') }}#schedule">How each figure is calculated</a></p>
{% if s.editable %}<form method="post" action="{{ url_for('plan.schedule_save') }}" class="form-row" id="sch-save">{% for k, v in s.keep.items() %}<input type="hidden" name="{{ k }}" value="{{ v }}">{% endfor %}
<label class="small">reason <select name="reason_code">{% for r in s.reasons %}<option value="{{ r.reason_code }}">{{ r.description }}</option>{% endfor %}</select></label>
<label class="small grow">note <input name="note" placeholder="what the driver does not know"></label>
<button class="primary" onclick="this.textContent='Saving…'">Save</button><button class="act" formaction="{{ url_for('plan.schedule_discard') }}">Discard</button>
<button class="act" formaction="{{ url_for('plan.schedule_recalculate') }}">Recalculate</button>
<span class="hint">one reason for everything not yet saved · Save writes it to {{ version }} and carries it into the plan · Recalculate sets every calculated month to driver × rate again and leaves typed months alone</span></form>
{% elif s.open %}<p class="hint">Months are typed by the cost centre's budget holder ({{ s.month_holders|join(', ') }}); drivers and rates by {{ s.method_holders|join(', ') }}.</p>{% endif %}
</div>
{% if last and last.act and last.act.startswith('schedule') %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else ('!' if c.flag else '✕') }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}
<style>.schwrap{overflow-x:auto;margin-bottom:.6rem}table.sch{font-size:.8rem;width:max-content;min-width:100%}table.sch td.n{vertical-align:top;white-space:nowrap}
table.sch .sticky{position:sticky;left:0;background:var(--panel);z-index:1;min-width:16rem}table.sch tr.grp td{background:var(--soft);border-top:1px solid var(--rule)}table.sch tr.grp td.sticky{background:var(--soft)}
table.sch .src{display:block;font-size:.7rem;color:var(--muted)}table.sch td.typed{box-shadow:inset 0 0 0 1px var(--ink)}table.sch td.closed,table.sch th.closed{color:var(--muted);background:var(--soft)}
table.sch td.unsaved{background:repeating-linear-gradient(135deg,transparent 0 5px,color-mix(in srgb,var(--muted) 14%,transparent) 5px 6px)}.state.unsaved{background:repeating-linear-gradient(135deg,transparent 0 5px,color-mix(in srgb,var(--muted) 18%,transparent) 5px 6px)}
table.sch input.cell{width:5.6rem;text-align:right;font-size:.8rem;padding:.12rem .3rem}table.sch td.tot{font-weight:600}.schlive.live-busy table.sch{cursor:progress}
.form-row{display:flex;flex-wrap:wrap;gap:.8rem;align-items:end;margin:.6rem 0}.form-row .grow{flex:1;display:flex;flex-direction:column}.form-row label{display:flex;flex-direction:column;gap:.2rem}</style>
{% if s.editable %}{{ live_script }}{% endif %}"""

RESET = """<h1>Reset to base<small>{{ l.account_code }} {{ l.account_name }} · {{ l.cc_name }} · {{ l.entity_code }} · {{ version }}</small></h1>
{% if not typed %}<p class="lede">Nothing typed on this line: every month is already driver × rate.</p>{% else %}
<form method="post" action="{{ url_for('plan.schedule_reset_do') }}">{% for k, v in keep.items() %}<input type="hidden" name="{{ k }}" value="{{ v }}">{% endfor %}<input type="hidden" name="line" value="{{ l.id }}">
<p class="lede">This removes <b>{{ typed|length }} typed figure{{ '' if typed|length == 1 else 's' }}</b> from the line — untick any to keep — and returns each to driver × rate. Nothing is removed until you confirm; the change is in your unsaved work until you Save.</p>
<table><thead><tr><th></th><th>Period</th><th class="n">Typed</th><th class="n">Calculated</th><th class="n">Difference</th></tr></thead><tbody>
{% for c in typed %}<tr><td><input type="checkbox" name="period" value="{{ c.period }}" checked></td><td>{{ c.period }}</td><td class="n">{{ '{:,.0f}'.format(c.amount) }}</td><td class="n">{{ '' if c.amount_calc is none else '{:,.0f}'.format(c.amount_calc) }}</td>
<td class="n">{{ '' if c.amount_calc is none else '{:+,.0f}'.format(c.amount - c.amount_calc) }}</td></tr>{% endfor %}</tbody></table>
<button class="primary">Remove the ticked typed figures</button> <a href="{{ back }}">keep them all</a></form>{% endif %}"""


def _macros():
    env = current_app.jinja_env
    if _CACHE.get("_env") is not env:
        _CACHE.update(_env=env, _module=env.from_string(MACROS).module)
    return _CACHE["_module"]


def _scope(who: str) -> set | None:
    """The plan's cost centres this person's organisation assignments reach; None when they have none (they read all)."""
    nodes = {r["node"] for r in q("select distinct node from dims.effective_entitlements where principal = ? and scope_dimension = 'organisation'", who or "")}
    return nodes or None


def _may_month(roles, who: str, cc: str) -> bool:
    v = _verb("amount")
    return bool(v) and roles.may(who, v, cc, dimension="organisation")


def view(who: str, version: str, fy: int, page: dict, roles, say: str | None = None) -> dict:
    from . import reads
    v = reads.version(version) or {}
    b = base(version)
    cells, saved, wc = cells_for(who, version)
    rules = b["rules"]
    inp = b["inp"]
    tree = costs.planning_cost_centres()
    mine = _scope(who)
    under: dict[str, set] = defaultdict(set)
    parent = {c["code"]: c["parent"] for c in tree}
    for c in tree:
        n = c["code"]
        while n:
            under[n].add(c["code"]); n = parent.get(n)
    visible = set(parent) if mine is None else set().union(*(under[n] for n in mine if n in under))
    roots = [c for c in tree if c["code"] in visible and (parent.get(c["code"]) not in visible)]
    cc = page.get("cc") if page.get("cc") in visible else (roots[0]["code"] if roots else "")
    entity = page.get("entity") or ""
    shown = under.get(cc, set()) & visible
    may_method = bool(_verb("rate")) and roles.may(who, _verb("rate"))
    accounts = {a["account_code"]: a["account_name"] for a in q("select account_code, account_name from dims.dim_gl_account")}
    closed = [r["period"] for r in q("select period from dims.dim_period where fiscal_year = ? and period_state = 'CLOSED' order by period", fy)]
    planned = [p for p in inp.periods if inp.fy_of.get(p) == fy]
    all_fy = [r["period"] for r in q("select period from dims.dim_period where fiscal_year = ? order by period", fy)]
    actual: dict = defaultdict(dict)
    if closed:
        for r in q(f"""select entity_code, cost_centre_code, account_code, period, sum(amount) a from plan.cost_actual where state = 'mapped'
                       and period in ({','.join('?' * len(closed))}) group by all""", *closed):
            actual[(r["entity_code"], r["cost_centre_code"], r["account_code"])][r["period"]] = r["a"]
    by_line = lines_of(cells)
    month_verb, may_cc = _verb("amount"), {}
    def may_at(cc_: str) -> bool:                  # one question per cost centre, not per line
        if cc_ not in may_cc:
            may_cc[cc_] = bool(month_verb) and roles.may(who, month_verb, cc_, dimension="organisation")
        return may_cc[cc_]
    order = {c["code"]: i for i, c in enumerate(tree)}
    groups: dict[str, dict] = {}
    unsaved = len(wc.acts) if wc else 0
    _, withheld = costs.pay_withheld(roles, who)
    role_ccs = {r["cost_centre_code"] for r in q("select cost_centre_code from dims.dim_cost_centre where labour_model = 'role'")} if withheld else set()
    labour_accts = {r["account_code"] for r in q("select account_code from dims.dim_gl_account where is_labour")}
    for line in sorted(set(by_line) | set(actual), key=lambda l: (order.get(l[1], 999), l[2], l[0])):
        if line[1] not in shown or (entity and line[0] != entity):
            continue
        if withheld and line[2] in labour_accts and line[1] not in role_ccs:
            continue                      # individual pay: read under read.pay only, and left out of every total
        cs = {c["period"]: c for c in by_line.get(line, [])}
        for p, c in cs.items():
            s0 = saved.get((*line, p)) or {}
            c["unsaved"] = bool(wc and wc.acts) and (s0.get("amount") != c["amount"] or s0.get("state") != c["state"])
        first = next(iter(cs.values()), None)
        s0 = saved.get((*line, planned[0] if planned else "")) or {}
        fy_amt = sum(actual[line].get(p) or 0 for p in closed) + sum((cs[p]["amount"] or 0) for p in planned if p in cs)
        l = {"id": line_id(line), "entity_code": line[0], "cost_centre_code": line[1], "account_code": line[2], "account_name": accounts.get(line[2], ""),
             "driver": first["driver"] if first else "last_year", "rate": first["rate"] if first else None, "rate_calc": first["rate_calc"] if first else None,
             "rate_typed": bool(first and first["rate_typed"]), "rate_unsaved": bool(first and s0 and (s0.get("rate") != first["rate"] or s0.get("driver") != first["driver"])),
             "cells": {p: cs[p] for p in planned if p in cs}, "actual": actual[line], "fy": fy_amt,
             "n_typed": sum(1 for c in cs.values() if c["state"] == "typed"), "may_month": may_at(line[1]) and v.get("status") == "open"}
        g = groups.setdefault(line[1], {"code": line[1], "name": next((c["name"] for c in tree if c["code"] == line[1]), line[1]), "lines": [], "by": defaultdict(float), "fy": 0.0})
        g["lines"].append(l)
        for p in closed:
            g["by"][p] += actual[line].get(p) or 0
        for p in planned:
            if p in cs:
                g["by"][p] += cs[p]["amount"] or 0
        g["fy"] += fy_amt
    tot = defaultdict(float)
    for g in groups.values():
        for p, x in g["by"].items():
            tot[p] += x
    ents = costs.entities()
    keep = {"version": version, "fy": fy, "cc": cc, "entity": entity}
    from . import reads as R
    drivers = q("select * from dims.ref_cost_driver order by ord")
    open_ = v.get("status") == "open" and bool(inp.periods)
    editable = open_ and (may_method or any(l["may_month"] for g in groups.values() for l in g["lines"]))
    return {"entities": ents, "entity": entity, "cc": cc, "centres": [c for c in tree if c["code"] in visible],
            "where": " · ".join(x for x in [next((c["name"] for c in tree if c["code"] == cc), ""), next((e["entity_name"] for e in ents if e["entity_code"] == entity), "both entities")] if x),
            "open": open_, "status": v.get("status"), "closed": closed, "planned": planned, "beyond": bool(planned) and len(closed) + len(planned) < len(all_fy),
            "window": inp.window, "groups": list(groups.values()), "tot": tot, "tot_fy": sum(g["fy"] for g in groups.values()),
            "may_method": may_method, "editable": editable, "unsaved": unsaved, "say": say, "keep": keep, "live_context": {"page": keep},
            "drivers": drivers, "driver_label": {d["driver"]: d["driver_label"] for d in drivers},
            "measures": [r for r in rules.values()], "reasons": q("select * from plan.ref_schedule_reason"),
            "withheld": withheld, "pay_holders": R.holders(costs.PAY_VERB), "pay_verb": costs.PAY_VERB,
            "month_holders": R.holders(_verb("amount")) if _verb("amount") else [], "method_holders": R.holders(_verb("rate")) if _verb("rate") else []}


def parts(s: dict) -> dict[str, str]:
    M = _macros()
    out = {"sch-status": str(M.sch_status(s))}
    for g in s["groups"]:
        out[f"sch-g-{g['code']}"] = str(M.sch_group(s, g))
        for l in g["lines"]:
            out[f"sch-l-{l['id']}"] = str(M.sch_row(s, l))
    out["sch-t"] = str(M.sch_total(s))
    return out


def register(bp, page, who_fn, ctx_fn, busy, session, roles, run_plan, scoped: dict) -> None:
    scoped["schedule"] = {"commands": RUN, "pending": LANDING.pending, "what": "opex schedule",
                          "says": "run completed — the opex schedule reads what was saved"}

    def _page_args(src) -> dict:
        c = ctx_fn()
        version = src.get("version") or c.get("version")
        from . import reads
        v = reads.version(version) or {}
        fy = int(src.get("fy") or c.get("fy") or v.get("fiscal_year") or 0)
        return {"version": version, "fy": fy, "cc": src.get("cc") or "", "entity": src.get("entity") or ""}

    def _back(pg: dict) -> str:
        return url_for("plan.schedule", **pg)

    def _refuse(who: str, version: str, line: tuple | None, kind: str, period: str | None, raw) -> str | None:
        from . import reads
        v = reads.version(version) or {}
        if v.get("status") != "open":
            return f"{version} is {v.get('status', 'unknown')} — nothing is typed on it"
        if not line:
            return "not a line of the schedule"
        b = base(version)
        if kind == "m":
            if period not in b["inp"].periods:
                return f"{period} is not a period the schedule plans"
            if not _may_month(roles, who, line[1]):
                return f"{who} does not hold {said(_verb('amount'))} at {line[1]}"
            if line in b["inp"].labour_lines:
                return "a labour line is filled by the labour model, from the headcount and the agreement — not typed here"
            if _num(raw) is None:
                return f"{raw!r} is not an amount"
            if abs(_num(raw)) > MAX_MONTH:
                return f"{raw} is beyond what one month of one line can be — at most {MAX_MONTH:,.0f}"
        else:
            if not _verb("rate") or not roles.may(who, _verb("rate")):
                return f"{who} does not hold {said(_verb('rate'))} — a line's driver and rate are Commercial finance's"
            if line in b["inp"].labour_lines:
                return "a labour line takes its amount from the labour model — it has no driver or rate to type"
            if kind == "r" and str(raw).strip() and _num(raw) is None:
                return f"{raw!r} is not a rate"
            if kind == "r" and _num(raw) is not None and abs(_num(raw)) > MAX_RATE:
                return f"{raw} is beyond what a rate can be — at most {MAX_RATE:,.0f}"
            if kind == "d" and raw not in [d["driver"] for d in q("select driver from dims.ref_cost_driver")]:
                return f"{raw!r} is not a driver"
        return None

    def _apply(who: str, version: str, field_: str, raw) -> tuple[bool, str | None]:
        """One field typed: m|line|period, r|line or d|line. Returns (changed, refusal)."""
        bits = field_.split("|")
        kind, line = bits[0], line_of(bits[1] if len(bits) > 1 else "")
        period = bits[2] if kind == "m" and len(bits) > 2 else None
        why = _refuse(who, version, line, kind, period, raw)
        if why:
            return False, why
        cells, _, wc = cells_for(who, version)
        if kind == "m":
            c = cells.get((*line, period)) or {}
            x = _num(raw)
            if c and c.get("amount") is not None and abs(c["amount"] - x) < 0.005:
                return False, None
            wc = working_copy(who, version, create=True)
            act(wc, who, line, "month", period, x, calc=c.get("amount_calc"))
        elif kind == "r":
            first = next((c for k, c in cells.items() if k[:3] == line), {})
            x = _num(raw)
            if (x is None and not first.get("rate_typed")) or (x is not None and first.get("rate_typed") and abs((first.get("rate") or 0) - x) < 1e-9):
                return False, None
            wc = working_copy(who, version, create=True)
            act(wc, who, line, "rate", value=x)
        elif kind == "d":
            first = next((c for k, c in cells.items() if k[:3] == line), {})
            if first.get("driver") == raw:
                return False, None
            wc = working_copy(who, version, create=True)
            act(wc, who, line, "driver", driver=raw)
        return True, None

    @bp.get("/schedule")
    def schedule():
        try:
            who = who_fn(); pg = _page_args(request.args)
            s = view(who, pg["version"], pg["fy"], pg, roles)
            return page(PAGE, title="Opex schedule", active="sch_schedule", width="none", version=pg["version"], fy=pg["fy"], s=s,
                        last=session.last, receipt_acts=("schedule",), live_script=working.script(), entity_note=costs.ENTITY_NOTE)
        except Busy as e:
            return busy("Opex schedule", e)

    @bp.post("/schedule/cell")
    def schedule_cell():
        """A figure typed (the page's script posts each as entered) into the person's working copy; the reply is the parts
        of the view it changed. Without the script, the grid posts here as a form: every changed field applied in order."""
        live = working.is_live()
        data = (request.get_json(silent=True) or {}) if live else request.form
        who = who_fn(); pg = _page_args((data.get("page") or {}) if live else data)
        version, fy = pg["version"], pg["fy"]
        if live:
            fields = [(str(data.get("cell") or ""), data.get("value"))]
        else:
            cells, _, _ = cells_for(who, version)
            fields = []
            for k, val in data.items():
                if not k[:2] in ("m|", "r|", "d|"):
                    continue
                fields.append((k, val))
        with COPIES.lock(who):
            before = parts(view(who, version, fy, pg, roles)) if live else {}
            said, n = [], 0
            for f, raw in fields:
                if not live and f.startswith("m|"):          # a plain post sends every month: only those that differ
                    line = line_of(f.split("|")[1]); c = cells.get((*line, f.split("|")[2])) if line else None
                    if c is None or _num(raw) is None or abs((c.get("amount") or 0) - _num(raw)) < 0.5:
                        continue
                if not live and f.startswith("r|") and not str(raw).strip():
                    line = line_of(f.split("|")[1]); first = next((c for k, c in cells.items() if line and k[:3] == line), {})
                    if not first.get("rate_typed"):
                        continue
                changed, why = _apply(who, version, f, raw)
                n += changed
                if why:
                    said.append(why)
            if live:
                after = parts(view(who, version, fy, pg, roles, say="; ".join(said) or None))
                force = ["sch-status"] + ([f"sch-l-{fields[0][0].split('|')[1]}"] if said and "|" in fields[0][0] else [])
                return working.reply(before, after, always=tuple(force))
        session.say("; ".join(said) if said else (f"{n} change{'s' if n != 1 else ''} applied — not yet saved" if n else "nothing changed"), not said)
        return redirect(_back(pg))

    @bp.post("/schedule/discard")
    def schedule_discard():
        who = who_fn(); pg = _page_args(request.form)
        with COPIES.lock(who):                    # a month still being applied lands before the copy is dropped
            wc = working_copy(who, pg["version"]); n = len(wc.acts) if wc else 0
            COPIES.drop(who, ("schedule", pg["version"]))
        session.say(f"{n} unsaved change{'s' if n != 1 else ''} discarded" if n else "nothing unsaved to discard", True)
        return redirect(_back(pg))

    @bp.post("/schedule/recalculate")
    def schedule_recalculate():
        """Every calculated month set to driver × rate again, from the drivers as the last run left them; typed months are
        left alone and counted, with those whose calculated amount has moved since they were typed."""
        who = who_fn(); pg = _page_args(request.form)
        base(pg["version"], fresh=True)
        cells, _, _ = cells_for(who, pg["version"])
        calc = sum(1 for c in cells.values() if c["state"] == "calculated")
        typed = [c for c in cells.values() if c["state"] == "typed"]
        moved = sum(1 for c in typed if c["moved"])
        session.say(f"recalculated: {calc} calculated months are driver × rate from the last run's drivers; {len(typed)} typed month"
                    f"{'' if len(typed) == 1 else 's'} left as typed, {moved} of them marked ◆ — their calculated amount has moved since they were typed. "
                    "Nothing typed was removed: Reset to base does that, line by line.", True)
        return redirect(_back(pg))

    @bp.get("/schedule/reset")
    def schedule_reset():
        who = who_fn(); pg = _page_args(request.args)
        line = line_of(request.args.get("line", ""))
        cells, _, _ = cells_for(who, pg["version"])
        typed = sorted((c for k, c in cells.items() if line and k[:3] == line and c["state"] == "typed"), key=lambda c: c["period"])
        acct = (q("select account_name from dims.dim_gl_account where account_code = ?", line[2]) or [{}])[0].get("account_name", "") if line else ""
        ccn = (q("select cost_centre_name from plan.planning_cost_centre where cost_centre_code = ?", line[1]) or [{}])[0].get("cost_centre_name", "") if line else ""
        l = {"id": line_id(line) if line else "", "account_code": line[2] if line else "", "account_name": acct, "cc_name": ccn, "entity_code": line[0] if line else ""}
        return page(RESET, title="Reset to base", active="sch_schedule", l=l, typed=typed, keep=pg, back=_back(pg), version=pg["version"])

    @bp.post("/schedule/reset")
    def schedule_reset_do():
        """The ticked typed months of a line back to calculated, in the person's working copy — confirmed on the page that
        named how many it removes."""
        f = request.form; who = who_fn(); pg = _page_args(f)
        line = line_of(f.get("line", "")); periods = f.getlist("period")
        why = _refuse(who, pg["version"], line, "m", (base(pg["version"])["inp"].periods or [None])[0], "0")
        if why is None and not periods:
            why = "nothing ticked — every typed month kept"
        if why:
            session.say(why, False)
            return redirect(_back(pg))
        with COPIES.lock(who):
            wc = working_copy(who, pg["version"], create=True)
            for p in periods:
                act(wc, who, line, "reset", p)
        session.say(f"{len(periods)} typed month{'s' if len(periods) != 1 else ''} returned to driver × rate — not yet saved", True)
        return redirect(_back(pg))

    @bp.post("/schedule/save")
    def schedule_save():
        """One save: every act in the person's working copy under one reason, as one file — then released by the run
        scoped to the schedule (the whole run when another file is waiting)."""
        from . import reads
        f = request.form; who = who_fn(); pg = _page_args(f); version = pg["version"]
        v = reads.version(version) or {}
        reason, note = f.get("reason_code", ""), (f.get("note") or "").strip()
        reasons = {r["reason_code"]: r for r in q("select * from plan.ref_schedule_reason")}
        with COPIES.lock(who):                    # a month still being applied lands before the copy is read
            wc = working_copy(who, version); n = len(wc.acts) if wc else 0
            verbs = [x for x in (_verb("amount"), _verb("rate")) if x]
            may = any(roles.may(who, x) for x in verbs)
            checks = [
                {"check": "who may type", "ok": may, "says": f"{who} holds {said(next(x for x in verbs if roles.may(who, x)))}" if may else f"{who} holds none of {', '.join(said(x) for x in verbs) or 'the verbs that type the schedule'}"},
                {"check": "version open", "ok": v.get("status") == "open", "says": f"{version} is {v.get('status', 'unknown')}"},
                {"check": "something to save", "ok": n > 0, "says": f"{n} change{'s' if n != 1 else ''} typed and not saved" if n else "nothing typed since the last save"},
                {"check": "a reason we know", "ok": reason in reasons, "says": reasons[reason]["description"] if reason in reasons else f"{reason or 'no reason'} is not a schedule reason"},
                {"check": "a note where the reason needs one", "ok": bool(note) or not (reasons.get(reason) or {}).get("note_required"),
                 "says": note or ("this reason needs a note" if (reasons.get(reason) or {}).get("note_required") else "not needed for this reason")},
            ]
            placed = receipts.judge(checks)
            stamp = dt.datetime.now(); save_id = f"SS-{stamp.strftime('%Y%m%d-%H%M%S-%f')}"
            if placed:
                LANDING.place(rows_for_save(wc, save_id, stamp, who, reason, note), who)
                COPIES.drop(who, ("schedule", version))
        session.last = receipts.write("schedule.save", who, save_id, checks, placed)
        if not placed:
            session.say("save refused: " + "; ".join(c["says"] for c in checks if not c["ok"]), False)
            return redirect(_back(pg))
        if run_plan(who, "schedule"):
            session.say(f"{save_id} saved — {n} change{'s' if n != 1 else ''} written to {version} and carried into the plan", True)
            return redirect(_back(pg))
        return redirect(url_for("plan.run"))
