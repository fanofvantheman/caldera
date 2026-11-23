"""Ownership under Admin (DEC-20261124-06): the table of planning facts against roles — who owns each fact (enters it and
sends it; exactly one role), who receives it once published — and the order that follows from the facts: what each uses,
what it is only reconciled with, and so which role waits on which.

The facts and their relations are declared (dims.ref_fact, dims.ref_fact_relation); the table is a register
(plan/reg_fact_role, read as dims.fact_role) the holder of the right to keep roles sets here. A right a fact names is
held through this table and nowhere else. Registered on the plan's blueprint by `register(...)`, called from
`face/__main__.py`."""
from __future__ import annotations

import datetime as dt

from chassis import receipts
from chassis.landing import LogLanding
from chassis.warehouse import Busy, q
from flask import redirect, request, url_for

from . import figures
from .words import said

VERB = "register.roles.maintain"
COLUMNS = ["fact", "role_code", "cell", "set_by", "set_on"]
LANDING = LogLanding("plan", "reg_fact_role", COLUMNS)
CELLS = (("", "—"), ("owns", "owns"), ("receives", "receives"))

PAGE = figures.SAVE_BAR + """<h1>Ownership<small>each planning fact · the one role that owns it · who receives it · what it waits on</small></h1>
<p class="hint">A fact has <b>exactly one owner</b>: the role that enters it and sends it. A role <b>receives</b> a fact once it is published. A role whose own fact uses another receives that one without a cell saying so — shown as <i>uses it</i>. Nothing here is built in: change a cell and save.{% if may %} A role is made on <a href="{{ url_for('plan.role_compose') }}">Compose a role</a> — a name is enough.{% else %} The table is set by {{ holders|join(', ') or 'nobody yet' }}.{% endif %}</p>
<div class="toolbar"><span class="seg"><span class="small muted">roles shown</span>{% if all_roles %}<a href="{{ url_for('plan.ownership') }}">those with a cell</a><b>every role</b>{% else %}<b>those with a cell</b><a href="{{ url_for('plan.ownership', roles='all') }}">every role</a>{% endif %}</span></div>
<form method="post" action="{{ url_for('plan.ownership_set') }}">{% if all_roles %}<input type="hidden" name="roles" value="all">{% endif %}
<div class="finwrap"><table class="own"><thead><tr><th>Planning fact</th>{% for r in roles %}<th>{{ r.role_name }}<div class="small muted">{{ r.held or 'held by nobody' }}</div></th>{% endfor %}</tr></thead><tbody>
{% for f in facts %}<tr><td><b>{{ f.fact_name }}</b><div class="small muted">{{ f.kind_says }} · {{ f.grain }}{% if f.right_verb %} · the app's right follows this row{% endif %}</div></td>
{% for r in roles %}{% set c = cells.get((f.fact, r.role_code), '') %}<td class="{{ c }}">{% if may %}<select class="cell" name="c|{{ f.fact }}|{{ r.role_code }}">{% for v, lab in options %}<option value="{{ v }}" {{ 'selected' if v == c }}>{{ lab }}</option>{% endfor %}</select>{% else %}{{ c or '' }}{% endif %}{% if not c and (f.fact, r.role_code) in implied %}<div class="small muted"><i>uses it</i></div>{% endif %}</td>{% endfor %}</tr>{% endfor %}
</tbody></table></div>
{% if may %}{{ save_bar(discard='reset', note='saved by ' ~ who ~ ' · a fact keeps exactly one owner: to move one, set the new owner and clear the old in the same save') }}{% endif %}</form>

<h2 id="order">The order<span class="count">it is on the facts; a role waits only through the facts it owns</span></h2>
<p class="hint">A fact that <b>uses</b> another is calculated from it and waits for it, or works from what was last published. A <b>standing</b> fact is set on its own, when its own event happens, and every plan uses what stands. Two facts <b>reconciled</b> are each set on their own and compared: neither waits, and a difference is an alert to both owners.</p>
<table><thead><tr><th>Planning fact</th><th>Owner</th><th>Uses — waits on</th><th>Used by</th><th>Reconciled with — alerts, never waits</th></tr></thead><tbody>
{% for f in facts %}<tr><td><b>{{ f.fact_name }}</b><div class="small muted">{{ f.kind_says }}</div></td><td>{{ f.owner or '—' }}</td>
<td class="small">{% for x in f.uses %}{{ x.name }} <span class="muted">({{ x.owner or 'no owner' }})</span>{{ '; ' if not loop.last }}{% else %}<span class="muted">nothing — set on its own</span>{% endfor %}</td>
<td class="small">{% for x in f.used_by %}{{ x.name }} <span class="muted">({{ x.owner or 'no owner' }})</span>{{ '; ' if not loop.last }}{% endfor %}</td>
<td class="small">{% for x in f.reconciled %}{{ x.name }} <span class="muted">({{ x.owner or 'no owner' }})</span>{{ '; ' if not loop.last }}{% endfor %}</td></tr>{% endfor %}
</tbody></table>

<h2 id="roles">By role<span class="count">what each owns, and whose facts it waits on</span></h2>
<table><thead><tr><th>Role</th><th>Owns</th><th>Waits on</th><th>Is waited on by</th></tr></thead><tbody>
{% for r in by_role %}<tr><td><b>{{ r.role_name }}</b><div class="small muted">{{ r.held or 'held by nobody' }}</div></td><td class="small">{{ r.owns|join('; ') }}</td>
<td class="small">{% for o, fs in r.waits_on.items() %}{{ o }} <span class="muted">({{ fs|join(', ') }})</span>{{ '; ' if not loop.last }}{% else %}<span class="muted">nobody</span>{% endfor %}</td>
<td class="small">{% for o, fs in r.waited_by.items() %}{{ o }} <span class="muted">({{ fs|join(', ') }})</span>{{ '; ' if not loop.last }}{% else %}<span class="muted">nobody</span>{% endfor %}</td></tr>{% endfor %}
</tbody></table>
{% if last %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else '✕' }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}
<style>.finwrap{overflow-x:auto;margin-bottom:.6rem}table.own th{vertical-align:bottom;min-width:7.5rem}table.own td.owns{box-shadow:inset 0 0 0 1px var(--ink)}table.own select.cell{font:inherit;font-size:.85rem;background:transparent;color:inherit;border:0}table.own td.owns select.cell{font-weight:700}</style>
<script>(function(){var f=document.querySelector('form[action$="/ownership/set"]');if(!f)return;[].forEach.call(f.querySelectorAll('select.cell'),function(s){s.setAttribute('data-was',s.value);});
f.addEventListener('change',function(e){if(!e.target.matches('select.cell'))return;var n=0;[].forEach.call(f.querySelectorAll('select.cell'),function(s){if(s.value!==s.getAttribute('data-was'))n++;s.closest('td').className=s.value;});
var b=f.querySelector('.savebar'),c=b&&b.querySelector('.savecount');if(c){c.textContent=n?n+' cell'+(n==1?'':'s')+' changed and not saved':'nothing changed';b.classList.toggle('dirty',n>0);}});
f.addEventListener('click',function(e){if(e.target.closest('[data-discard="reset"]'))[].forEach.call(f.querySelectorAll('select.cell'),function(s){s.value=s.getAttribute('data-was');s.closest('td').className=s.value;});});})();</script>"""


def table() -> dict:
    """The facts, the roles, the cells standing and what follows from the facts' relations."""
    facts = q("select * from dims.ref_fact order by ord")
    names = {f["fact"]: f["fact_name"] for f in facts}
    roles = q("select role_code, role_name from dims.ctl_role_definition order by role_name")
    held: dict = {}
    for r in q("select distinct role_code, principal from dims.ctl_role_assignment where valid_to is null or valid_to >= current_date order by 2"):
        held.setdefault(r["role_code"], []).append(r["principal"].split("@")[0])
    cells = {(r["fact"], r["role_code"]): r["cell"] for r in q("select fact, role_code, cell from dims.fact_role")}
    rname = {r["role_code"]: r["role_name"] for r in roles}
    owner = {f: rc for (f, rc), c in cells.items() if c == "owns"}
    rel = q("select fact, relation, other_fact from dims.ref_fact_relation")
    uses = [(r["fact"], r["other_fact"]) for r in rel if r["relation"] == "uses"]
    rec = [(r["fact"], r["other_fact"]) for r in rel if r["relation"] == "reconciled_with"]
    implied = {(o, owner[f]) for f, o in uses if f in owner and owner.get(o) != owner[f]}    # a role whose fact uses another receives it
    tag = lambda x: {"name": names.get(x, x), "owner": rname.get(owner.get(x))}
    for f in facts:
        k = f["fact"]
        f["kind_says"] = "calculated in the cycle" if f["kind"] == "calculated" else "standing — set on its own, dated"
        f["owner"] = rname.get(owner.get(k))
        f["uses"] = [tag(o) for x, o in uses if x == k]
        f["used_by"] = [tag(x) for x, o in uses if o == k]
        f["reconciled"] = [tag(o) for x, o in rec if x == k] + [tag(x) for x, o in rec if o == k]
    by_role = []
    for rc in sorted({v for v in owner.values()}, key=lambda x: rname.get(x, x)):
        waits, waited = {}, {}
        for f, o in uses:
            if owner.get(f) == rc and owner.get(o) and owner[o] != rc:
                waits.setdefault(rname[owner[o]], []).append(names[o])
            if owner.get(o) == rc and owner.get(f) and owner[f] != rc:
                waited.setdefault(rname[owner[f]], []).append(names[o])
        by_role.append({"role_name": rname.get(rc, rc), "held": ", ".join(held.get(rc, [])), "owns": [names[f] for f in names if owner.get(f) == rc],
                        "waits_on": {k: sorted(set(v)) for k, v in waits.items()}, "waited_by": {k: sorted(set(v)) for k, v in waited.items()}})
    for r in roles:
        r["held"] = ", ".join(held.get(r["role_code"], []))
    return {"facts": facts, "roles": roles, "cells": cells, "implied": implied, "by_role": by_role, "names": names, "rname": rname}


def register(bp, page, who_fn, busy, session, roles, run_plan, scoped: dict) -> None:
    from . import reads
    scoped["ownership"] = {"what": "ownership", "says": "run completed — the table stands; the rights that follow a fact are its owner's"}

    @bp.get("/ownership")
    def ownership():
        try:
            who = who_fn(); t = table()
            every = request.args.get("roles") == "all"
            used = {rc for (_, rc) in t["cells"]}
            shown = [r for r in t["roles"] if every or r["role_code"] in used]
            return page(PAGE, title="Ownership", active="ownership", may=roles.may(who, VERB), holders=reads.holders(VERB), all_roles=every,
                        facts=t["facts"], roles=shown, cells=t["cells"], implied=t["implied"], by_role=t["by_role"], options=CELLS,
                        last=session.last, receipt_acts=("ownership.",))
        except Busy as e:
            return busy("Ownership", e)

    @bp.post("/ownership/set")
    def ownership_set():
        f = request.form; who = who_fn(); t = table()
        now_ = dict(t["cells"])
        posted = {}
        for name, v in f.items():
            tag, _, rest = name.partition("|")
            fact, _, rc = rest.partition("|")
            if tag == "c" and fact in t["names"] and rc in t["rname"] and v in ("", "owns", "receives"):
                posted[(fact, rc)] = v
        changed = {k: v for k, v in posted.items() if v != now_.get(k, "")}
        after = {**now_, **changed}
        wrong = []
        for fact, nm in t["names"].items():
            owners = [t["rname"][rc] for (x, rc), c in after.items() if x == fact and c == "owns"]
            if len(owners) != 1:
                wrong.append(f"{nm}: {'no owner' if not owners else ' and '.join(owners)}")
        may = roles.may(who, VERB)
        says = "; ".join(f"{t['names'][fa]} — {t['rname'][rc]}: {v or 'cleared'}" for (fa, rc), v in sorted(changed.items()))
        checks = [
            {"check": "who may set the table", "ok": may, "says": f"{who} holds {said(VERB)}" if may else f"{who} does not hold {said(VERB)} — the table is set by {', '.join(reads.holders(VERB)) or 'nobody yet'}"},
            {"check": "a cell changed", "ok": bool(changed), "says": says or "no cell differs from the table standing"},
            {"check": "exactly one owner a fact", "ok": not wrong, "says": "every fact has one" if not wrong else "; ".join(wrong) + " — a fact has exactly one owner"},
        ]
        placed = receipts.judge(checks)
        if placed:
            at = dt.datetime.now().isoformat(timespec="seconds")
            LANDING.place([{"fact": fa, "role_code": rc, "cell": v, "set_by": who, "set_on": at} for (fa, rc), v in sorted(changed.items())], who)
        session.last = receipts.write("ownership.set", who, f"{len(changed)} cells", checks, placed)
        back = url_for("plan.ownership", roles=f.get("roles") or None)
        if not placed:
            session.say("not saved: " + "; ".join(c["says"] for c in checks if not c["ok"]), False)
            return redirect(back)
        if run_plan(who, "ownership"):
            session.say(f"{len(changed)} cell{'s' if len(changed) != 1 else ''} saved — {says}", True)
            return redirect(back)
        return redirect(url_for("plan.run"))
