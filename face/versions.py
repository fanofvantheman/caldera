"""Versions, and closing and reopening one (DEC-20261113-05, first part): a version is open or closed, and the state is
read from a register of acts (plan.version_act → plan.version_state), never edited in place. Close and reopen are acts by
the holders of `version.freeze`, each with a receipt; reopening asks for a reason; a version that is the declared reference
of another is not reopened — a changed reference is a new version, or every gap read against it would move without
anyone having decided it. A closed version takes no entry and no change of any register; it stays readable, and every
calculation keeps reading it.

An act is a file in the landing, released at once by a run scoped to the version's state (the whole run when another file
is waiting). Any state per step inside a version is not built.

Naming a version from a base is an act by a holder of `version.name`: the new version is a copy at naming. What people
decided on the base and still stands is copied onto it — layer entries, Finance's figures with the cells each wrote, the
schedule's acts, the assumption values and amendments, the promotions typed here and the neighbour lines — each copy under
a new id, keeping the author and time of the act it came from and naming it (`copied_from`); what arrived from outside is
referenced, not copied — the forecasting run in force per account and the promotions system's files the base had taken are
recorded on the new version as `take` acts. From then on the two are independent. A what-if keeps its base's from point; a
version for a new cycle takes a later one, and copied figures that now fall in actual periods are refused by the checks
that already refuse them — counted on the receipt first. Released by the whole run.

Promotion makes a version the latest view — the version every page opens on — by a holder of `scenario.promote`, with a
reason: the version comes back whole; nothing is merged into another and nothing is moved. Naming never moves the latest
view; promoting the base again is how a promotion is taken back.

Each version also carries its from point — the last period it treats as actual, fixed when it was named — and its horizon:
periods by month after the from point, then quarters, set from its kind when named. Every grid reads both from here. The
defaults by kind, and the shorter window a step plans (the opex schedule's rolling year), are shown beneath. Changing a
version's horizon is an act like closing: by a holder of `version.name`, with a reason and a receipt, inside the reach the
models calculate, the saved figures it would leave past the horizon (or bring back inside it) counted before it is
placed; released by a run from the version register down, since every grid reads the horizon. Registered on the plan's blueprint by `register(...)`, called from `face/__main__.py`."""
from __future__ import annotations

import datetime as dt

from chassis import receipts
from chassis.landing import LogLanding
from chassis.warehouse import Busy, q
from flask import redirect, request, url_for

from .words import said

VERB = "version.freeze"
COLUMNS = ["act_id", "version_id", "act", "reason", "entered_by", "entered_on", "horizon_periods",
           "base_version", "version_kind", "cycle", "fiscal_year", "from_period", "horizon_start", "horizon_end", "horizon_quarters",
           "calendar_variant", "standard_version", "reference_version", "owner",
           "arrival", "arrival_id", "account_code", "arrival_taken_in_at", "source_version"]
PROMOTE_VERB = "scenario.promote"
# what is copied at naming: the register, how its rows in force on the base are found, the id columns a copy renames
COPIES = [
    ("layer_entry", "layer entries", ["entry_id"],
     """select b.* from bronze.layer_entry b join plan.change_record r on r.record = 'demand plan' and r.act = 'entry' and r.act_id = b.entry_id
        where b.version_id = ? and coalesce(b.action, 'enter') = 'enter' and r.standing in ('stands', 'overwritten')"""),
    ("reg_finance_overlay", "Finance's figures", ["edit_id", "save_id", "typed"],
     """with f as (select r.act_id from plan.change_record r where r.record = 'Finance''s plan' and r.act = 'figure' and r.version_id = ?
                   and r.standing in ('stands', 'overwritten'))
        select b.* from bronze.reg_finance_overlay b where (b.action = 'enter' and b.edit_id in (select act_id from f))
                                                     or (b.action = 'cell' and b.typed in (select act_id from f))"""),
    ("reg_schedule_edit", "schedule acts", ["edit_id", "save_id"],
     """select b.* from bronze.reg_schedule_edit b join plan.change_record r on r.record = 'opex schedule' and r.act_id = b.edit_id
        where b.version_id = ? and b.action <> 'withdraw' and r.standing in ('stands', 'overwritten')"""),
    ("reg_capex", "capital plan items", ["act_id"],
     """select b.* from bronze.reg_capex b join plan.capex_item i on i.act_id = b.act_id where b.version_id = ? and i.standing = 'stands'"""),
    ("reg_assumption_amend", "assumption amendments", ["amend_id"],
     """select b.* from bronze.reg_assumption_amend b join plan.change_record r on r.record = 'assumptions' and r.act_id = b.amend_id
        where b.version_id = ? and b.valid_from <> 'ALL' and r.standing = 'stands'"""),
    ("reg_promo_event", "promotions typed here", [],
     """select b.* from bronze.reg_promo_event b join plan.promo_typed_event t on t.event_id = b.event_id and t.version_id = b.version_id
        where b.version_id = ? and t.state <> 'refused'
        qualify row_number() over (partition by b.event_id order by b.source_file desc, b.file_row_number desc) = 1"""),
    ("reg_unit_cost_act", "unit cost components typed", ["act_id"],
     """select b.* from bronze.reg_unit_cost_act b join plan.unit_cost_act a on a.act_id = b.act_id where b.version_id = ?"""),
    ("reg_production_act", "production quantities typed", ["act_id"],
     """select b.* from bronze.reg_production_act b join plan.production_act a on a.act_id = b.act_id where b.version_id = ?"""),
    ("reg_purchase_act", "purchases typed", ["act_id"],
     """select b.* from bronze.reg_purchase_act b join plan.purchase_act a on a.act_id = b.act_id where b.version_id = ?"""),
    ("reg_promo_neighbour", "neighbour lines", ["neighbour_id"],
     """select b.* from bronze.reg_promo_neighbour b where b.version_id = ?
        and b.neighbour_id in (select neighbour_id from plan.promo_neighbour where version_id = b.version_id)"""),
]
NOT_COPIED = "submissions (the new version's units start open), the base's own version acts, withdrawn, released and refused acts"
HORIZON_VERB = "version.name"
LANDING = LogLanding("plan", "reg_version_act", COLUMNS)


def _columns(table: str) -> list[str]:
    """A register's columns as loaded, without the load's own stamps; a copy adds the act it came from."""
    cols = [r["column_name"] for r in q(f"select column_name from (describe bronze.{table})")
            if not r["column_name"].startswith("_dlt") and r["column_name"] not in ("source_file", "file_row_number")]
    return cols + ([] if "copied_from" in cols else ["copied_from"])


def copies(base: str, new: str) -> dict[str, list[dict]]:
    """Every act in force on the base, as a row of its own register on the new version: a new id (`<id>@<version>`,
    the original's prefix kept, so what reads the kind of an id still reads it), the author and time of the act it came
    from, and that act named. The base's own assumption values come too, as the new version's values (from ALL).
    Where a copy of purchasing's receipts stands in the base, that copy is carried across instead (`purchasing_plan.carry`,
    DEC-20261121-02) and the base's typed purchases are not copied: on a plan with a standing copy it is all that is read."""
    from . import purchasing_plan
    skip = {"reg_purchase_act"} if purchasing_plan.standing(base) else set()
    out: dict[str, list[dict]] = {}
    for table, _, ids, sql in COPIES:
        rows = []
        for r in ([] if table in skip else q(sql, base)):
            r = {k: v for k, v in r.items() if not k.startswith("_dlt") and k not in ("source_file", "file_row_number")}
            origin = r.get(ids[0]) if ids else f"{base}:{r.get('event_id')}"
            for c in ids:
                if r.get(c):
                    r[c] = f"{r[c]}@{new}"
            rows.append({**r, "version_id": new, "copied_from": origin})
        out[table] = rows
    own = q("select assumption_code, value, owner, note from dims.reg_assumption where version_id = ? and period = 'ALL' order by assumption_code", base)
    b = q("select named_on from dims.ctl_version where version_id = ?", base)
    out["reg_assumption_amend"] += [{"amend_id": f"{a['assumption_code']}@{new}", "version_id": new, "assumption_code": a["assumption_code"],
                                     "valid_from": "ALL", "value": a["value"], "note": a["note"], "entered_by": a["owner"],
                                     "entered_on": str(b[0]["named_on"]) if b else "", "copied_from": f"{base}:{a['assumption_code']}"} for a in own]
    return out


def takes(base: str) -> list[dict]:
    """What arrived from outside and the base reads — referenced on the new version, never copied: the forecasting run in
    force per account, and every file from the promotions system the base had taken."""
    runs = q("select account_code, run_id, taken_in_at::TEXT taken_in_at from plan.version_run where version_id = ? order by account_code", base)
    files = q("select sender_file, taken_in_at, source_version from plan.version_sender_file where version_id = ? order by taken_in_at, sender_file", base)
    return ([{"arrival": "forecast_run", "arrival_id": r["run_id"], "account_code": r["account_code"], "arrival_taken_in_at": r["taken_in_at"],
              "source_version": base} for r in runs]
            + [{"arrival": "sender_file", "arrival_id": f["sender_file"], "account_code": "", "arrival_taken_in_at": f["taken_in_at"],
                "source_version": f["source_version"]} for f in files])
PAGE = """<h1>Plan administration<small>{{ process_label }} · the plans of its kind{{ '' if owned_kinds|length == 1 else 's' }} ({{ owned_kinds|join(', ') or 'none yet' }}) — named, open or closed; a closed version takes no entry and stays readable</small></h1>
{% if not owned_kinds %}<p class="lede">{{ process_label }} has no kind of plan of its own yet: it reads the versions below, which other processes administer.</p>{% endif %}
<p class="hint">{% if may %}You close and reopen versions: each is an act with a receipt; reopening asks why. A Plan another is read against is not reopened — a changed reference is a new version.{% else %}Versions are closed and reopened by {{ holders|join(', ') or 'nobody yet' }}.{% endif %} The actuals are closed by the period, not here.</p>
<table><thead><tr><th>Version</th><th>Kind</th><th>Cycle</th><th>Actual to</th><th>Horizon</th><th>Calculated</th><th>Read against</th><th>State</th><th>Last act</th>{% if may %}<th></th>{% endif %}</tr></thead><tbody>
{% for v in versions %}<tr class="{{ 'off' if v.status == 'closed' or not v.owned }}"><td><b>{{ v.version_id|planfull }}</b> <span class="small muted">{{ v.version_id }}</span>{% if v.is_latest_view %} <span class="state">the latest view</span>{% endif %}<div class="small muted">named {{ v.named_on }} · {{ v.owner }}{% if v.base_version %} · from {{ v.base_version }}{% endif %}</div>
{% if may_promote and v.owned and v.status == 'open' and v.version_kind == 'latest_view' and not v.is_latest_view %}<form class="inline" method="post" action="{{ url_for('plan.version_promote') }}"><input type="hidden" name="version_id" value="{{ v.version_id }}"><input name="reason" size="16" required placeholder="why it becomes the latest view"> <button class="act" onclick="this.textContent='Promoting…'">promote</button></form>{% endif %}</td><td class="small">{{ v.version_kind.replace('_', ' ') }}</td><td class="small">{{ v.cycle or '' }}</td>
<td class="small">{% if v.version_kind == 'actual' %}{{ v.from_period }}{% elif v.fiscal_year and v.from_period < v.fiscal_year ~ 'P01' %}<span class="muted">none in FY{{ v.fiscal_year }}</span>{% else %}{{ v.from_period }}{% endif %}</td>
<td class="small">{% if v.horizon_periods %}{{ v.horizon_periods }} periods, to {{ v.plan_through }}{% if v.horizon_quarters %}; then {{ v.horizon_quarters }} quarters{% endif %}{% else %}<span class="muted">nothing planned</span>{% endif %}{% if v.named_horizon_periods is not none and v.named_horizon_periods != v.horizon_periods %}<div class="muted">named with {{ v.named_horizon_periods }}</div>{% endif %}
{% if may_horizon and v.owned and v.status == 'open' and v.version_kind != 'actual' %}<form class="inline horizon" method="post" action="{{ url_for('plan.version_horizon') }}"><input type="hidden" name="version_id" value="{{ v.version_id }}"><input name="horizon_periods" size="3" inputmode="numeric" value="{{ v.horizon_periods }}" aria-label="periods by month"> <input name="reason" size="14" required placeholder="why it changes"> <button class="act" onclick="this.textContent='Changing…'">change</button></form>{% endif %}</td>
<td class="small">{{ v.horizon_start }} – {{ v.horizon_end }}</td><td class="small">{{ v.reference_version or '—' }}{% if v.reference_of %}<div class="muted">the reference of {{ v.reference_of }}</div>{% endif %}</td>
<td><span class="state">{{ v.status }}</span></td>
<td class="small">{% if v.last_act %}{{ v.last_act }} by {{ v.last_act_by }}, {{ (v.last_act_on or '')[:16].replace('T', ' ') }}{% if v.last_act_reason %} — {{ v.last_act_reason }}{% endif %}{% elif v.version_kind == 'actual' %}closed by the period{% else %}as named{% endif %}</td>
{% if may %}<td class="acts">{% if not v.owned %}<span class="small muted">{{ v.process_label }}'s — read only here</span>{% elif v.version_kind == 'actual' %}{% elif v.status == 'open' %}<form class="inline" method="post" action="{{ url_for('plan.version_close') }}"><input type="hidden" name="version_id" value="{{ v.version_id }}"><input name="reason" size="18" placeholder="note (optional)"> <button class="act" onclick="this.textContent='Closing…'">close</button></form>
{% elif v.is_reference %}<span class="small muted">not reopened — {{ v.reference_of.split(',')|map('trim')|map('plan')|join(', ') }} {{ 'is' if ',' not in v.reference_of else 'are' }} read against it</span>
{% else %}<form class="inline" method="post" action="{{ url_for('plan.version_reopen') }}"><input type="hidden" name="version_id" value="{{ v.version_id }}"><input name="reason" size="18" required placeholder="why it reopens"> <button class="act" onclick="this.textContent='Reopening…'">reopen</button></form>{% endif %}</td>{% endif %}</tr>{% endfor %}</tbody></table>
{% if last and last.act in ('version.close', 'version.reopen', 'version.horizon', 'version.name', 'version.promote') %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else '✕' }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}
<p class="hint"><b>Actual to</b> is the last period a version treats as actual, fixed when it was named: every grid on the version shows the periods of its year up to it as actuals, marked and never typed, by anyone — a later close does not move it; a later close is a new version. <b>Horizon</b> is how far the plan runs after it, past the year end where it reaches, and it is the version's own. <b>Calculated</b> is how far the plan's models calculate on the version; a horizon never runs past it.</p>
{% if may_name %}<h2>Name a version from another<span class="count">a copy of what was decided on it; what arrived from outside is read, not copied · <a href="{{ url_for('plan.plan_start') }}">start a plan</a> shows what is carried across first</span></h2>
<form class="entry" method="post" action="{{ url_for('plan.version_name') }}">
<label>from<select name="base_version">{% for v in versions if v.version_kind != 'actual' %}<option value="{{ v.version_id }}" {{ 'selected' if v.is_latest_view }}>{{ v.version_id }} · {{ v.status }} · actual to {{ v.from_period }}</option>{% endfor %}</select></label>
<label>code<input name="version_id" size="16" placeholder="{{ suggest }}" pattern="[A-Z0-9][A-Z0-9-]+"></label>
<label>actual to<select name="from_period">{% for pp in from_points %}<option value="{{ pp }}" {{ 'selected' if loop.first }}>{{ pp }}</option>{% endfor %}</select></label>
<label class="wide">why<input name="reason" required placeholder="a what-if, or the next cycle"></label>
<label class="small"><input type="checkbox" name="lock_source" value="1"> lock the one it is named from</label>
<label class="small"><input type="checkbox" name="lock_others" value="1"> lock every other version of its plan</label>
<button class="act" onclick="this.textContent='Naming…'">name</button></form>
<p class="hint">The new version starts as a copy of everything still standing on the one it is named from — the demand plan's entries, Finance's figures, the opex schedule, the assumptions, the promotions typed here and their neighbour lines — each under the name and time of whoever made it, marked with what it was copied from; the forecasting runs and the promotions system's files it reads are the same ones, read, not copied. From then on the two are independent. Keep the period it is actual to for a what-if; take a later one for the next cycle, and anything copied that falls in what is now actual is refused, and counted before it is placed. Not copied: {{ not_copied }}. Each stage starts as it stands on the one it is named from — signed off, published or open. Locking the source, or every other version of the plan, is done in the same act, with the same reason. Naming does not change which version is the latest view; promoting does.</p>{% endif %}
{% if steps_due %}<h2 id="due">Steps and their due dates<span class="count">what the workflow page reads as late · <a href="{{ url_for('plan.workflow') }}">workflow</a></span></h2>
<table><thead><tr><th>Step</th>{% for v in due_versions %}<th>{{ v }}</th>{% endfor %}{% if may_due %}<th></th>{% endif %}</tr></thead><tbody>
{% for s in steps_due %}<tr><td>{{ s.step_label }}{% if not s.built %} <span class="small muted">not built</span>{% endif %}</td>{% for v in due_versions %}<td class="small">{{ due.get((v, s.step)) or '—' }}</td>{% endfor %}
{% if may_due %}<td>{% if s.built %}<form class="inline" method="post" action="{{ url_for('plan.workflow_due') }}"><input type="hidden" name="step" value="{{ s.step }}"><select name="version">{% for v in due_versions %}<option>{{ v }}</option>{% endfor %}</select> <input name="due_on" type="date" required> <button class="act small">set</button></form>{% endif %}</td>{% endif %}</tr>{% endfor %}</tbody></table>{% endif %}
<h2>Horizons<span class="count">what each kind of version is named with, and the shorter window a step plans</span></h2>
<div class="cards"><div class="card"><table><thead><tr><th>Kind</th><th class="n">Periods by month</th><th class="n">Then quarters</th><th>Reaches</th></tr></thead><tbody>
{% for k in kinds %}<tr><td>{{ k.kind_label }}</td><td class="n">{{ k.horizon_periods }}</td><td class="n">{{ k.horizon_quarters }}</td><td class="small">{{ k.says }}</td></tr>{% endfor %}</tbody></table>
<p class="hint">A version takes its kind's horizon when it is named. Past the months a latest view runs in quarters to the end of the second fiscal year after its from point, the baseline carried forward: Finance's grid shows a column a quarter, the sum of its periods, and a figure typed on one is written down to them. A Plan's name does not carry its horizon — the reach is here.</p></div>
<div class="card"><table><thead><tr><th>Step</th><th class="n">Periods</th><th>Window</th></tr></thead><tbody>
{% for s in steps %}<tr><td>{{ s.step_label }}</td><td class="n">{{ s.horizon_periods }}</td><td class="small">{{ s.says }}</td></tr>{% endfor %}</tbody></table>
<p class="hint">A step may plan a shorter window than the version, never a longer one: it plans the lesser of the two.</p></div></div>
<h2>Acts<span class="count">every close, reopen, change of horizon, naming, port and promotion, newest first — the register the states and horizons above are read from · <a href="{{ url_for('plan.change_history') }}">change history</a></span></h2>
<table><thead><tr><th>When</th><th>Version</th><th>Act</th><th>By</th><th>Why</th></tr></thead><tbody>
{% for a in acts %}<tr><td class="small">{{ (a.entered_on or '')[:16].replace('T', ' ') }}</td><td>{{ a.version_id }}</td><td>{{ a.act }}{% if a.act == 'horizon' %} to {{ a.horizon_periods }} periods{% elif a.act == 'name' %} from {{ a.base_version }}, actual to {{ a.from_period }}{% if takes.get(a.version_id) %} <span class="small muted">· reads {{ takes[a.version_id] }} arrivals of its base's</span>{% endif %}{% elif a.act == 'promote' %} to the latest view{% elif a.act == 'port' %} from {{ a.base_version }}{% endif %}</td><td class="small">{{ a.entered_by }}</td><td class="small">{{ a.reason or '' }}</td></tr>
{% else %}<tr><td colspan="5" class="muted">No version has been closed or reopened.</td></tr>{% endfor %}
{% for w in waiting %}<tr><td class="small">{{ w.entered_on[:16].replace('T', ' ') }}</td><td>{{ w.version_id }}</td><td>{{ w.act }} <span class="small muted">placed, waiting for the run</span></td><td class="small">{{ w.entered_by }}</td><td class="small">{{ w.reason }}</td></tr>{% endfor %}</tbody></table>"""


# Start a plan (DEC-20261121-02): the same act as naming a version from another, from the IBP side's own entry — what will be
# carried across shown before, and the same list of parts as it stands in a plan afterwards. Purchasing is the one part that
# stands as a copy today; the rest of the plan is carried by naming as before.
START = """<h1>Start a plan<small>a new IBP plan begins as the prior plan carried across · each planner then replaces their part when they are ready</small></h1>
<h2><span class="step">1</span>The new plan</h2>
<div class="card"><form class="entry" method="post" action="{{ url_for('plan.version_name') }}" id="start"><input type="hidden" name="back" value="start">{% if request.args.get('version') %}<input type="hidden" name="version" value="{{ request.args.get('version') }}">{% endif %}
<label>Name <input name="version_id" value="{{ request.args.get('version_id', '') }}" placeholder="{{ suggest }}" pattern="[A-Z0-9][A-Z0-9-]+"><span class="hint">a code, {{ suggest }} if left empty; the plan reads by its cycle and its actual months, as every plan does</span></label>
<label>Carry across from <select name="base_version" onchange="redraw(this.form)">{% for v in bases %}<option value="{{ v.version_id }}" {{ 'selected' if v.version_id == base.version_id }}>{{ v.version_id|planfull }}{{ ' — the latest view' if v.is_latest_view }}{{ ' · closed' if v.status != 'open' }}</option>{% endfor %}</select><span class="hint">what stands in that plan is copied into this one, part by part</span></label>
<label>Actuals to <select name="from_period" onchange="redraw(this.form)">{% for pp in from_points %}<option value="{{ pp }}" {{ 'selected' if pp == from_p }}>{{ per(pp) }}{{ ' — the latest closed' if pp == last_closed }}</option>{% endfor %}</select><span class="hint">periods to this close are the record; nothing planned for them is carried</span></label>
<label>Plans through <input value="{{ per(st.through) if st.through else 'nothing to plan' }}" disabled><span class="hint">as far as {{ base.version_id|plan }} plans, within what the plan calculates</span></label>
<label class="wide">Why <input name="reason" required value="{{ request.args.get('reason', '') }}" placeholder="the next cycle, or a what-if"></label>
<div class="actions">{% if may_name %}<button class="primary" onclick="this.textContent='Starting…'">Start the plan</button>{% else %}<span class="muted small">Plans are started by {{ holders|join(', ') or 'nobody yet' }}.</span>{% endif %}<span class="hint">the plan is whole from the first moment: its figures are worked out from what was carried across, against the new close</span></div>
</form></div>
<script>function redrawn(f){const u=new URLSearchParams();for(const k of ['version','version_id','reason']){const e=f.elements[k];if(e&&e.value)u.set(k,e.value)}u.set('base',f.elements.base_version.value);u.set('actuals_to',f.elements.from_period.value);return u.toString()}
function redraw(f){location.search=redrawn(f)}</script>

<h2><span class="step">2</span>What will be carried across<span class="count">from {{ base.version_id|planfull }} · shown before you start</span></h2>
<table class="board"><thead><tr><th></th><th>Part of the plan</th><th>Sent by</th><th>Standing in the prior plan</th><th class="n">Carried</th><th>Left behind</th></tr></thead><tbody>
{% if carry %}{% set w = carry.was %}<tr><td class="mark">●</td><td><b>Purchasing</b><div class="small muted">{{ pn(plants_of(w.receipts)) or 'no plant' }}</div></td><td class="small">{{ (w.carried or {}).by or w.by }}</td>
<td>{{ w.source }}<div class="small muted">{% if w.carried %}carried across from {{ w.carried.from|planfull }} · sent {{ when(w.carried.at) }}{% else %}sent {{ when(w.at) }}{% endif %}</div></td>
<td class="n">{{ n(carry.receipts|length, 'receipt') }}</td>
<td class="small">{% for r in carry.left_behind %}<div>{{ names.get(r.input_code, r.input_code) }}, {{ plants.get(r.plant_code, r.plant_code) }}, {{ per(r.period) }} — {{ r.why }}</div>{% else %}<span class="muted">nothing</span>{% endfor %}</td></tr>
{% else %}<tr><td class="mark">○</td><td><b>Purchasing</b></td><td></td><td class="muted">nothing stands in {{ base.version_id|plan }}<div class="small">nothing is carried; the new plan has no additional receipts until purchasing sends one</div></td><td class="n">—</td><td></td></tr>{% endif %}
</tbody></table>
<p class="hint">Each part is copied as it stands in the prior plan — the facts its planner sent, not the figures worked out from them. A copy carried across is read-only, like any other. What was planned for a period that has since closed is left behind and named here. The rest of the plan is carried with it as before: everything still standing on {{ base.version_id|plan }} — the demand plan's entries, Finance's figures, the opex schedule, the assumptions, the promotions typed here — each under the name of whoever made it.</p>

{% if here %}<h2><span class="step">3</span>What stands in {{ here.version_id|planfull }}<span class="count">the same list, as it stands now · the plan chosen above</span></h2>
<div class="cards">
<div class="card stat"><span>Parts</span><b>{{ parts|length }}</b><div class="small muted">one copy standing in each</div></div>
<div class="card stat"><span>Sent for this plan</span><b>{{ parts|selectattr('sent')|list|length }}</b><div class="small muted">{{ parts|selectattr('sent')|map(attribute='name')|join(' · ') or 'none yet' }}</div></div>
<div class="card stat"><span>Still as carried across</span><b>{{ parts|selectattr('carried')|list|length }}</b><div class="small muted">{{ parts|selectattr('carried')|map(attribute='name')|join(' · ') or 'none' }}</div></div>
</div>
<table class="board"><thead><tr><th></th><th>Part of the plan</th><th>Sent by</th><th>Standing now</th><th>Since</th><th class="n">Holds</th><th></th></tr></thead><tbody>
{% for x in parts %}{% set s = x.held %}<tr><td class="mark">{{ '○' if x.carried else '●' }}</td><td><b>{{ x.name }}</b><div class="small muted">{{ pn(plants_of(s.receipts)) or 'no plant' }}</div></td><td class="small">{{ (s.carried or {}).by or s.by }}</td>
{% if x.carried %}<td class="muted">carried across from {{ s.carried.from|planfull }}<div class="small">{{ s.source }}, sent {{ when(s.carried.at) }}{% if s.carried.left_behind %} · left behind: {% for r in s.carried.left_behind %}{{ names.get(r.input_code, r.input_code) }}, {{ plants.get(r.plant_code, r.plant_code) }}, {{ per(r.period) }} — {{ r.why }}{{ '; ' if not loop.last }}{% endfor %}{% endif %}</div></td>
{% else %}<td>{{ s.source }}<div class="small muted">sent for this plan{% if s.made_against %} · made against {% for c in s.made_against.copies %}consumption at {{ plants.get(c.plant, c.plant) }} from {{ c.source|plan }} of {{ when(c.taken_at) }}{{ ', ' if not loop.last }}{% endfor %}{% endif %}</div></td>{% endif %}
<td class="small">{{ when(s.at) }}</td><td class="n">{{ n(s.receipts|length, 'receipt') }}</td><td class="acts"><form class="inline" method="get" action="{{ url_for('plan.material_stock') }}"><input type="hidden" name="version" value="{{ here.version_id }}"><button class="act">View</button></form></td></tr>
{% else %}<tr><td class="mark">○</td><td><b>Purchasing</b></td><td></td><td class="muted" colspan="4">nothing stands in {{ here.version_id|plan }} — it has no additional receipts</td></tr>{% endfor %}
</tbody></table>
<p class="hint">● sent for this plan · ○ still as carried across. One copy stands in each part; a planner sending again replaces it, and nothing earlier is kept. The plan's figures are worked out again from what stands whenever a part is replaced. Closing the plan closes every part with it.</p>{% endif %}
{% if last and last.act == 'version.name' %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok and not c.flag else ('!' if c.flag else '✕') }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}
<style>h2 .step{display:inline-grid;place-items:center;width:1.5rem;height:1.5rem;margin-right:.5rem;border:1px solid var(--ink);border-radius:50%;font:400 .8rem var(--sans);vertical-align:.15em}
table.board td.mark{width:1.4rem;color:var(--muted)}</style>"""


def starting(base: dict, from_p: str) -> dict:
    """What a version named from `base` with actuals to `from_p` will plan, as naming sets it: its first plan period, its
    horizon — the base's, within what the models calculate — and the plan periods that horizon covers."""
    known = bool(from_p) and bool(q("select 1 from dims.dim_period where period = ?", from_p))
    later = bool(base) and from_p != base.get("from_period")
    start = base.get("horizon_start")
    if later and known:
        start = (q("select min(period) p from dims.dim_period where period > ?", from_p) or [{}])[0].get("p")
    reach = q("select count(*) n from dims.dim_period where period > ? and period <= ?", from_p, base.get("horizon_end") or "")[0]["n"] if known else 0
    horizon = min(int(base.get("horizon_periods") or 0), reach)
    periods = [r["period"] for r in q("select period from dims.dim_period where period > ? order by period limit ?", from_p, horizon)] if known and horizon else []
    return {"known": known, "later": later, "start": start, "horizon": horizon, "periods": periods, "through": periods[-1] if periods else None}


def suggest_code(base: str, base_from: str | None, taken: list[str], from_period: str | None = None) -> str:
    """A code for a version named from `base`: for a later from point, the base's code with its period replaced (the
    next cycle); for the same from point, the base's code with the first letter not yet taken (a what-if)."""
    import re
    if from_period and base_from and from_period != base_from and re.match(r"[A-Z]\d{6}", base):
        fy, p = int(from_period[:4]), int(from_period[-2:])         # the next cycle: the kind and its first planned period
        return base[0] + (f"{fy}{p + 1:02d}" if p < 12 else f"{fy + 1}01")
    for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        if f"{base}-{c}" not in taken:
            return f"{base}-{c}"
    return f"{base}-Z"


def register(bp, page, who_fn, busy, session, roles, run_plan, scoped: dict) -> None:
    from . import reads
    import csv
    scoped["versions"] = {"what": "version state",
                          "says": "run completed — the version's state is the act just taken"}
    scoped["version_horizon"] = {"what": "version horizon",
                                 "says": "run completed — every grid on the version takes its new horizon"}

    def _waiting() -> list[dict]:
        out = []
        for p in LANDING.pending():
            with open(p, newline="") as fh:
                out += list(csv.DictReader(fh))
        return out

    @bp.get("/versions")
    def versions():
        try:
            who = who_fn()
            proc = request.args.get("via") or "ibp"            # the process whose plans these are (DEC-20261115-03 point 2)
            from .workflow import PROCESS_LABEL
            kinds_ = reads.version_kinds()
            process_of = {k["version_kind"]: k.get("process") for k in kinds_}
            owned_kinds = [k["kind_label"].lower() for k in kinds_ if k.get("process") == proc]
            vs = [{**v, "owned": process_of.get(v.get("version_kind")) == proc,
                   "process_label": PROCESS_LABEL.get(process_of.get(v.get("version_kind")), "the close")} for v in reads.versions()]
            vs.sort(key=lambda v: not v["owned"])
            steps_due = q("select * from plan.ref_step where process = ? order by ord", proc)
            due_versions = [v["version_id"] for v in vs if v["owned"] and v.get("status") == "open"]
            due = {(r["version_id"], r["step"]): str(r["due_on"]) for r in q("select distinct version_id, step, due_on from plan.step_state where due_on is not null")}
            last_closed = (q("select max(period) p from dims.dim_period where period_state = 'CLOSED'") or [{}])[0].get("p")
            latest = next((v for v in vs if v.get("is_latest_view")), None) or next((v for v in vs if v.get("version_kind") != "actual"), {})
            from_points = [r["period"] for r in q("select period from dims.dim_period where period >= ? and period <= ? order by period",
                                                   latest.get("from_period") or "", last_closed or "")]
            takes_n = {r["version_id"]: r["n"] for r in q("select version_id, count(*) n from plan.version_act where act = 'take' group by 1")}
            return page(PAGE, title="Versions", active="versions", versions=vs, acts=q("select * from plan.version_act where act <> 'take' order by entered_on desc, act_id desc"),
                        waiting=[w for w in _waiting() if w.get("act") != "take"], kinds=reads.version_kinds(), steps=reads.step_horizons(), may=roles.may(who, VERB), holders=reads.holders(VERB),
                        may_horizon=roles.may(who, HORIZON_VERB), may_name=roles.may(who, HORIZON_VERB), may_promote=roles.may(who, PROMOTE_VERB),
                        suggest=suggest_code(latest.get("version_id") or "", latest.get("from_period"), [v["version_id"] for v in vs]) if latest else "",
                        from_points=from_points, takes=takes_n, not_copied=NOT_COPIED, last=session.last, receipt_acts=("version.",),
                        process_label=PROCESS_LABEL.get(proc, proc), owned_kinds=owned_kinds, steps_due=steps_due, due_versions=due_versions, due=due,
                        may_due=roles.may(who, "cycle.open"))
        except Busy as e:
            return busy("Versions", e)

    @bp.get("/versions/start")
    def plan_start():
        """Start a plan: the naming act's own entry on the IBP side — what will be carried across from the base, before,
        and what stands in the plan chosen above, after (DEC-20261121-02)."""
        try:
            from . import purchasing_plan
            from .purchases import per, when
            who = who_fn()
            bases = [v for v in reads.versions() if v.get("version_kind") != "actual"]
            latest = next((v for v in bases if v.get("is_latest_view")), bases[0] if bases else {})
            base = next((v for v in bases if v["version_id"] == request.args.get("base")), latest)
            last_closed = (q("select max(period) p from dims.dim_period where period_state = 'CLOSED'") or [{}])[0].get("p") or ""
            from_points = [r["period"] for r in q("select period from dims.dim_period where period >= ? and period <= ? order by period",
                                                   base.get("from_period") or "", last_closed)] or [base.get("from_period")]
            from_p = request.args.get("actuals_to") if request.args.get("actuals_to") in from_points else from_points[-1]
            st = starting(base, from_p)
            taken = [v["version_id"] for v in reads.versions()] + [w.get("version_id") for w in _waiting() if w.get("act") == "name"]
            here = reads.version(request.args.get("version") or "") or reads.version(reads.default_version() or "")
            s = purchasing_plan.standing(here["version_id"]) if here else None
            parts = [{"name": "Purchasing", "held": s, "carried": bool((s.get("carried") or {}).get("from")), "sent": not (s.get("carried") or {}).get("from")}] if s else []
            plants = {r["node_code"]: r["node_name"] for r in q("select node_code, node_name from dims.dim_node")}
            names = {r["material_code"]: r["material_name"] for r in q("select material_code, material_name from dims.dim_input_material")}
            return page(START, title="Start a plan", active="start", width="1240px", bases=bases, base=base, from_points=from_points, from_p=from_p,
                        last_closed=last_closed, st=st, suggest=suggest_code(base.get("version_id") or "", base.get("from_period"), taken, from_p),
                        carry=purchasing_plan.carried(base.get("version_id") or "", from_p, st["periods"]), here=here, parts=parts,
                        may_name=roles.may(who, HORIZON_VERB), holders=reads.holders(HORIZON_VERB), plants=plants, names=names,
                        plants_of=lambda rs: sorted({r["plant_code"] for r in rs or []}),
                        pn=lambda codes: " and ".join(plants.get(c, c) for c in codes),
                        n=lambda k, w: f"{k} {w}{'' if k == 1 else 's'}", per=per, when=when, last=session.last, receipt_acts=("version.name",))
        except Busy as e:
            return busy("Start a plan", e)

    def _act(kind: str):
        f = request.form; who = who_fn(); vid = f.get("version_id", ""); reason = (f.get("reason") or "").strip()
        v = reads.version(vid) or {}
        may = roles.may(who, VERB)
        want = "open" if kind == "close" else "closed"
        checks = [
            {"check": f"who may {kind}", "ok": may, "says": f"{who} holds {said(VERB)}" if may else f"{who} does not hold {said(VERB)} — versions are closed and reopened by {', '.join(reads.holders(VERB)) or 'nobody yet'}"},
            {"check": "a version of the plan", "ok": bool(v) and v.get("version_kind") != "actual",
             "says": f"{vid} · {(v.get('version_kind') or '').replace('_', ' ')}" if v and v.get("version_kind") != "actual" else (f"{vid} is the actuals — closed by the period, not by an act" if v else f"{vid or 'nothing'} is not a version")},
            {"check": f"the version is {want}", "ok": v.get("status") == want, "says": f"{vid} is {v.get('status', 'unknown')}"},
        ]
        if kind == "reopen":
            checks += [
                {"check": "not the reference of another", "ok": not v.get("is_reference"),
                 "says": "no version is read against it" if not v.get("is_reference") else
                         f"{v.get('reference_of')} {'is' if ',' not in (v.get('reference_of') or '') else 'are'} read against {vid} — a changed reference is a new version, or every gap read against it would move without anyone having decided it"},
                {"check": "a reason", "ok": bool(reason), "says": reason or "reopening a version says why"},
            ]
        placed = receipts.judge(checks)
        if placed:
            now = dt.datetime.now()
            LANDING.place([{"act_id": f"VA-{now.strftime('%Y%m%d-%H%M%S-%f')}", "version_id": vid, "act": kind, "reason": reason,
                            "entered_by": who, "entered_on": now.isoformat(timespec="seconds"), "horizon_periods": ""}], who)
        session.last = receipts.write(f"version.{kind}", who, vid, checks, placed)
        if not placed:
            session.say(f"{kind} refused: " + "; ".join(c["says"] for c in checks if not c["ok"]), False)
            return redirect(url_for("plan.versions"))
        if run_plan(who, "versions"):
            session.say(f"{vid} {'closed — no entry or change is taken on it; it stays readable' if kind == 'close' else 'reopened'}", True)
            return redirect(url_for("plan.versions"))
        return redirect(url_for("plan.run"))

    @bp.post("/versions/close")
    def version_close():
        return _act("close")

    @bp.post("/versions/reopen")
    def version_reopen():
        return _act("reopen")

    @bp.post("/versions/name")
    def version_name():
        """A version named from a base: a copy at naming of what was decided on the base and stands, and a reference to
        what arrived from outside — checked, counted on the receipt, then placed as files and released by the whole run."""
        import re
        f = request.form; who = who_fn(); reason = (f.get("reason") or "").strip()
        base_id = f.get("base_version", ""); base = reads.version(base_id) or {}
        vs = reads.versions(); taken = [v["version_id"] for v in vs] + [w.get("version_id") for w in _waiting() if w.get("act") == "name"]
        from_p = (f.get("from_period") or base.get("from_period") or "").strip()
        code = (f.get("version_id") or "").strip().upper() or suggest_code(base_id, base.get("from_period"), taken, from_p)
        last_closed = (q("select max(period) p from dims.dim_period where period_state = 'CLOSED'") or [{}])[0].get("p") or ""
        st = starting(base, from_p)
        known, later, start, horizon = st["known"], st["later"], st["start"], st["horizon"]
        back = "plan.plan_start" if f.get("back") == "start" else "plan.versions"
        may = roles.may(who, HORIZON_VERB)
        checks = [
            {"check": "who may name a version", "ok": may, "says": f"{who} holds {said(HORIZON_VERB)}" if may else f"{who} does not hold {said(HORIZON_VERB)} — versions are named by {', '.join(reads.holders(HORIZON_VERB)) or 'nobody yet'}"},
            {"check": "a version of the plan to start from", "ok": bool(base) and base.get("version_kind") != "actual",
             "says": f"{base_id} · {(base.get('version_kind') or '').replace('_', ' ')} · {base.get('status')}" if base and base.get("version_kind") != "actual" else f"{base_id or 'nothing'} is not a version of the plan"},
            {"check": "a new code", "ok": bool(re.fullmatch(r"[A-Z0-9][A-Z0-9-]{1,30}", code)) and code not in taken,
             "says": f"{code}" if code not in taken and re.fullmatch(r"[A-Z0-9][A-Z0-9-]{1,30}", code) else (f"{code} is already a version" if code in taken else f"'{code}' is not a code — letters, digits and hyphens")},
            {"check": "actual to", "ok": known and bool(base) and from_p >= (base.get("from_period") or "") and from_p <= last_closed and from_p < (base.get("horizon_end") or ""),
             "says": (f"{from_p} — {'a later from point: a new cycle' if later else 'the base' + chr(39) + 's own: a what-if'}" if known and base and base.get("from_period") <= from_p <= last_closed
                      else f"{from_p or 'nothing'} — a version is actual to its base's period or a later one, never after the last closed period ({last_closed})")},
            {"check": "a reason", "ok": bool(reason), "says": reason or "naming a version says why"},
        ]
        from . import purchasing_plan
        rows = copies(base_id, code) if all(c["ok"] for c in checks[:2]) else {}
        arrivals = takes(base_id) if rows else []
        if rows:
            n = {t: len(r) for t, r in rows.items()}
            n["reg_finance_overlay"] = sum(1 for r in rows["reg_finance_overlay"] if r.get("action") == "enter")      # a figure, not the cells it wrote
            n["reg_assumption_amend"] = sum(1 for r in rows["reg_assumption_amend"] if r.get("valid_from") != "ALL")
            checks.append({"check": "what is copied", "ok": True,
                           "says": " · ".join(f"{n[t]} {label}" for t, label, _, _ in COPIES) + f" · {sum(1 for r in rows['reg_assumption_amend'] if r.get('valid_from') == 'ALL')} assumption values"})
            checks.append({"check": "what is read, not copied", "ok": True,
                           "says": " · ".join(x for x in [f"{sum(1 for a in arrivals if a['arrival'] == 'forecast_run')} forecasting runs, by account",
                                                         f"{sum(1 for a in arrivals if a['arrival'] == 'sender_file')} files from the promotions system"]) })
            if later and known:
                past = (sum(1 for r in rows["layer_entry"] if (r.get("period_from") or "") <= from_p)
                        + sum(1 for r in rows["reg_finance_overlay"] if r.get("action") == "enter" and (r.get("period") or "") <= from_p)
                        + sum(1 for r in rows["reg_schedule_edit"] if r.get("period") and r["period"] <= from_p))
                if past:
                    checks.append({"check": "copied into what is now actual", "ok": False, "flag": True,
                                   "says": f"{past} copied entries, figures and months start in or before {from_p}: they are refused there, kept on record"})
        carry = purchasing_plan.carried(base_id, from_p, st["periods"]) if rows else None
        if carry:
            left = carry["left_behind"]
            checks.append({"check": "purchasing's copy carried", "ok": True, "flag": bool(left),
                           "says": f"{len(carry['receipts'])} receipt{'s' if len(carry['receipts']) != 1 else ''} of “{carry['was']['source']}”, standing in {base_id}"
                                   + (" · left behind: " + "; ".join(f"{r['input_code']} at {r['plant_code']} in {r['period']} — {r['why']}" for r in left) if left else "")})
        # creating a version: its stage states start as the source's, and it may lock the source or every other version of
        # its plan in the same act (DEC-20261123-01 points 3, 8, 11; ambiguity #126)
        stage_from = [r for r in q("select stage, last_action, last_reason from plan.stage_state where version_id = ? and last_action in ('hand_over', 'publish') and ord = unit_to", base_id)] if rows else []
        pv = purchasing_plan.plan_versions([v for v in vs if v.get("version_kind") != "actual"])
        plan_of = (pv.get(base_id) or {}).get("plan")
        to_lock = ([base_id] if f.get("lock_source") else []) + ([x for x, y in pv.items() if y["plan"] == plan_of and x != base_id] if f.get("lock_others") else [])
        to_lock = [x for x in dict.fromkeys(to_lock) if (reads.version(x) or {}).get("status") == "open"]
        if stage_from or f.get("lock_source") or f.get("lock_others"):
            may_lock = roles.may(who, VERB)
            checks.append({"check": "stages and locks", "ok": may_lock or not to_lock,
                           "says": " · ".join(x for x in [
                               ("stages as on " + base_id + ": " + ", ".join(f"{r['stage']} {'published' if r['last_action'] == 'publish' else 'signed off'}" for r in stage_from)) if stage_from else "every stage open, as on " + base_id,
                               (("locks " + ", ".join(to_lock)) if may_lock else f"{who} does not hold {said(VERB)} — versions are locked by {', '.join(reads.holders(VERB)) or 'nobody yet'}") if to_lock else ""] if x)})
        placed = receipts.judge(checks)
        if placed:
            now = dt.datetime.now(); stamp = now.strftime('%Y%m%d-%H%M%S-%f'); when = now.isoformat(timespec="seconds")
            if to_lock:
                LANDING.place([{"act_id": f"VA-{stamp}-L{i:02d}", "version_id": x, "act": "close", "reason": f"locked when {code} was named from {base_id}: {reason}",
                                "entered_by": who, "entered_on": when, "horizon_periods": ""} for i, x in enumerate(to_lock, start=1)], who)
            if stage_from:
                from . import stages as S
                S.ACTS.place([{"act_id": f"SA-{stamp}-{i:02d}", "version_id": code, "stage": r["stage"], "action": r["last_action"],
                               "reason": f"as on {base_id}" + (f": {r['last_reason']}" if r.get("last_reason") else ""), "entered_by": who, "entered_at": when}
                              for i, r in enumerate(stage_from, start=1)], who)
            act = {"act_id": f"VA-{stamp}", "version_id": code, "act": "name", "reason": reason, "entered_by": who, "entered_on": when,
                   "horizon_periods": str(horizon), "base_version": base_id, "version_kind": base.get("version_kind"),
                   "cycle": re.sub(r"\d{4}P\d{2}", from_p, base.get("cycle") or "") if later else base.get("cycle"),
                   "fiscal_year": (q("select fiscal_year from dims.dim_period where period = ?", start) or [{}])[0].get("fiscal_year") or base.get("fiscal_year"),
                   "from_period": from_p, "horizon_start": start, "horizon_end": base.get("horizon_end"), "horizon_quarters": str(base.get("horizon_quarters") or 0),
                   "calendar_variant": base.get("calendar_variant"), "standard_version": base.get("standard_version"),
                   "reference_version": base.get("reference_version") or "", "owner": base.get("owner")}
            LANDING.place([act] + [{"act_id": f"VA-{stamp}-T{i:02d}", "version_id": code, "act": "take", "reason": f"read from {base_id} at naming",
                                    "entered_by": who, "entered_on": when, "base_version": base_id, **a} for i, a in enumerate(arrivals, start=1)], who)
            for table, rs in rows.items():
                if rs:
                    LogLanding("plan", table, _columns(table)).place(rs, who)
            if carry:
                purchasing_plan.carry(base_id, code, from_p, st["periods"], who)
        session.last = receipts.write("version.name", who, code, checks, placed)
        if not placed:
            session.say("not named: " + "; ".join(c["says"] for c in checks if not c["ok"] and not c.get("flag")), False)
            return redirect(url_for(back, base=base_id, actuals_to=from_p) if back == "plan.plan_start" else url_for(back))
        if run_plan(who, ""):
            session.say(f"{code} named from {base_id}, actual to {from_p} — a copy of what stands on {base_id}; the two are independent from now", True)
            return redirect(url_for(back, version=code) if back == "plan.plan_start" else url_for(back))
        return redirect(url_for("plan.run"))

    @bp.post("/versions/promote")
    def version_promote():
        """A version promoted to the latest view, whole: an act by a holder of scenario.promote, with a reason. Nothing is
        merged and nothing moves but which version is the latest view."""
        f = request.form; who = who_fn(); vid = f.get("version_id", ""); reason = (f.get("reason") or "").strip()
        v = reads.version(vid) or {}
        may = roles.may(who, PROMOTE_VERB)
        checks = [
            {"check": "who may promote", "ok": may, "says": f"{who} holds {said(PROMOTE_VERB)}" if may else f"{who} does not hold {said(PROMOTE_VERB)} — a version is promoted by {', '.join(reads.holders(PROMOTE_VERB)) or 'nobody yet'}"},
            {"check": "a latest view, open", "ok": bool(v) and v.get("version_kind") == "latest_view" and v.get("status") == "open",
             "says": f"{vid} · {(v.get('version_kind') or '').replace('_', ' ')} · {v.get('status')}" if v else f"{vid or 'nothing'} is not a version"},
            {"check": "not already the latest view", "ok": not v.get("is_latest_view"), "says": f"{vid} is the latest view already" if v.get("is_latest_view") else f"{vid} becomes the latest view, whole"},
            {"check": "a reason", "ok": bool(reason), "says": reason or "a promotion says why"},
        ]
        placed = receipts.judge(checks)
        if placed:
            now = dt.datetime.now()
            LANDING.place([{"act_id": f"VA-{now.strftime('%Y%m%d-%H%M%S-%f')}", "version_id": vid, "act": "promote", "reason": reason,
                            "entered_by": who, "entered_on": now.isoformat(timespec="seconds")}], who)
        session.last = receipts.write("version.promote", who, vid, checks, placed)
        if not placed:
            session.say("not promoted: " + "; ".join(c["says"] for c in checks if not c["ok"]), False)
            return redirect(url_for("plan.versions"))
        if run_plan(who, "versions"):
            session.say(f"{vid} is the latest view — every page opens on it", True)
            return redirect(url_for("plan.versions"))
        return redirect(url_for("plan.run"))

    @bp.post("/versions/horizon")
    def version_horizon():
        """A version's horizon changed: an act, never an edit of the register — by a holder of version.name, on an open
        version, with a reason, inside the reach the models calculate. The saved figures it leaves past the new horizon
        are refused by the plan's own check, kept on record; those it brings back inside are taken again — both are
        counted on the receipt before anything is placed, told and not refused."""
        f = request.form; who = who_fn(); vid = f.get("version_id", ""); reason = (f.get("reason") or "").strip()
        raw = (f.get("horizon_periods") or "").strip()
        v = reads.version(vid) or {}
        n = int(raw) if raw.isdigit() else None
        through = None
        if n and v.get("from_period"):
            r = q("select period from dims.dim_period where period > ? order by period limit 1 offset ?", v["from_period"], n - 1)
            through = r[0]["period"] if r else None
        inside = bool(through) and through <= (v.get("horizon_end") or "")
        may = roles.may(who, HORIZON_VERB)
        out_ = back = 0
        if inside:
            out_ = q("select count(*) n from plan.finance_edit where version_id = ? and state = 'in_force' and period > ?", vid, through)[0]["n"]
            back = q("select count(*) n from plan.finance_edit where version_id = ? and state like 'refused: past%' and period <= ?", vid, through)[0]["n"]
        checks = [
            {"check": "who may change a horizon", "ok": may, "says": f"{who} holds {said(HORIZON_VERB)}" if may else f"{who} does not hold {said(HORIZON_VERB)} — a version's horizon is set by {', '.join(reads.holders(HORIZON_VERB)) or 'nobody yet'}"},
            {"check": "a version of the plan, open", "ok": bool(v) and v.get("version_kind") != "actual" and v.get("status") == "open",
             "says": f"{vid} is {v.get('status', 'unknown')}" if v else f"{vid or 'nothing'} is not a version"},
            {"check": "periods by month", "ok": bool(n) and n <= 60, "says": f"{n} periods after {v.get('from_period')}" if n and n <= 60 else f"'{raw}' is not a whole number of periods from 1 to 60"},
            {"check": "a change", "ok": n != v.get("horizon_periods"), "says": f"{v.get('horizon_periods')} → {n}" if n != v.get("horizon_periods") else f"{vid} already plans {n} periods"},
            {"check": "inside what the plan calculates", "ok": inside,
             "says": f"to {through}, inside {v.get('horizon_start')} – {v.get('horizon_end')}" if inside else f"{n} periods would run past {v.get('horizon_end')}, the last period the models calculate on {vid}"},
            {"check": "a reason", "ok": bool(reason), "says": reason or "a changed horizon says why"},
        ]
        if inside and (out_ or back):
            checks.append({"check": "saved figures", "ok": False, "flag": True,
                           "says": " · ".join(x for x in [f"{out_} of Finance's saved figures fall past {through} and are refused, kept on record" if out_ else "",
                                                          f"{back} refused for lying past the horizon come back inside it" if back else ""] if x)})
        placed = receipts.judge(checks)
        if placed:
            now = dt.datetime.now()
            LANDING.place([{"act_id": f"VA-{now.strftime('%Y%m%d-%H%M%S-%f')}", "version_id": vid, "act": "horizon", "reason": reason,
                            "entered_by": who, "entered_on": now.isoformat(timespec="seconds"), "horizon_periods": str(n)}], who)
        session.last = receipts.write("version.horizon", who, vid, checks, placed)
        if not placed:
            session.say("horizon not changed: " + "; ".join(c["says"] for c in checks if not c["ok"] and not c.get("flag")), False)
            return redirect(url_for("plan.versions"))
        if run_plan(who, "version_horizon"):
            session.say(f"{vid} now plans {n} periods, to {through} — every grid on it takes the new horizon", True)
            return redirect(url_for("plan.versions"))
        return redirect(url_for("plan.run"))
