"""Stages (DEC-20261118-04 point 1, DEC-20261119-01): a Plan is worked in eight stages — demand, demand valuation,
inventory, production, materials, cost, Finance's forecast, statements — in that order, each with its owner. A Plan has one
number for each figure: every stage reads the stage before it as it stands, and nothing is copied between stages. A
stage's state — open or handed over — records that its owner has put their work in the Plan; it gates nothing. A
deployment may compress adjacent stages into one (a set-up setting on this page).

Whether a stage is **behind** — not yet recalculated since an override or a port before it — follows from the
recalculation setting beside the compression (face/overrides.py): automatic recalculates at once and nothing is behind;
manual leaves the stages after an override behind until someone recalculates, here.

How soon one person's released figures must show for another is not settled (DEC-20261118-04 point 7) and nothing here
assumes it.

Registered on the plan's blueprint by `register(...)`, called once from `face/__main__.py`."""
from __future__ import annotations

import datetime as dt

from chassis import receipts
from chassis.landing import LogLanding
from chassis.warehouse import Busy, q
from flask import redirect, request, url_for

from . import overrides
from .words import said

ACT_COLUMNS = ["act_id", "version_id", "stage", "action", "reason", "entered_by", "entered_at"]
ACTS = LogLanding("plan", "reg_stage_act", ACT_COLUMNS)
SETTING_COLUMNS = ["stage", "kept", "reason", "entered_by", "entered_at"]
SETTINGS = LogLanding("plan", "reg_stage_setting", SETTING_COLUMNS)
SETTING_VERB = "version.name"

PAGE = """<h1>Stages<small>{{ version|plan }} · eight stages in order, each with its owner — one number for each figure: every stage reads the stage before it as it stands</small></h1>
<p class="hint">A stage calculates its figures from the stage before it; at the points the model declares, its owner may type over a calculated figure, with a reason, the calculated figure kept beside it. Work is done in a sandbox and ported into the Plan (<a href="{{ url_for('plan.port') }}">Port</a>), so one person's working moves no one else's. <b>Handed over</b> records that the owner has put their work in the Plan; it does not hold anything back from the next stage. A shortfall goes back: the stage before changes its plan. Recalculation after an override or a port is <b>{{ mode }}</b>{{ ': every stage after it recalculates at once' if mode == 'automatic' else ': the stages after it read behind until someone recalculates' }}. {{ version|plan }} is {{ plan_state }}.</p>
<table><thead><tr><th>#</th><th>Stage</th><th>Hands over</th><th>Owner</th><th>State</th><th>Last act</th><th>Recalculated</th><th></th></tr></thead><tbody>
{% for s in stages %}<tr class="{{ 'off' if s.folded }}"><td>{{ s.ord }}</td><td><b>{{ s.stage_name }}</b></td><td class="small">{{ s.hands_over }}</td><td class="small">{{ s.owners|join(', ') or '—' }}</td>
<td>{% if s.folded %}<span class="small muted">one with {{ s.folded }} — handed over with it</span>{% else %}<span class="state {{ s.state|replace(' ', '-') }}">{{ s.state }}</span>{% endif %}</td>
<td class="small">{% if s.last_action %}{{ 'handed over' if s.last_action == 'hand_over' else 'reopened' }} {{ s.last_at[:16].replace('T', ' ') }} by {{ s.last_by }}{% if s.last_reason %} — {{ s.last_reason }}{% endif %}{% else %}—{% endif %}</td>
<td class="small">{% if s.recalc == 'behind' %}<span class="state behind">behind</span> <span class="muted">— not yet recalculated since an override before it</span>{% elif s.recalc %}<span class="state">{{ s.recalc }}</span> <span class="muted">— placed, not yet run</span>{% else %}<span class="muted">yes</span>{% endif %}</td>
<td>{% if s.may and is_open and not s.folded %}<form class="inline" method="post" action="{{ url_for('plan.stage_act') }}"><input type="hidden" name="stage" value="{{ s.stage }}">
<input name="reason" placeholder="{{ 'why reopen (required)' if s.state != 'open' else 'note' }}" size="12"> {% if s.state == 'open' %}<button class="act" name="action" value="hand_over">Hand over</button>{% else %}<button class="act" name="action" value="reopen">Reopen</button>{% endif %}</form>{% endif %}</td></tr>{% endfor %}</tbody></table>
{% if any_behind %}<p>{% if may_run %}<form class="inline" method="post" action="{{ url_for('plan.recalculate') }}"><button class="primary" onclick="this.textContent='Recalculating…'">Recalculate</button></form> {% endif %}<span class="hint">{{ waiting_n }} override{{ 's' if waiting_n != 1 }} placed on {{ version|plan }} and not yet run{% if not may_run %} — recalculated by {{ run_holders }}{% endif %}.</span></p>{% endif %}
<p class="hint">How soon one person's released figures must show for another is not settled; nothing here assumes a number. A handover is in force after the next run.</p>
<h2 id="setting">Recalculation<span class="count">a set-up setting, for every Plan — after an override or a port, the models after it recalculate at once, or are marked behind until asked</span></h2>
<p>Recalculation is <b>{{ mode }}</b>{% if recalc.entered_by %} <span class="small muted">— set by {{ recalc.entered_by }}, {{ (recalc.entered_at or '')[:16].replace('T', ' ') }}: {{ recalc.reason }}</span>{% else %} <span class="small muted">— the default: a monthly cycle has no point recalculating the stages after one still being adjusted</span>{% endif %}</p>
{% if may_set %}<form class="entry" method="post" action="{{ url_for('plan.recalc_setting') }}">
<label>recalculation<select name="mode"><option value="automatic" {{ 'selected' if mode == 'manual' }}>automatic — at once, after every override and port</option><option value="manual" {{ 'selected' if mode == 'automatic' }}>manual — the stages after it behind until asked</option></select></label>
<label class="wide">why<input name="reason" required placeholder="a weekly tactical cycle"></label>
<div class="actions"><button class="primary">Set</button><span class="hint">applies to every Plan</span></div></form>{% endif %}
<h2>Handovers kept<span class="count">a set-up setting — adjacent stages may be compressed into one owner's work, never reordered</span></h2>
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
            recalc = overrides.behind(version) if overrides.mode() == "manual" else {}
            out = []
            for r in rows:
                s = ref[r["stage"]]
                last_of_unit = r["ord"] == r["unit_to"]
                unit_last = next((x for x in rows if x["ord"] == r["unit_to"]), r)
                out.append({**r, **s, "state": unit_last["state"], "owners": reads.holders(s["verb"]), "recalc": recalc.get(r["stage"], ""),
                            "folded": None if last_of_unit else names.get(unit_last["stage"]), "may": roles.may(who, s["verb"])})
            setting = (q("select * from plan.recalc_setting") or [{}])[0]
            return page(PAGE, title="Stages", active="stages", width="none", version=version, stages=out, is_open=v.get("status") == "open",
                        plan_state=v.get("status", "unknown"), settings=q("select * from plan.stage_setting order by ord"),
                        may_set=roles.may(who, SETTING_VERB), mode=overrides.mode(), recalc=setting,
                        any_behind=any(recalc.values()), waiting_n=sum(overrides.waiting(version).values()),
                        may_run=roles.may(who, overrides.RUN_VERB), run_holders=", ".join(reads.holders(overrides.RUN_VERB)) or "nobody yet",
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
        checks = [
            {"check": "a stage", "ok": bool(ref and st), "says": ref["stage_name"] if ref else f"{stage or 'nothing'} is not a stage"},
            {"check": "who hands it over", "ok": may, "says": (f"{who} holds {said(ref['verb'])}" if may else f"{who} does not hold {said(ref['verb'])} — {ref['stage_name']} is handed over by {', '.join(reads.holders(ref['verb'])) or 'nobody yet'}") if ref else "—"},
            {"check": "the plan is open", "ok": v.get("status") == "open", "says": f"{version} is {v.get('status', 'unknown')}"},
            {"check": "the stage hands over", "ok": bool(st) and st["ord"] == st["unit_to"],
             "says": "it ends its unit" if st and st["ord"] == st["unit_to"] else "a compressed stage is handed over with the stage it runs into"},
            {"check": "the act", "ok": action in ("hand_over", "reopen") and (action == "hand_over" or bool(reason)),
             "says": {"hand_over": "hand over — the owner's work is in the Plan; the next stage reads it as it stands, as it always does",
                      "reopen": f"reopen — {reason}" if reason else "a reopen says why"}.get(action, "hand over or reopen")},
        ]
        placed = receipts.judge(checks)
        if placed:
            now = dt.datetime.now()
            ACTS.place([{"act_id": f"STG-{now:%Y%m%d%H%M%S%f}", "version_id": version, "stage": stage, "action": action, "reason": reason,
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
