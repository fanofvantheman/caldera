"""Rights and roles under Admin (DEC-20261114-04): the rights the plan has, read by group or by class of right; the roles,
the shipped set and the client's own side by side, with who holds each, where and for which kind of plan; and composing a
role of the client's own from the rights.

A right is a verb of the register `dims.ref_verb` — closed: a role grants only these, and every audit is written on them,
so a composed role is held to the same rules as a shipped one. A role is a named set of rights of any size. The node a
right is held at and the kind of plan are on the assignment, never on the right. Composing is set-up, by the holder of
`register.roles.maintain`; it grants nothing until someone is assigned the role, which is not done here. Registered on
the plan's blueprint by `register(...)`, called from `face/__main__.py`."""
from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict

from chassis import receipts
from chassis.landing import LogLanding
from chassis.warehouse import Busy, q
from flask import redirect, request, url_for

from .words import said

VERB = "register.roles.maintain"
COLUMNS = ["role_code", "role_name", "description", "action", "composed_by", "composed_on"]
LANDING = LogLanding("plan", "reg_role", COLUMNS)
RUN = [["uv", "run", "python", "-m", "ingest.pipeline", "--only", "reg_role"],
       ["uv", "run", "sqlmesh", "plan", "prod", "--restate-model", "dims.ctl_role_definition+", "--restate-model", "dims.ctl_role_action+",
        "--auto-apply", "--no-prompts"]]
CLASS_SAID = {"enter": "enters", "maintain": "keeps", "decide": "decides", "read": "reads", "run": "runs"}
CLASS_ORDER = ["enter", "maintain", "decide", "run", "read"]

RIGHTS = """<h1>Rights<small>every right the plan has — what a role is made of; where it is held and for which kind of plan are on the assignment</small></h1>
<div class="toolbar"><span class="seg">{% for k, label in views %}{% if k == by %}<b>{{ label }}</b>{% else %}<a href="{{ url_for('plan.roles', by=k) }}">{{ label }}</a>{% endif %}{% endfor %}</span></div>
<p class="hint">A role is a named set of these, of any size. The list is closed: a role — ours or your own — grants nothing that is not on it, and every check on who may do what is written on the rights, so a role you compose is held to the same rules as the ones we ship.</p>
{% for g in groups %}<h2>{{ g.label }}<span class="count">{{ g.rights|length }}</span></h2>
<table><thead><tr><th>Right</th><th>{{ 'Class' if by == 'group' else 'Group' }}</th><th>Granted by</th><th class="n">Held by</th></tr></thead><tbody>
{% for r in g.rights %}<tr><td>{{ r.said }}<div class="small muted"><code>{{ r.verb }}</code></div></td><td class="small">{{ r.class_said if by == 'group' else r.verb_group }}</td>
<td class="small">{% for x in r.roles %}{{ x.role_name }}{% if x.own %} <span class="state">your own</span>{% endif %}{{ ', ' if not loop.last }}{% else %}<span class="muted">no role{% if r.verb == 'mapping.propose' %} — the mapping tool's first pass, held by no person{% endif %}</span>{% endfor %}</td>
<td class="n">{{ r.people or '' }}</td></tr>{% endfor %}</tbody></table>{% endfor %}"""

ROLES = """<h1>Roles<small>the set we ship, and your own beside it — each a named set of rights; held by a person at a node, for a kind of plan</small></h1>
<p class="hint">{{ n_shipped }} shipped, {{ n_own }} of your own.{% if may %} <a href="{{ url_for('plan.role_compose') }}">Compose a role</a> from the rights; composing grants nothing until someone is assigned it.{% endif %}</p>
<table><thead><tr><th>Role</th><th>Rights</th><th>Held by — where, for which plans</th>{% if may %}<th></th>{% endif %}</tr></thead><tbody>
{% for r in roles %}<tr><td><b>{{ r.role_name }}</b>{% if r.own %} <span class="state">your own</span>{% endif %}<div class="small muted">{{ r.description or '' }}</div>{% if r.own %}<div class="small muted">composed by {{ r.composed_by }}, {{ (r.composed_on or '')[:10] }}</div>{% endif %}</td>
<td class="small">{% for c in r.by_class %}<div><b>{{ c.label }}</b> {{ c.rights|join('; ') }}</div>{% endfor %}</td>
<td class="small">{% for h in r.holders %}<div>{{ h.principal }} · {{ h.scope_dimension }} {{ h.scope_node }} · {{ h.kind }}</div>{% else %}<span class="muted">nobody yet</span>{% endfor %}</td>
{% if may %}<td class="acts small">{% if r.own %}<a href="{{ url_for('plan.role_compose', role=r.role_code) }}">change…</a>{% endif %}</td>{% endif %}</tr>{% endfor %}</tbody></table>"""

COMPOSE = """<h1>Compose a role<small>a named set of the plan's rights — your own, beside the roles we ship, and held to the same checks</small></h1>
{% if not may %}<p class="lede">Roles are composed by {{ holders|join(', ') or 'nobody yet' }}.</p>{% else %}
<form method="post" action="{{ url_for('plan.role_compose_do') }}">
<div class="form-row"><label class="small">name <input name="role_name" required value="{{ role.role_name or '' }}" placeholder="Sales budget holder"></label>
<label class="small grow">what it is for <input name="description" value="{{ role.description or '' }}" placeholder="who holds it and what they stand behind"></label>{% if role.role_code %}<input type="hidden" name="role_code" value="{{ role.role_code }}">{% endif %}</div>
{% for g in groups %}<fieldset><legend>{{ g.label }}</legend>{% for r in g.rights %}<label class="small pick"><input type="checkbox" name="verb" value="{{ r.verb }}" {{ 'checked' if r.verb in chosen }}> {{ r.said }} <span class="muted">· {{ r.class_said }}</span></label>{% endfor %}</fieldset>{% endfor %}
<p><button class="primary" onclick="this.textContent='Composing…'">{{ 'Change the role' if role.role_code else 'Compose the role' }}</button> <span class="hint">it grants nothing until someone is assigned it; in force after the run that follows</span></p></form>{% endif %}
{% if last and last.act == 'role.compose' %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else ('!' if c.flag else '✕') }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}
<style>fieldset{border:1px solid var(--rule);margin:.6rem 0;padding:.4rem .8rem;display:grid;grid-template-columns:repeat(auto-fill,minmax(19rem,1fr));gap:.2rem .8rem}legend{font-weight:600}.pick{display:block}.form-row{display:flex;flex-wrap:wrap;gap:.8rem;align-items:end;margin:.6rem 0}.form-row .grow{flex:1;display:flex;flex-direction:column}.form-row label{display:flex;flex-direction:column;gap:.2rem}</style>"""


def rights() -> list[dict]:
    held = defaultdict(list)
    for r in q("""select a.action, d.role_code, d.role_name, d.own from dims.ctl_role_action a join dims.ctl_role_definition d using (role_code)
                  order by d.own, d.role_name"""):
        held[r["action"]].append(r)
    people = {r["action"]: r["n"] for r in q("select action, count(distinct principal) n from dims.effective_entitlements group by 1")}
    return [{**v, "said": said(v["verb"]), "class_said": CLASS_SAID.get(v["right_class"], v["right_class"]), "roles": held.get(v["verb"], []),
             "people": people.get(v["verb"], 0)} for v in q("select * from dims.ref_verb order by ord, verb")]


def grouped(rs: list[dict], by: str) -> list[dict]:
    out: dict[str, list] = {}
    if by == "class":
        for c in CLASS_ORDER:
            out[f"{CLASS_SAID[c].capitalize()} — {c}"] = [r for r in rs if r["right_class"] == c]
    else:
        for r in rs:
            out.setdefault(r["verb_group"], []).append(r)
    return [{"label": k, "rights": v} for k, v in out.items() if v]


def register(bp, page, who_fn, busy, session, roles, run_plan, scoped: dict) -> None:
    from . import reads
    scoped["roles"] = {"commands": RUN, "pending": LANDING.pending, "what": "roles",
                       "says": "run completed — the role is in the register; it grants nothing until someone is assigned it"}

    @bp.get("/roles", endpoint="roles")
    def roles_page():
        try:
            by = request.args.get("by") if request.args.get("by") in ("group", "class") else "group"
            return page(RIGHTS, title="Rights", active="roles_rights", by=by, views=[("group", "by group"), ("class", "by class of right")],
                        groups=grouped(rights(), by))
        except Busy as e:
            return busy("Rights", e)

    @bp.get("/roles/list")
    def roles_list():
        try:
            who = who_fn()
            defs = q("select * from dims.ctl_role_definition order by own, role_name")
            verbs = {v["verb"]: v for v in q("select * from dims.ref_verb")}
            acts = defaultdict(list)
            for r in q("select role_code, action from dims.ctl_role_action order by action"):
                acts[r["role_code"]].append(r["action"])
            holders = defaultdict(list)
            for h in q("""select principal, role_code, scope_dimension, scope_node, version_kind from dims.ctl_role_assignment
                          where valid_to is null or valid_to >= current_date order by principal"""):
                holders[h["role_code"]].append({**h, "kind": (h["version_kind"] or "").replace("_", " ") + " only" if h["version_kind"] else "every plan"})
            out = []
            for d in defs:
                by = defaultdict(list)
                for a in acts.get(d["role_code"], []):
                    by[(verbs.get(a) or {}).get("right_class", "?")].append(said(a).removeprefix("the right to "))
                out.append({**d, "holders": holders.get(d["role_code"], []),
                            "by_class": [{"label": CLASS_SAID.get(c, c).capitalize(), "rights": by[c]} for c in CLASS_ORDER if by.get(c)]})
            return page(ROLES, title="Roles", active="roles_roles", roles=out, may=roles.may(who, VERB),
                        n_shipped=sum(1 for d in defs if not d["own"]), n_own=sum(1 for d in defs if d["own"]))
        except Busy as e:
            return busy("Roles", e)

    @bp.get("/roles/compose")
    def role_compose():
        try:
            who = who_fn(); code = request.args.get("role") or ""
            role = (q("select * from dims.ctl_role_definition where role_code = ? and own", code) or [{}])[0] if code else {}
            chosen = {r["action"] for r in q("select action from dims.ctl_role_action where role_code = ?", role["role_code"])} if role else set()
            return page(COMPOSE, title="Compose a role", active="roles_compose", may=roles.may(who, VERB), holders=reads.holders(VERB),
                        groups=grouped(rights(), "group"), role=role, chosen=chosen, last=session.last, receipt_acts=("role.",))
        except Busy as e:
            return busy("Compose a role", e)

    @bp.post("/roles/compose")
    def role_compose_do():
        f = request.form; who = who_fn()
        name, desc = (f.get("role_name") or "").strip(), (f.get("description") or "").strip()
        chosen = sorted(set(f.getlist("verb")))
        code = f.get("role_code") or re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")
        known = {v["verb"] for v in q("select verb from dims.ref_verb")}
        shipped = {r["role_code"] for r in q("select role_code from dims.ctl_role_definition where not own")}
        named = {r["role_name"].lower(): r["role_code"] for r in q("select role_name, role_code from dims.ctl_role_definition")}
        unknown = [v for v in chosen if v not in known]
        may = roles.may(who, VERB)
        checks = [
            {"check": "who may compose", "ok": may, "says": f"{who} holds {said(VERB)}" if may else f"{who} does not hold {said(VERB)} — roles are composed by {', '.join(reads.holders(VERB)) or 'nobody yet'}"},
            {"check": "a name", "ok": bool(code), "says": f"{name} ({code})" if code else "a role is named"},
            {"check": "not one we ship", "ok": code not in shipped, "says": "your own" if code not in shipped else f"{code} is a role we ship — compose your own beside it, under another name"},
            {"check": "a name not taken", "ok": named.get(name.lower(), code) == code, "says": "no other role is called that" if named.get(name.lower(), code) == code else f"{named.get(name.lower())} is already called {name}"},
            {"check": "at least one right", "ok": bool(chosen), "says": f"{len(chosen)} right{'s' if len(chosen) != 1 else ''}" if chosen else "a role is a set of one right or more"},
            {"check": "rights the plan has", "ok": not unknown, "says": "every one on the list" if not unknown else f"{', '.join(unknown)} — not a right the plan has"},
        ]
        if any(re.fullmatch(r"layer\.[1-9]\.enter", v) for v in chosen) and "delta.supply.enter" in chosen:
            checks.append({"check": "the demand plan and the supply constraint", "ok": False, "flag": True,
                           "says": "one holder would both enter demand and enter the supply constraint — the constraint gets a back door into the demand signal; the plan's check will name whoever is assigned it"})
        placed = receipts.judge(checks)
        if placed:
            now = dt.datetime.now().isoformat(timespec="seconds")
            LANDING.place([{"role_code": code, "role_name": name, "description": desc, "action": v, "composed_by": who, "composed_on": now} for v in chosen], who)
        session.last = receipts.write("role.compose", who, code or name, checks, placed)
        if not placed:
            session.say("role not composed: " + "; ".join(c["says"] for c in checks if not c["ok"] and not c.get("flag")), False)
            return redirect(url_for("plan.role_compose", role=f.get("role_code") or None))
        if run_plan(who, "roles"):
            session.say(f"{name} composed — {len(chosen)} rights; it grants nothing until someone is assigned it", True)
            return redirect(url_for("plan.roles_list"))
        return redirect(url_for("plan.run"))
