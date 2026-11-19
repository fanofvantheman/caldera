"""Workflow per process (DEC-20261115-03 points 3–5): every step of the process at every node of the dimension it is
scoped on — nothing yet · open · submitted · accepted · sent back — with who holds it and since when, the step's due date
and whether it is late; and the acts: submit, reopen, accept, send back with a reason. It is the demand plan's submission
made general: the acts are rows of the same register (`plan/reg_submission`, subject `step:<step>`), read by
`plan.submission` and `plan.step_state`. A submitted or accepted node takes no entry until it is sent back or reopened;
nothing a model calculates waits on it.

The page is listed in each process (via), and shows that process's steps. Registered on the plan's blueprint by
`register(...)`, called once from `face/__main__.py`."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

from chassis import receipts
from chassis.warehouse import Busy, q
from flask import redirect, request, url_for

from .words import said

ACTS = {"submit": ("submit_verb", ("open", "sent_back", "nothing")), "reopen": (None, ("submitted", "accepted")),
        "accept": ("decide_verb", ("submitted",)), "send_back": ("decide_verb", ("submitted", "accepted"))}
DUE_VERB = "cycle.open"
STATE_SAYS = {"nothing": "nothing yet", "open": "open", "submitted": "submitted", "accepted": "accepted", "sent_back": "sent back"}
PROCESS_LABEL = {"ibp": "Integrated business planning", "finplan": "Financial planning", "strategic": "Strategic plan"}

PAGE = """<h1>Workflow<small>{{ process_label }} · {{ version|plan }} · each step at each node: nothing yet, open, submitted, accepted or sent back — who holds it, since when, and its due date</small></h1>
{% if not steps %}<p class="lede">{{ process_label }} has no steps with a workflow yet.</p>{% else %}
<div class="wfwrap"><table class="wf"><thead><tr><th class="sticky">{{ 'Cost centre' if org else 'Node' }}</th>{% for s in steps %}<th>{{ s.step_label }}{% if not s.built %} <span class="small muted">not built</span>{% endif %}
<div class="small muted">{% if s.due_on %}due {{ s.due_on }}{% if s.late %} · <b class="no">late</b>{% endif %}{% else %}no due date{% endif %}{% if s.n %} · {{ s.n_in }} of {{ s.n }} in{% endif %}</div></th>{% endfor %}</tr></thead><tbody>
{% for n in nodes %}<tr class="{{ 'grp' if not n.is_leaf }}"><td class="sticky" style="padding-left:{{ 0.4 + n.depth * 1.0 }}rem">{% if n.is_leaf %}{{ n.name }}{% else %}<b>{{ n.name }}</b>{% endif %} <span class="small muted">{{ n.code }}</span></td>
{% for s in steps %}{% set c = cells.get((s.step, n.code)) %}<td class="wfc {{ c.state if c }}">{% if c and (c.has_figures or c.acted_by) %}<span class="state {{ c.state }}">{{ says[c.state] }}</span>{% if not n.is_leaf and c.n_beneath %} <span class="small muted">{{ c.n_in }}/{{ c.n_beneath }} in</span>{% endif %}
{% if c.acted_by %}<div class="small muted">{{ c.acted_by }} · {{ c.acted_on }}{% if c.note %} — {{ c.note }}{% endif %}</div>{% endif %}
{% for a in c.acts %}<form class="inline" method="post" action="{{ url_for('plan.workflow_act') }}"><input type="hidden" name="step" value="{{ s.step }}"><input type="hidden" name="node" value="{{ n.code }}"><input type="hidden" name="act" value="{{ a }}">{% if a == 'send_back' %}<input name="note" size="10" required placeholder="why">{% endif %}<button class="act small">{{ a.replace('_', ' ') }}</button></form>{% endfor %}
{% elif c %}<span class="small muted">—</span>{% endif %}</td>{% endfor %}</tr>{% endfor %}</tbody></table></div>
<p class="hint">A node is open while it has figures and no one has submitted it. Submitting hands it over: it takes no entry until it is sent back (with a reason) or reopened. Accepting is the reviewer's; it too keeps the node closed to entry. Nothing a calculation reads waits on these states — the plan is calculated from what is entered, whatever its state. A node above a cost centre shows how many of the cost centres beneath it are in. Due dates are set on the process's plan administration page.</p>{% endif %}
{% if last and last.act and last.act.startswith('workflow') %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else ('!' if c.flag else '✕') }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}
<style>.wfwrap{overflow-x:auto}table.wf{font-size:.82rem}table.wf td.wfc{vertical-align:top;min-width:9rem}table.wf tr.grp td{background:var(--soft)}table.wf .sticky{position:sticky;left:0;background:var(--panel)}
table.wf tr.grp td.sticky{background:var(--soft)}.state.submitted,.state.accepted{font-weight:600}.state.sent_back{text-decoration:underline dotted}</style>"""


def steps_of(process: str) -> list[dict]:
    return q("select * from plan.ref_step where process = ? order by ord", process)


def state_at(version: str, step: str, nodes: list[str]) -> dict | None:
    """The first node of `nodes` (a cost centre, then its ancestors) whose step is handed over — submitted or accepted."""
    if not nodes:
        return None
    rows = {r["node"]: r for r in q(f"""select node, state, acted_by, acted_on from plan.step_state where version_id = ? and step = ?
                                        and node in ({','.join('?' * len(nodes))})""", version, step, *nodes)}
    return next((rows[n] for n in nodes if n in rows and rows[n]["state"] in ("submitted", "accepted")), None)


def ancestors(cc: str) -> list[str]:
    """A cost centre and every node above it, nearest first."""
    rows = q("select ancestor_code a, depth from dims.dim_organisation_hierarchy where descendant_code = ? order by depth", cc)
    return [r["a"] for r in rows] or [cc]


def locked(version: str, step: str, cc: str) -> str | None:
    """Why entry at a cost centre is refused because its step is handed over, or None."""
    s = state_at(version, step, ancestors(cc))
    if not s:
        return None
    return (f"{step} at {s['node']} is {STATE_SAYS[s['state']]} ({s['acted_by']}, {s['acted_on']}) — it takes no entry until it is sent back "
            "or reopened on the workflow page")


def register(bp, page, who_fn, ctx_fn, busy, session, roles, run_plan, scoped: dict, landing) -> None:
    from . import reads
    from . import costs
    scoped["workflow"] = {"what": "workflow",
                          "says": "run completed — the step's state is the act just taken"}

    def _process() -> str:
        p = request.args.get("via") or request.form.get("via") or "ibp"
        return p if p in PROCESS_LABEL else "ibp"

    def _verb(step: dict, act: str) -> list[str]:
        k = ACTS[act][0]
        return [step[k]] if k else [step["submit_verb"], step["decide_verb"]]

    @bp.get("/workflow")
    def workflow():
        try:
            who = who_fn(); proc = _process()
            version = ctx_fn().get("version") or reads.default_version()
            v = reads.version(version) or {}
            steps = steps_of(proc)
            rows = q("select * from plan.step_state where version_id = ? and process = ?", version, proc)
            org = any(s["dimension"] == "organisation" for s in steps)
            tree = costs.planning_cost_centres() if org else []
            names = {c["code"]: c for c in tree}
            units = {r["code"]: r["label"] for r in q("select planning_unit code, any_value(planning_unit_name) as \"label\" from dims.dim_account group by 1")}
            nodes, seen = [], set()
            for c in tree:
                nodes.append({"code": c["code"], "name": c["name"], "depth": c["depth"], "is_leaf": c["kind"] not in ("company", "function")}); seen.add(c["code"])
            for r in sorted(rows, key=lambda r: (r["node"] != "ALL", r["node"])):
                if r["node"] not in seen:
                    seen.add(r["node"])
                    nodes.append({"code": r["node"], "name": "the plan as a whole" if r["node"] == "ALL" else units.get(r["node"], r["node"]),
                                  "depth": 0 if r["node"] == "ALL" else 1, "is_leaf": r["node"] != "ALL"})
            if org:                         # the business-wide steps (revenue at the plan as a whole) sit on the company's row
                for r in rows:
                    if r["node"] == "ALL":
                        r["node"] = "CAL"
                nodes = [n for n in nodes if n["code"] != "ALL"]
            by_step = {s["step"]: s for s in steps}
            cells = {}
            for r in rows:
                s = by_step[r["step"]]
                node = "ALL" if r["node"] == "CAL" and s["dimension"] != "organisation" else r["node"]
                dim = s["dimension"] if s["dimension"] != "location" else "location"
                acts = [a for a, (_, fits) in ACTS.items() if r["state"] in fits and v.get("status") == "open" and s["built"]
                        and any(roles.may(who, x, node, dimension=dim, kind=v.get("version_kind")) for x in _verb(s, a))
                        and not (a == "submit" and not r["has_figures"])]
                cells[(r["step"], r["node"])] = {**r, "acts": acts}
            today = dt.date.today().isoformat()
            for s in steps:
                mine = [r for r in rows if r["step"] == s["step"] and r["is_leaf"] and r["has_figures"]]
                s["n"], s["n_in"] = len(mine), sum(1 for r in mine if r["state"] in ("submitted", "accepted"))
                s["due_on"] = next((str(r["due_on"]) for r in rows if r["step"] == s["step"] and r["due_on"]), None)
                s["late"] = bool(s["due_on"] and s["due_on"] < today and s["n_in"] < s["n"])
            return page(PAGE, title="Workflow", active="workflow", version=version, process_label=PROCESS_LABEL[proc], steps=steps, nodes=nodes,
                        cells=cells, org=org, says=STATE_SAYS, last=session.last, receipt_acts=("workflow",))
        except Busy as e:
            return busy("Workflow", e)

    @bp.post("/workflow/act")
    def workflow_act():
        f = request.form; who = who_fn()
        version = ctx_fn().get("version") or reads.default_version()
        v = reads.version(version) or {}
        step = next((s for s in q("select * from plan.ref_step where step = ?", f.get("step", ""))), None)
        act, node, note = f.get("act", ""), f.get("node", ""), (f.get("note") or "").strip()
        if step and step["dimension"] != "organisation" and node == "CAL":
            node = "ALL"
        st = (q("select * from plan.step_state where version_id = ? and step = ? and node = ?", version, step["step"], node) or [None])[0] if step else None
        verbs = _verb(step, act) if step and act in ACTS else []
        holds = any(roles.may(who, x, node, dimension=step["dimension"], kind=v.get("version_kind")) for x in verbs) if step else False
        checks = [
            {"check": "a step and an act", "ok": bool(step) and act in ACTS and bool(step and step["built"]),
             "says": f"{act.replace('_', ' ')} {step['step_label']}" if step and act in ACTS else f"{f.get('step')} · {act} is not a step and act the workflow has"},
            {"check": "version open", "ok": v.get("status") == "open", "says": f"{version} is {v.get('status', 'unknown')}"},
            {"check": "who holds the right here", "ok": holds,
             "says": f"{who} holds {' or '.join(said(x) for x in verbs)} at {node}" if holds else f"{who} does not hold {' or '.join(said(x) for x in verbs) or 'the right'} at {node}"},
            {"check": "the act fits the state", "ok": bool(st) and act in ACTS and st["state"] in ACTS[act][1],
             "says": f"{step['step_label'] if step else '?'} at {node} is {STATE_SAYS.get(st['state'], st['state']) if st else 'unknown'}"},
            {"check": "a reason to send it back", "ok": act != "send_back" or bool(note), "says": note or ("sending back says why" if act == "send_back" else "not needed")},
        ]
        placed = receipts.judge(checks)
        sid = f"SB-W-{dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
        if placed:
            landing.place([{"submission_id": sid, "action": act, "version_id": version, "subject": step["subject"], "scope_node": node, "submitted_by": who,
                            "submitted_on": dt.date.today().isoformat(), "note": note, "due_on": ""}], who)
        session.last = receipts.write(f"workflow.{act}", who, f"{f.get('step')}@{node}", checks, placed)
        nxt = f.get("next") or ""
        back = nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("plan.workflow", via=_process())
        if not placed:
            session.say(f"{act.replace('_', ' ')} refused: " + "; ".join(c["says"] for c in checks if not c["ok"]), False)
            return redirect(back)
        if run_plan(who, "workflow"):
            session.say(f"{step['step_label']} at {node}: {STATE_SAYS[{'submit': 'submitted', 'accept': 'accepted', 'send_back': 'sent_back', 'reopen': 'open'}[act]]}", True)
            return redirect(back)
        return redirect(url_for("plan.run"))

    @bp.post("/workflow/due")
    def workflow_due():
        """A step's due date on a version — set on the process's administration page by a holder of the cycle's right."""
        f = request.form; who = who_fn()
        version = f.get("version") or ctx_fn().get("version")
        step = next((s for s in q("select * from plan.ref_step where step = ?", f.get("step", ""))), None)
        due = (f.get("due_on") or "").strip()
        try:
            ok_date = bool(dt.date.fromisoformat(due))
        except ValueError:
            ok_date = False
        holds = roles.may(who, DUE_VERB)
        checks = [{"check": "a step", "ok": bool(step), "says": step["step_label"] if step else f"{f.get('step')} is not a step"},
                  {"check": "who sets the cycle", "ok": holds, "says": f"{who} holds {said(DUE_VERB)}" if holds else f"{who} does not hold {said(DUE_VERB)}"},
                  {"check": "a date", "ok": ok_date, "says": due or "no date"}]
        placed = receipts.judge(checks)
        sid = f"SB-D-{dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
        if placed:
            landing.place([{"submission_id": sid, "action": "due", "version_id": version, "subject": step["subject"], "scope_node": "ALL", "submitted_by": who,
                            "submitted_on": dt.date.today().isoformat(), "note": "", "due_on": due}], who)
        session.last = receipts.write("workflow.due", who, f"{f.get('step')}@{version}", checks, placed)
        back = url_for("plan.versions", via=_process())
        if not placed:
            session.say("due date refused: " + "; ".join(c["says"] for c in checks if not c["ok"]), False)
            return redirect(back)
        if run_plan(who, "workflow"):
            session.say(f"{step['step_label']} due {due} on {version}", True)
        return redirect(back)
