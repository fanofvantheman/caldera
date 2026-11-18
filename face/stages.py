"""Stages (DEC-20261118-04): a Plan is worked in eight stages, each handed over by its owner — demand, demand valuation,
inventory, production, materials, cost, Finance's forecast, statements. Within an open Plan each stage is open, handed
over or behind; a stage reads the last handed-over state of the stage before it, never its latest release; a handover is
an act, never a side effect of a run. A deployment may compress adjacent stages into one (a set-up setting on this page).

The handover takes the figures the stage after reads, where this build reads across that seam by a handover: demand
valuation → inventory (the demand plan's cases by stocking node × material × week) and production → materials (cases to
make by material × plant × period). Every other seam reads the stage before as it stands, and the page says so.

How soon one person's released figures must show for another is not settled (point 7) and nothing here assumes it.

Registered on the plan's blueprint by `register(...)`, called once from `face/__main__.py`."""
from __future__ import annotations

import datetime as dt

from chassis import CONFIG, receipts
from chassis.landing import LogLanding
from chassis.warehouse import Busy, q
from flask import redirect, request, url_for

from .words import said

ACT_COLUMNS = ["act_id", "version_id", "stage", "action", "reason", "snapshot", "entered_by", "entered_at"]
ACTS = LogLanding("plan", "reg_stage_act", ACT_COLUMNS)
SETTING_COLUMNS = ["stage", "kept", "reason", "entered_by", "entered_at"]
SETTINGS = LogLanding("plan", "reg_stage_setting", SETTING_COLUMNS)
SNAP_DEMAND = LogLanding("plan", "reg_stage_snap_demand", ["act_id", "version_id", "node_code", "material_code", "week_id", "cases"])
SNAP_PRODUCTION = LogLanding("plan", "reg_stage_snap_production", ["act_id", "version_id", "material_code", "plant_code", "period", "quantity"])
SETTING_VERB = "version.name"
# the seams read by a handover, and what the handover takes: the stage that hands over → (what it takes, its landing, its query)
SEAMS = {
    "valuation": ("the demand plan's cases by stocking node × material × week", SNAP_DEMAND,
                  """select n.node_code, d.material_code, d.week_id, sum(d.cases) cases from plan.unconstrained_demand d
                     join dims.ref_serving_node n using (ship_to_code) where d.version_id = ? group by all"""),
    "production": ("cases to make by material × plant × period", SNAP_PRODUCTION,
                   "select material_code, plant_code, period, quantity from plan.production_requirement where version_id = ?"),
}

PAGE = """<h1>Stages<small>{{ version }} · eight handovers between owners, in order — each stage reads what the stage before handed over, never its latest figures</small></h1>
<p class="hint">A stage proposes its figures from what was handed to it; its owner may type over a proposal, with a reason, the proposal kept beside it; nothing reaches the next stage until the owner hands over — always an act, never a side effect of a run. A shortfall goes back: the stage before changes its plan and hands over again, and the stages after it read <b>behind</b> until their owners hand over in turn. {{ version }} is {{ plan_state }}.</p>
<table><thead><tr><th>#</th><th>Stage</th><th>Hands over</th><th>Owner</th><th>State</th><th>Last act</th><th>The stage after reads</th><th></th></tr></thead><tbody>
{% for s in stages %}<tr class="{{ 'off' if s.folded }}"><td>{{ s.ord }}</td><td><b>{{ s.stage_name }}</b></td><td class="small">{{ s.hands_over }}</td><td class="small">{{ s.owners|join(', ') or '—' }}</td>
<td>{% if s.folded %}<span class="small muted">one with {{ s.folded }} — handed over with it</span>{% else %}<span class="state {{ s.state|replace(' ', '-') }}">{{ s.state }}</span>{% endif %}</td>
<td class="small">{% if s.last_action %}{{ 'handed over' if s.last_action == 'hand_over' else 'reopened' }} {{ s.last_at[:16].replace('T', ' ') }} by {{ s.last_by }}{% if s.last_reason %} — {{ s.last_reason }}{% endif %}{% else %}—{% endif %}</td>
<td class="small">{{ s.reads }}</td>
<td>{% if s.may and is_open and not s.folded %}<form class="inline" method="post" action="{{ url_for('plan.stage_act') }}"><input type="hidden" name="stage" value="{{ s.stage }}">
<input name="reason" placeholder="{{ 'why reopen (required)' if s.state != 'open' else 'note' }}" size="12"> {% if s.state == 'open' or s.state == 'behind' %}<button class="act" name="action" value="hand_over">Hand over</button>{% endif %}{% if s.state != 'open' %} <button class="act" name="action" value="reopen">Reopen</button>{% endif %}</form>{% endif %}</td></tr>{% endfor %}</tbody></table>
<p class="hint">{{ waiting_says }} How soon one person's released figures must show for another is not settled; nothing here assumes a number. A handover is in force after the next run.</p>
<h2 id="setting">Handovers kept<span class="count">a set-up setting — adjacent stages may be compressed into one owner's work, never reordered</span></h2>
<table><thead><tr><th>After</th><th>Handover</th><th>Why</th><th>By</th></tr></thead><tbody>
{% for s in settings if s.ord < 8 %}<tr><td>{{ s.stage_name }}</td><td>{{ 'kept' if s.handover_kept else 'compressed — runs straight through into the next' }}</td><td class="small">{{ s.reason or 'the default: the eight, separate' }}</td><td class="small">{{ s.entered_by or '' }}</td></tr>{% endfor %}</tbody></table>
{% if may_set %}<form class="entry" method="post" action="{{ url_for('plan.stage_setting') }}">
<label>after<select name="stage">{% for s in settings if s.ord < 8 %}<option value="{{ s.stage }}">{{ s.stage_name }}</option>{% endfor %}</select></label>
<label>handover<select name="kept"><option value="false">compress into the next</option><option value="true">keep</option></select></label>
<label class="wide">why<input name="reason" required placeholder="one person now owns both"></label>
<div class="actions"><button class="primary">Set</button><span class="hint">applies to every Plan, after the next run</span></div></form>{% endif %}
{% if last %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else ('!' if c.flag else '✕') }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}
<style>.state.behind{font-weight:600}.state.open{color:var(--muted)}</style>"""


def _waiting() -> int:
    """Files the face has placed that the warehouse has not yet taken in: a handover then would take figures a run has not made."""
    built = CONFIG.db.stat().st_mtime if CONFIG.db.exists() else 0
    return sum(1 for p in CONFIG.landing.rglob("*.csv") if p.stat().st_mtime > built)


def register(bp, page, who_fn, ctx_fn, busy, session, roles) -> None:
    from . import reads

    def version_of() -> str:
        return ctx_fn().get("version") or reads.default_version()

    @bp.get("/stages")
    def stages():
        try:
            who = who_fn(); version = version_of(); v = reads.version(version) or {}
            ref = {r["stage"]: r for r in q("select * from dims.ref_stage order by ord")}
            rows = q("select * from plan.stage_state where version_id = ? order by ord", version)
            names = {r["stage"]: r["stage_name"] for r in ref.values()}
            out = []
            for r in rows:
                s = ref[r["stage"]]
                last_of_unit = r["ord"] == r["unit_to"]
                nxt = next((x for x in ref.values() if x["ord"] == r["ord"] + 1), None)
                if not r["handover_kept"] and nxt:
                    reads_as = f"{nxt['stage_name']} runs straight through from it"
                elif r["stage"] in SEAMS and nxt:
                    reads_as = (f"{nxt['stage_name']} reads {SEAMS[r['stage']][0]} as handed over" if r["snapshot"]
                                else f"{nxt['stage_name']} reads it as it stands — this handover took no figures; it will at the next")
                elif nxt:
                    reads_as = f"{nxt['stage_name']} reads it as it stands — this build does not yet read across this seam by a handover"
                else:
                    reads_as = "—"
                unit_last = next((x for x in rows if x["ord"] == r["unit_to"]), r)
                out.append({**r, **s, "state": unit_last["state"], "owners": reads.holders(s["verb"]), "reads": reads_as,
                            "folded": None if last_of_unit else names.get(unit_last["stage"]), "may": roles.may(who, s["verb"])})
            n = _waiting()
            return page(PAGE, title="Stages", active="stages", width="none", version=version, stages=out, is_open=v.get("status") == "open",
                        plan_state=v.get("status", "unknown"), settings=q("select * from plan.stage_setting order by ord"),
                        may_set=roles.may(who, SETTING_VERB),
                        waiting_says=f"{n} file{'s' if n != 1 else ''} placed and not yet taken in by a run — a stage reading across a handover is handed over after it." if n else "",
                        last=session.last, receipt_acts=("stage",))
        except Busy as e:
            return busy("Stages", e)

    @bp.post("/stages/act")
    def stage_act():
        f = request.form; who = who_fn(); version = version_of(); v = reads.version(version) or {}
        stage, action, reason = f.get("stage") or "", f.get("action") or "", (f.get("reason") or "").strip()
        ref = (q("select * from dims.ref_stage where stage = ?", stage) or [None])[0]
        st = (q("select * from plan.stage_state where version_id = ? and stage = ?", version, stage) or [None])[0]
        may = bool(ref) and roles.may(who, ref["verb"])
        waiting = _waiting()
        seam = SEAMS.get(stage) if st and st["handover_kept"] else None
        checks = [
            {"check": "a stage", "ok": bool(ref and st), "says": ref["stage_name"] if ref else f"{stage or 'nothing'} is not a stage"},
            {"check": "who hands it over", "ok": may, "says": (f"{who} holds {said(ref['verb'])}" if may else f"{who} does not hold {said(ref['verb'])} — {ref['stage_name']} is handed over by {', '.join(reads.holders(ref['verb'])) or 'nobody yet'}") if ref else "—"},
            {"check": "the plan is open", "ok": v.get("status") == "open", "says": f"{version} is {v.get('status', 'unknown')}"},
            {"check": "the stage hands over", "ok": bool(st) and st["ord"] == st["unit_to"],
             "says": "it ends its unit" if st and st["ord"] == st["unit_to"] else "a compressed stage is handed over with the stage it runs into"},
            {"check": "the act", "ok": action in ("hand_over", "reopen") and (action == "hand_over" or bool(reason)),
             "says": {"hand_over": "hand over", "reopen": f"reopen — {reason}" if reason else "a reopen says why"}.get(action, "hand over or reopen")},
            {"check": "the figures it hands over are made", "ok": not (seam and waiting),
             "says": f"{waiting} file{'s' if waiting != 1 else ''} not yet taken in by a run — run first, then hand over" if seam and waiting
                     else (f"takes {seam[0]}" if seam else "the stage after reads it as it stands")},
        ]
        placed = receipts.judge(checks)
        if placed:
            now = dt.datetime.now()
            act_id = f"STG-{now:%Y%m%d%H%M%S%f}"
            snap = ""
            if seam:                                   # the figures the stage after reads, as handed over (or as they stood at a reopen)
                _, landing, sql = seam
                rows = q(sql, version)
                if rows:
                    landing.place([{**r, "act_id": act_id, "version_id": version} for r in rows], who)
                    snap = f"{len(rows)} rows"
            ACTS.place([{"act_id": act_id, "version_id": version, "stage": stage, "action": action, "reason": reason, "snapshot": snap,
                         "entered_by": who, "entered_at": now.isoformat(timespec="seconds")}], who)
        session.last = receipts.write(f"stage.{action or 'act'}", who, f"{version}:{stage}", checks, placed)
        session.say(f"{ref['stage_name'] if ref else stage} {'handed over' if action == 'hand_over' else 'reopened'} — in force after the next run" if placed
                    else "refused: " + "; ".join(x["says"] for x in checks if not x["ok"]), placed)
        return redirect(url_for("plan.stages"))

    @bp.post("/stages/setting")
    def stage_setting():
        f = request.form; who = who_fn()
        stage, kept, reason = f.get("stage") or "", (f.get("kept") or "") == "true", (f.get("reason") or "").strip()
        ref = (q("select * from dims.ref_stage where stage = ?", stage) or [None])[0]
        may = roles.may(who, SETTING_VERB)
        checks = [
            {"check": "who keeps the setting", "ok": may, "says": f"{who} holds {said(SETTING_VERB)}" if may else f"{who} does not hold {said(SETTING_VERB)}"},
            {"check": "a handover between two stages", "ok": bool(ref) and ref["ord"] < 8, "says": f"after {ref['stage_name']}" if ref else f"{stage or 'nothing'} is not a stage"},
            {"check": "a reason", "ok": bool(reason), "says": reason or "a setting says why"},
        ]
        placed = receipts.judge(checks)
        if placed:
            SETTINGS.place([{"stage": stage, "kept": "true" if kept else "false", "reason": reason, "entered_by": who,
                             "entered_at": dt.datetime.now().isoformat(timespec="seconds")}], who)
        session.last = receipts.write("stage.setting", who, stage, checks, placed)
        session.say("set — after the next run" if placed else "refused: " + "; ".join(x["says"] for x in checks if not x["ok"]), placed)
        return redirect(url_for("plan.stages") + "#setting")
