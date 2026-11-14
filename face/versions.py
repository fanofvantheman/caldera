"""Versions, and closing and reopening one (DEC-20261113-05, first part): a version is open or closed, and the state is
read from a register of acts (plan.version_act → plan.version_state), never edited in place. Close and reopen are acts by
the holders of `version.freeze`, each with a receipt; reopening asks for a reason; a version that is the declared reference
of another is not reopened — a changed reference is a new version, or every gap read against it would move without
anyone having decided it. A closed version takes no entry and no change of any register; it stays readable, and every
calculation keeps reading it.

An act is a file in the landing, released at once by a run scoped to the version's state (the whole run when another file
is waiting). Naming a new version from a base and any state per step inside a version are not built — the decision
leaves both open.

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
COLUMNS = ["act_id", "version_id", "act", "reason", "entered_by", "entered_on", "horizon_periods"]
HORIZON_VERB = "version.name"
HORIZON_RUN = [["uv", "run", "python", "-m", "ingest.pipeline", "--only", "reg_version_act"],
               ["uv", "run", "sqlmesh", "plan", "prod", "--restate-model", "dims.ctl_version+", "--restate-model", "plan.version_act+",
                "--auto-apply", "--no-prompts"]]
LANDING = LogLanding("plan", "reg_version_act", COLUMNS)
RUN = [["uv", "run", "python", "-m", "ingest.pipeline", "--only", "reg_version_act"],
       ["uv", "run", "sqlmesh", "plan", "prod", "--restate-model", "plan.version_act+", "--auto-apply", "--no-prompts"]]

PAGE = """<h1>Versions<small>named, owned, open or closed — the plan is a stack of entries on a version; a closed version takes no entry and stays readable</small></h1>
<p class="hint">{% if may %}You close and reopen versions: each is an act with a receipt; reopening asks why. A version another is read against is not reopened — a changed reference is a new version.{% else %}Versions are closed and reopened by {{ holders|join(', ') or 'nobody yet' }}.{% endif %} The actuals are closed by the period, not here.</p>
<table><thead><tr><th>Version</th><th>Kind</th><th>Cycle</th><th>Actual to</th><th>Horizon</th><th>Calculated</th><th>Read against</th><th>State</th><th>Last act</th>{% if may %}<th></th>{% endif %}</tr></thead><tbody>
{% for v in versions %}<tr class="{{ 'off' if v.status == 'closed' }}"><td><b>{{ v.version_id }}</b><div class="small muted">named {{ v.named_on }} · {{ v.owner }}</div></td><td class="small">{{ v.version_kind.replace('_', ' ') }}</td><td class="small">{{ v.cycle or '' }}</td>
<td class="small">{% if v.version_kind == 'actual' %}{{ v.from_period }}{% elif v.fiscal_year and v.from_period < v.fiscal_year ~ 'P01' %}<span class="muted">none in FY{{ v.fiscal_year }}</span>{% else %}{{ v.from_period }}{% endif %}</td>
<td class="small">{% if v.horizon_periods %}{{ v.horizon_periods }} periods, to {{ v.plan_through }}{% if v.horizon_quarters %}; then {{ v.horizon_quarters }} quarters{% endif %}{% else %}<span class="muted">nothing planned</span>{% endif %}{% if v.named_horizon_periods is not none and v.named_horizon_periods != v.horizon_periods %}<div class="muted">named with {{ v.named_horizon_periods }}</div>{% endif %}
{% if may_horizon and v.status == 'open' and v.version_kind != 'actual' %}<form class="inline horizon" method="post" action="{{ url_for('plan.version_horizon') }}"><input type="hidden" name="version_id" value="{{ v.version_id }}"><input name="horizon_periods" size="3" inputmode="numeric" value="{{ v.horizon_periods }}" aria-label="periods by month"> <input name="reason" size="14" required placeholder="why it changes"> <button class="act" onclick="this.textContent='Changing…'">change</button></form>{% endif %}</td>
<td class="small">{{ v.horizon_start }} – {{ v.horizon_end }}</td><td class="small">{{ v.reference_version or '—' }}{% if v.reference_of %}<div class="muted">the reference of {{ v.reference_of }}</div>{% endif %}</td>
<td><span class="state">{{ v.status }}</span></td>
<td class="small">{% if v.last_act %}{{ v.last_act }} by {{ v.last_act_by }}, {{ (v.last_act_on or '')[:16].replace('T', ' ') }}{% if v.last_act_reason %} — {{ v.last_act_reason }}{% endif %}{% elif v.version_kind == 'actual' %}closed by the period{% else %}as named{% endif %}</td>
{% if may %}<td class="acts">{% if v.version_kind == 'actual' %}{% elif v.status == 'open' %}<form class="inline" method="post" action="{{ url_for('plan.version_close') }}"><input type="hidden" name="version_id" value="{{ v.version_id }}"><input name="reason" size="18" placeholder="note (optional)"> <button class="act" onclick="this.textContent='Closing…'">close</button></form>
{% elif v.is_reference %}<span class="small muted">not reopened — {{ v.reference_of }} {{ 'is' if ',' not in v.reference_of else 'are' }} read against it</span>
{% else %}<form class="inline" method="post" action="{{ url_for('plan.version_reopen') }}"><input type="hidden" name="version_id" value="{{ v.version_id }}"><input name="reason" size="18" required placeholder="why it reopens"> <button class="act" onclick="this.textContent='Reopening…'">reopen</button></form>{% endif %}</td>{% endif %}</tr>{% endfor %}</tbody></table>
{% if last and last.act in ('version.close', 'version.reopen', 'version.horizon') %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else '✕' }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}
<p class="hint"><b>Actual to</b> is the last period a version treats as actual, fixed when it was named: every grid on the version shows the periods of its year up to it as actuals, marked and never typed, by anyone — a later close does not move it; a later close is a new version. <b>Horizon</b> is how far the plan runs after it, past the year end where it reaches, and it is the version's own. <b>Calculated</b> is how far the plan's models calculate on the version; a horizon never runs past it.</p>
<h2>Horizons<span class="count">what each kind of version is named with, and the shorter window a step plans</span></h2>
<div class="cards"><div class="card"><table><thead><tr><th>Kind</th><th class="n">Periods by month</th><th class="n">Then quarters</th><th>Reaches</th></tr></thead><tbody>
{% for k in kinds %}<tr><td>{{ k.kind_label }}</td><td class="n">{{ k.horizon_periods }}</td><td class="n">{{ k.horizon_quarters }}</td><td class="small">{{ k.says }}</td></tr>{% endfor %}</tbody></table>
<p class="hint">A version takes its kind's horizon when it is named. Quarters past the months are not planned yet.</p></div>
<div class="card"><table><thead><tr><th>Step</th><th class="n">Periods</th><th>Window</th></tr></thead><tbody>
{% for s in steps %}<tr><td>{{ s.step_label }}</td><td class="n">{{ s.horizon_periods }}</td><td class="small">{{ s.says }}</td></tr>{% endfor %}</tbody></table>
<p class="hint">A step may plan a shorter window than the version, never a longer one: it plans the lesser of the two.</p></div></div>
<h2>Acts<span class="count">every close, reopen and change of horizon, newest first — the register the states and horizons above are read from · <a href="{{ url_for('plan.change_history') }}">change history</a></span></h2>
<table><thead><tr><th>When</th><th>Version</th><th>Act</th><th>By</th><th>Why</th></tr></thead><tbody>
{% for a in acts %}<tr><td class="small">{{ (a.entered_on or '')[:16].replace('T', ' ') }}</td><td>{{ a.version_id }}</td><td>{{ a.act }}{% if a.act == 'horizon' %} to {{ a.horizon_periods }} periods{% endif %}</td><td class="small">{{ a.entered_by }}</td><td class="small">{{ a.reason or '' }}</td></tr>
{% else %}<tr><td colspan="5" class="muted">No version has been closed or reopened.</td></tr>{% endfor %}
{% for w in waiting %}<tr><td class="small">{{ w.entered_on[:16].replace('T', ' ') }}</td><td>{{ w.version_id }}</td><td>{{ w.act }} <span class="small muted">placed, waiting for the run</span></td><td class="small">{{ w.entered_by }}</td><td class="small">{{ w.reason }}</td></tr>{% endfor %}</tbody></table>"""


def register(bp, page, who_fn, busy, session, roles, run_plan, scoped: dict) -> None:
    from . import reads
    import csv
    scoped["versions"] = {"commands": RUN, "pending": LANDING.pending, "what": "version state",
                          "says": "run completed — the version's state is the act just taken"}
    scoped["version_horizon"] = {"commands": HORIZON_RUN, "pending": LANDING.pending, "what": "version horizon",
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
            return page(PAGE, title="Versions", active="versions", versions=reads.versions(), acts=q("select * from plan.version_act order by entered_on desc, act_id desc"),
                        waiting=_waiting(), kinds=reads.version_kinds(), steps=reads.step_horizons(), may=roles.may(who, VERB), holders=reads.holders(VERB),
                        may_horizon=roles.may(who, HORIZON_VERB), last=session.last, receipt_acts=("version.",))
        except Busy as e:
            return busy("Versions", e)

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
