"""Withdrawal after a save, and the record read as a page (DEC-20261114-01 steps b and c).

A withdrawal is one act across the grids: a later act that names an earlier one and takes it out of force, at the grain
it was made — a save, or one figure in it — by its author or a holder of the verb, with a reason and a receipt. Never a
deletion: the named act stays on record, marked. The plan is calculated again from the acts that remain, so a figure the
withdrawn one had written over comes back where it reached, and no rule is written for it. The person sees the
consequence — the figures that will change — before they confirm.

    the demand plan    a layer entry is a save of one figure: a withdrawal row in the layer entries (in force after the next run)
    Finance's plan     a release row naming a save, or one figure (released at once by the run scoped to Finance's part)
    the opex schedule  a withdraw row naming a save, or one act (released at once by the run scoped to the schedule)

The change history is `plan.change_record` on a page: per version, every act in order — who, when, why, what it did and
whether it stands, was withdrawn, was overwritten by a later act, or was refused. Registered on the plan's blueprint by
`register(...)`, called from `face/__main__.py`."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

from chassis import receipts
from chassis.warehouse import Busy, q
from flask import redirect, request, url_for

from . import finance_live
from . import schedule as S
from .words import said

GRIDS = {"demand": "the demand plan", "finance": "Finance's plan", "schedule": "the opex schedule"}
RECORD = {"demand": "demand plan", "finance": "Finance's plan", "schedule": "opex schedule"}
FIN_VERB = "overlay.finance.enter"
SHOWN = 40                                                 # changed figures listed on the confirmation; the rest counted

CONFIRM = """<h1>Withdraw<small>{{ grid_label }} · {{ version }} · {{ 'a whole save' if is_save else 'one figure' }} — taken out of force by a later act, never deleted</small></h1>
{% if not acts %}<p class="lede">{{ subject }} is not on {{ version }}{% if waiting %} — or the warehouse has not seen it yet: a save is withdrawn after the run that took it in{% endif %}.</p>{% else %}
<table><thead><tr><th>Act</th><th>When</th><th>By</th><th>What</th><th>Why</th><th>Standing</th></tr></thead><tbody>
{% for a in acts[:20] %}<tr class="{{ 'off' if a.standing != 'stands' }}"><td><code>{{ a.act_id }}</code></td><td class="small">{{ a.at_shown }}</td><td class="small">{{ a.by_whom }}</td><td class="small">{{ a.what }}</td><td class="small">{{ a.why or '' }}</td><td><span class="state">{{ a.standing }}</span></td></tr>{% endfor %}
{% if acts|length > 20 %}<tr><td colspan="6" class="muted">and {{ acts|length - 20 }} more in the save</td></tr>{% endif %}</tbody></table>
<h2>What changes<span class="count">{{ effect.says }}</span></h2>
{% if effect.rows %}<table><thead><tr>{% for h in effect.head %}<th class="{{ 'n' if loop.index > effect.nkeys }}">{{ h }}</th>{% endfor %}</tr></thead><tbody>
{% for r in effect.rows[:shown] %}<tr>{% for x in r %}<td class="{{ 'n' if loop.index > effect.nkeys }}">{{ x }}</td>{% endfor %}</tr>{% endfor %}
{% if effect.rows|length > shown %}<tr><td colspan="{{ effect.head|length }}" class="muted">and {{ effect.rows|length - shown }} more</td></tr>{% endif %}</tbody>
{% if effect.total %}<tfoot><tr>{% for x in effect.total %}<td class="{{ 'n' if loop.index > effect.nkeys }}"><b>{{ x }}</b></td>{% endfor %}</tr></tfoot>{% endif %}</table>{% endif %}
{% if refusals %}<p class="flash no">Not withdrawn: {{ refusals|join('; ') }}.</p>{% else %}
<form method="post" action="{{ url_for('plan.withdrawal_do') }}" class="form-row"><input type="hidden" name="grid" value="{{ grid }}"><input type="hidden" name="id" value="{{ subject }}"><input type="hidden" name="version" value="{{ version }}">
<label class="small grow">why it is withdrawn <input name="reason" required placeholder="the reason goes on record with the act"></label>
<button class="primary" onclick="this.textContent='Withdrawing…'">Withdraw {{ 'the save' if is_save else 'the figure' }}</button> <a href="{{ back }}">keep it</a></form>
<p class="hint">{{ when }} The act stays on record, struck through, with yours beside it; the plan is calculated again from what remains.</p>{% endif %}{% endif %}
<style>.form-row{display:flex;flex-wrap:wrap;gap:.8rem;align-items:end;margin:.6rem 0}.form-row .grow{flex:1;display:flex;flex-direction:column}</style>"""

HISTORY = """<h1>Change history<small>{{ version }} · every act on the plan in order — who, when, why, and whether it stands; nothing is removed from the record</small></h1>
<form class="toolbar" method="get">{{ context_fields() }}<label>record<select name="record" onchange="this.form.submit()"><option value="">every record</option>{% for r in records %}<option value="{{ r.record }}" {{ 'selected' if r.record == record }}>{{ r.record }} ({{ r.n }})</option>{% endfor %}</select></label>
<label>standing<select name="standing" onchange="this.form.submit()"><option value="">any</option>{% for s in ('stands', 'withdrawn', 'overwritten', 'refused') %}<option {{ 'selected' if s == standing }}>{{ s }}</option>{% endfor %}</select></label></form>
<div class="cards tiles">{% for s in tally %}<div class="card stat"><span>{{ s.standing }}</span><b>{{ '{:,}'.format(s.n) }}</b></div>{% endfor %}</div>
<p class="hint"><b>Stands</b>: in force. <b>Withdrawn</b>: a later act took it out of force — the act that did is in the list, naming it. <b>Overwritten</b>: a later act reached the same figure and it no longer shows anywhere; withdraw that later act and this one stands again. <b>Refused</b>: placed, and failed one of the plan's checks. A door's decision stands for every version and is listed on each.{% if may_any %} <i>withdraw…</i> shows what would change before anything is withdrawn.{% endif %}</p>
<table><thead><tr><th>When</th><th>Record</th><th>Act</th><th>By</th><th>What</th><th>Why</th><th>Standing</th><th></th></tr></thead><tbody>
{% for a in acts %}<tr class="{{ 'off' if a.standing not in ('stands',) }}"><td class="small">{{ a.at_shown }}</td><td class="small">{{ a.record }}</td><td class="small">{{ a.act }}<div class="muted"><code>{{ a.act_id }}</code></div></td><td class="small">{{ a.by_whom or '' }}</td>
<td class="small">{{ a.what }}{% if a.save_id and a.save_id != a.act_id %}<div class="muted">in save {{ a.save_id }}</div>{% endif %}</td><td class="small">{{ a.why or '' }}</td><td><span class="state">{{ a.standing }}</span></td>
<td class="acts small">{% if a.can_withdraw %}<a href="{{ url_for('plan.withdrawal', grid=a.grid, id=a.withdraw_id, version=version) }}">withdraw…</a>{% if a.save_id and a.save_id != a.withdraw_id %}<br><a href="{{ url_for('plan.withdrawal', grid=a.grid, id=a.save_id, version=version) }}">the save…</a>{% endif %}{% endif %}</td></tr>
{% else %}<tr><td colspan="8" class="muted">No act on {{ version }}{% if record %} in {{ record }}{% endif %}.</td></tr>{% endfor %}</tbody></table>
{% if more %}<p class="hint">The {{ '{:,}'.format(acts|length) }} latest shown of {{ '{:,}'.format(total) }} — choose a record or a standing to narrow it.</p>{% endif %}"""


def _shown_at(a) -> str:
    return str(a or "")[:16].replace("T", " ")


def _n(x, d=0) -> str:
    return "" if x is None else f"{x:,.{d}f}"


def acts_named(grid: str, version: str, subject: str) -> list[dict]:
    """The acts a withdrawal of `subject` covers: the one act, or every act of the save it names."""
    return q("""select *, cast(acted_at as text) at_text from plan.change_record where record = ? and version_id = ? and grid = ?
                and (withdraw_id = ? or save_id = ?) order by acted_at, act_id""", RECORD[grid], version, grid, subject, subject)


def effect(grid: str, version: str, subject: str) -> dict:
    """The figures that will change, computed before anything is placed — by the function the run uses."""
    if grid == "finance":
        rows = finance_live.without(version, subject)
        dv = sum((r["cases_after"] or 0) - (r["cases_now"] or 0) for r in rows)
        dn = sum((r["net_sales_after"] or 0) - (r["net_sales_now"] or 0) for r in rows)
        return {"says": f"{len(rows):,} cells of Finance's plan at account × material × period; volume {dv:+,.0f} cases, net sales {dn:+,.0f}" if rows else
                        "nothing — every figure it wrote has been written over since, so the plan does not move",
                "head": ["Account", "Material", "Period", "Cases now", "after", "Net sales now", "after"], "nkeys": 3,
                "rows": [[r["account_code"], r["material_code"], r["period"], _n(r["cases_now"]), _n(r["cases_after"]), _n(r["net_sales_now"]), _n(r["net_sales_after"])] for r in rows],
                "total": ["", "", "Change", "", f"{dv:+,.0f}", "", f"{dn:+,.0f}"] if rows else None, "n": len(rows)}
    if grid == "schedule":
        b = S.base(version)
        after = S.compute(b["inp"], S.in_force(b["on_file"] + [{"action": "withdraw", "withdraws": subject}]), b["rules"])
        rows = [(k, b["cells"].get(k) or {}, c) for k, c in after.items() if abs(((b["cells"].get(k) or {}).get("amount") or 0) - (c.get("amount") or 0)) > 0.005]
        rows.sort(key=lambda r: r[0])
        d = sum((c.get("amount") or 0) - (n.get("amount") or 0) for _, n, c in rows)
        return {"says": f"{len(rows):,} months of the schedule; {d:+,.0f} in all" if rows else "nothing — a later act already stands where it reached",
                "head": ["Entity", "Cost centre", "Account", "Period", "Now", "After", "State after"], "nkeys": 4,
                "rows": [[k[0], k[1], k[2], k[3], _n(n.get("amount")), _n(c.get("amount")), c.get("state")] for k, n, c in rows],
                "total": ["", "", "", "Change", "", f"{d:+,.0f}", ""] if rows else None, "n": len(rows)}
    by = defaultdict(float)
    for r in q("select period, value_kind, sum(value) v from plan.entry_cells where entry_id = ? group by all order by period", subject):
        by[(r["period"], r["value_kind"])] += r["v"] or 0
    rows = [[p, k, _n(-v, 1)] for (p, k), v in sorted(by.items())]
    return {"says": f"the entry's contribution leaves the demand plan in {len(rows)} period{'s' if len(rows) != 1 else ''}, after the next run" if rows else
                    "the entry contributes nothing to the demand plan now",
            "head": ["Period", "As", "Change"], "nkeys": 2, "rows": rows, "total": None, "n": len(rows)}


def checks_for(grid: str, version: str, subject: str, acts: list[dict], who: str, roles, reads, reason: str | None) -> list[dict]:
    """The same rules for every grid: on file and seen by the warehouse, still standing, the version open, who may."""
    v = reads.version(version) or {}
    standing = [a for a in acts if a["standing"] == "stands" and a["act"] not in ("withdraw", "withdrawal", "release")]
    authors = {a["by_whom"] for a in acts}
    if grid == "finance":
        may, verb = roles.may(who, FIN_VERB, kind=v.get("version_kind")), FIN_VERB
    elif grid == "schedule":
        verbs = [x for x in (S._verb("rate"),) if x]
        ccs = {r["cost_centre_code"] for r in q("select distinct cost_centre_code from plan.schedule_edit where edit_id = ? or save_id = ?", subject, subject)}
        month_ok = bool(ccs) and bool(S._verb("amount")) and all(roles.may(who, S._verb("amount"), c, dimension="organisation", kind=v.get("version_kind")) for c in ccs)
        may, verb = (authors == {who}) or any(roles.may(who, x, kind=v.get("version_kind")) for x in verbs) or month_ok, verbs[0] if verbs else "the schedule's verbs"
    else:
        layer = acts[0]["what"].split(" ")[1] if acts else "?"
        verb = f"layer.{layer}.withdraw"
        may = roles.may(who, verb, kind=v.get("version_kind"))
    out = [
        {"check": "on file", "ok": bool(acts), "says": f"{subject} on {version}, {len(acts)} act{'s' if len(acts) != 1 else ''}" if acts else f"{subject} is not on {version}, or the warehouse has not seen it yet"},
        {"check": "still standing", "ok": bool(standing), "says": f"{len(standing)} of them stand" if standing else "nothing in it stands — already withdrawn, overwritten or refused"},
        {"check": "version open", "ok": v.get("status") == "open", "says": f"{version} is {v.get('status', 'unknown')}"},
        {"check": "who may withdraw", "ok": bool(may), "says": f"{who} {'made it' if authors == {who} else 'holds ' + said(verb)}" if may else f"{who} did not make it and does not hold {said(verb)}"},
    ]
    if reason is not None:
        out.append({"check": "a reason", "ok": bool(reason), "says": reason or "a withdrawal says why"})
    return out


def register(bp, page, who_fn, busy, session, roles, run_plan, entries_landing, finance_landing) -> None:
    from . import reads

    def _back(grid: str, version: str) -> str:
        return url_for("plan.change_history", version=version, record=RECORD.get(grid, ""))

    @bp.get("/withdrawal")
    def withdrawal():
        try:
            who = who_fn(); a = request.args
            grid = a.get("grid") if a.get("grid") in GRIDS else "finance"
            version = a.get("version") or reads.default_version(); subject = a.get("id", "")
            acts = acts_named(grid, version, subject)
            for x in acts:
                x["at_shown"] = _shown_at(x["at_text"])
            is_save = len(acts) > 1 or (bool(acts) and acts[0]["save_id"] == subject and grid != "demand")
            checks = checks_for(grid, version, subject, acts, who, roles, reads, None)
            eff = effect(grid, version, subject) if acts else {"says": "", "rows": []}
            when = "It is in force after the next run." if grid == "demand" else "It is in force at once: the run scoped to this part of the plan carries it in."
            return page(CONFIRM, title="Withdraw", active="version_history", grid=grid, grid_label=GRIDS[grid], version=version, subject=subject, acts=acts,
                        is_save=is_save, effect=eff, shown=SHOWN, refusals=[c["says"] for c in checks if not c["ok"]], back=_back(grid, version), when=when,
                        waiting=True)
        except Busy as e:
            return busy("Withdraw", e)

    @bp.post("/withdrawal")
    def withdrawal_do():
        f = request.form; who = who_fn()
        grid = f.get("grid") if f.get("grid") in GRIDS else ""
        version = f.get("version") or ""; subject = f.get("id", ""); reason = (f.get("reason") or "").strip()
        acts = acts_named(grid, version, subject) if grid else []
        checks = checks_for(grid or "finance", version, subject, acts, who, roles, reads, reason)
        placed = receipts.judge(checks)
        now = dt.datetime.now(); stamp = now.strftime("%Y%m%d-%H%M%S-%f")
        if placed and grid == "finance":
            finance_landing.place([{"edit_id": f"FR-{stamp}", "action": "release", "withdraws": subject, "version_id": version, "note": reason,
                                    "entered_by": who, "entered_on": now.isoformat(timespec="microseconds")}], who)
        elif placed and grid == "schedule":
            S.LANDING.place([{"edit_id": f"SW-{stamp}", "save_id": f"SW-{stamp}", "version_id": version, "action": "withdraw", "withdraws": subject,
                              "entity_code": "", "cost_centre_code": "", "account_code": "", "period": "", "value": "", "driver": "", "calc_at_entry": "",
                              "reason_code": "", "note": reason, "entered_by": who, "entered_on": now.isoformat(timespec="microseconds")}], who)
        elif placed and grid == "demand":
            layer = int(acts[0]["what"].split(" ")[1])
            entries_landing.place([{"entry_id": f"LW-F-{stamp}", "action": "withdraw", "withdraws": subject, "version_id": version, "layer_no": layer,
                                    "entered_by": who, "entered_on": dt.date.today().isoformat(), "reason_code": "", "effect_type": "primary",
                                    "scope_material": "", "scope_customer": "", "period_from": "", "period_to": "", "value_kind": "cases", "value": 0,
                                    "spread_rule": "baseline_shape", "note": reason}], who)
        session.last = receipts.write(f"withdrawal.{grid or 'unknown'}", who, subject, checks, placed)
        if not placed:
            session.say("withdrawal refused: " + "; ".join(c["says"] for c in checks if not c["ok"]), False)
            return redirect(url_for("plan.withdrawal", grid=grid or "finance", id=subject, version=version))
        if grid == "demand":
            session.say(f"withdrawal of {subject} placed — it takes effect on the next run", True)
            return redirect(_back(grid, version))
        if run_plan(who, grid):
            session.say(f"{subject} withdrawn from {version} — the plan is calculated again from what remains", True)
            return redirect(_back(grid, version))
        return redirect(url_for("plan.run"))

    @bp.get("/versions/history")
    def change_history():
        try:
            who = who_fn(); a = request.args
            version = a.get("version") or reads.default_version()
            record, standing = a.get("record") or "", a.get("standing") or ""
            where, params = "where (version_id = ? or version_id is null)", [version]
            records = q(f"select record, count(*) n from plan.change_record {where} group by 1 order by 1", *params)
            tally = q(f"select standing, count(*) n from plan.change_record {where}" + (" and record = ?" if record else "") + " group by 1 order by 1", *params, *([record] if record else []))
            if record:
                where += " and record = ?"; params.append(record)
            if standing:
                where += " and standing = ?"; params.append(standing)
            total = q(f"select count(*) n from plan.change_record {where}", *params)[0]["n"]
            acts = q(f"select *, cast(acted_at as text) at_text from plan.change_record {where} order by acted_at desc nulls last, act_id desc limit 400", *params)
            v = reads.version(version) or {}
            is_open = v.get("status") == "open"
            may = {"finance": roles.may(who, FIN_VERB), "schedule": bool(S._verb("rate")) and roles.may(who, S._verb("rate"))}
            held = set(roles.actions_held(who)) if hasattr(roles, "actions_held") else set()
            for x in acts:
                x["at_shown"] = _shown_at(x["at_text"])
                g = x["grid"]
                x["can_withdraw"] = bool(g) and is_open and x["standing"] == "stands" and (
                    may.get(g) or x["by_whom"] == who or (g == "demand" and f"layer.{x['what'].split(' ')[1]}.withdraw" in held))
            return page(HISTORY, title="Change history", active="version_history", version=version, records=records, record=record, standing=standing,
                        tally=tally, acts=acts, total=total, more=total > len(acts), may_any=any(x["can_withdraw"] for x in acts))
        except Busy as e:
            return busy("Change history", e)
