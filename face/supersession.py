"""Supersession (DEC-20261118-01, DEC-20261117-04): a register of links between materials, kept on Launches by whoever
holds the launch right. One link holds a share for each from → to pair, an optional uplift with a reason (in the
innovation layer), an optional end, the switch — on a week, or when the predecessor's stock runs out — and optionally the
accounts it applies to. The five kinds are presets over those settings, all offered; a combination they do not name is
the same link with the settings changed. A link carries demand only, and is an act on the record: withdrawn, the history
goes back where it was.

Registered on the plan's blueprint by `register(...)`, called once from `face/__main__.py`."""
from __future__ import annotations

import datetime as dt

from chassis import receipts
from chassis.landing import LogLanding
from chassis.warehouse import Busy, q
from flask import redirect, request, url_for

from .words import said

VERB = "layer.7.enter"
COLUMNS = ["act_id", "link_id", "action", "version_id", "kind", "from_material", "to_material", "share", "uplift_pct", "uplift_reason", "switch",
           "switch_week", "end_week", "accounts", "reason", "entered_by", "entered_at"]
ACTS = LogLanding("plan", "reg_supersession", COLUMNS)
# the presets: what each kind fills (DEC-20261118-01 point 2) — the person may change any setting after choosing one
KINDS = {
    "replace":      ("Replace", "one for one — a pack, label or code change the buyer does not choose between; the successor takes the history whole", "run_out"),
    "replace_gain": ("Replace with a gain", "one for one, better: the history as the floor, plus a declared uplift in the innovation layer", "run_out"),
    "merge":        ("Merge", "several into one — each predecessor's history × the share retained; the rest is lost volume, shown", "date"),
    "split":        ("Split", "one into several — the history × a share each", "date"),
    "temporary":    ("Temporary", "a bonus or promotional pack stands in for a window, then the baseline goes back to the standard item", "date"),
}

PAGE = """<h1>Supersession<small>{{ version }} · links between materials — this material's demand continues as that one's</small></h1>
<p class="hint">A link moves demand only: price, terms, the bill, the route and the standard are the successor's own. From the switch the predecessor's baseline moves onto each successor at its share — the rest is lost volume — and a declared uplift lands in the innovation layer. A new material that sits alongside the old one is a launch with cannibalisation, not a link. {% if may and is_open %}You keep the links.{% else %}Kept by {{ holders|join(', ') or 'nobody yet' }}.{% endif %} A link is in the plan after the next run.</p>
<table><thead><tr><th>Link</th><th>Kind</th><th>From</th><th>To</th><th class="n">Share</th><th class="n">Uplift</th><th>Switch</th><th>End</th><th>Accounts</th><th class="n">Moved</th><th class="n">Lost</th><th>Why</th><th></th></tr></thead><tbody>
{% for l in links %}<tr><td><code>{{ l.link_id }}</code></td><td>{{ l.kind_label }}</td><td>{{ l.from_material }}</td><td>{{ l.to_material }}</td><td class="n">{{ '{:.0%}'.format(l.share) }}</td>
<td class="n">{{ '{:+.0f}%'.format(l.uplift_pct) if l.uplift_pct else '' }}</td><td class="small">{{ l.switch_says }}</td><td class="small">{{ l.end_week or '' }}</td><td class="small">{{ l.accounts or 'all' }}</td>
<td class="n">{{ '{:,.0f}'.format(l.moved or 0) }}</td><td class="n">{{ '{:,.0f}'.format(l.lost or 0) if l.lost else '' }}</td><td class="small">{{ l.reason }}</td>
<td>{% if may and is_open and l.first %}<form class="inline" method="post" action="{{ url_for('plan.supersession_withdraw') }}"><input type="hidden" name="link_id" value="{{ l.link_id }}"><input name="reason" required placeholder="why" size="10"> <button class="act">Withdraw</button></form>{% endif %}</td></tr>
{% else %}<tr><td colspan="13" class="muted">No links on {{ version }}.</td></tr>{% endfor %}</tbody></table>
{% if may and is_open %}<h2 id="link">Make a link<span class="count">choose a kind — it fills the settings; change any of them</span></h2>
<form class="entry" method="post" action="{{ url_for('plan.supersession_set') }}">
<label>kind<select name="kind">{% for k, v in kinds.items() %}<option value="{{ k }}">{{ v[0] }}</option>{% endfor %}</select></label>
<label class="wide">from (one or more, comma separated)<input name="from_materials" required placeholder="material codes"></label>
<label class="wide">to (one or more, comma separated)<input name="to_materials" required placeholder="material codes"></label>
<label>shares<input name="shares" placeholder="1 — or one per pair, comma separated"></label>
<label>uplift %<input name="uplift_pct" type="number" step="any"></label><label class="wide">uplift reason<input name="uplift_reason"></label>
<label>switch<select name="switch"><option value="">the kind's default</option><option value="run_out">when the predecessor runs out</option><option value="date">on a week</option></select></label>
<label>switch week<select name="switch_week"><option value="">—</option>{% for w in weeks %}<option>{{ w }}</option>{% endfor %}</select></label>
<label>end week<select name="end_week"><option value="">none</option>{% for w in weeks %}<option>{{ w }}</option>{% endfor %}</select></label>
<label>accounts<input name="accounts" placeholder="blank: all"></label>
<label class="wide">why<input name="reason" required></label>
<div class="actions"><button class="primary">Place</button><span class="hint">{% for k, v in kinds.items() %}<b>{{ v[0] }}</b>: {{ v[1] }}{{ '; ' if not loop.last }}{% endfor %}.</span></div></form>{% endif %}
{% if last %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else ('!' if c.flag else '✕') }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}"""


def _split(x: str | None) -> list[str]:
    return [s.strip() for s in (x or "").split(",") if s.strip()]


def register(bp, page, who_fn, ctx_fn, busy, session, roles) -> None:
    from . import reads

    def version_of() -> str:
        return ctx_fn().get("version") or reads.default_version()

    @bp.get("/launches/supersession")
    def supersession():
        try:
            who = who_fn(); version = version_of(); v = reads.version(version) or {}
            sw = {r["link_id"]: r for r in q("select * from plan.supersession_switch where version_id = ?", version)}
            moved = {(r["link_id"], r["material_code"]): r["c"] for r in q(
                "select link_id, material_code, sum(cases) c from plan.supersession_line where version_id = ? and part = 'on' group by all", version)}
            off = {r["link_id"]: -r["c"] for r in q("select link_id, sum(cases) c from plan.supersession_line where version_id = ? and part = 'off' group by all", version)}
            links, seen = [], set()
            for l in q("select * from plan.supersession_link where version_id = ? order by link_id, from_material, to_material", version):
                s = sw.get(l["link_id"]) or {}
                on_total = sum(c for (k, _), c in moved.items() if k == l["link_id"])
                links.append({**l, "kind_label": KINDS.get(l["kind"], (l["kind"],))[0], "switch_says": s.get("says") or l["switch"],
                              "moved": moved.get((l["link_id"], l["to_material"])), "lost": (off.get(l["link_id"], 0) - on_total) if l["link_id"] not in seen else None,
                              "first": l["link_id"] not in seen})
                seen.add(l["link_id"])
            vp = reads.version_periods(version)
            weeks = [r["week_id"] for r in q(f"select week_id from dims.dim_week where period in ({','.join('?' * len(vp['plan']))}) order by 1", *vp["plan"])] if vp["plan"] else []
            return page(PAGE, title="Launches · Supersession", active="supersession", width="none", version=version, links=links, kinds=KINDS, weeks=weeks,
                        may=roles.may(who, VERB, kind=v.get("version_kind")), holders=reads.holders(VERB), is_open=v.get("status") == "open",
                        last=session.last, receipt_acts=("supersession",))
        except Busy as e:
            return busy("Supersession", e)

    @bp.post("/launches/supersession/set")
    def supersession_set():
        f = request.form; who = who_fn(); version = version_of(); v = reads.version(version) or {}
        kind = f.get("kind") or ""
        froms, tos = _split(f.get("from_materials")), _split(f.get("to_materials"))
        try:
            shares = [float(x) for x in _split(f.get("shares"))] or [1.0]
        except ValueError:
            shares = []
        uplift = f.get("uplift_pct") or ""
        switch = f.get("switch") or (KINDS[kind][2] if kind in KINDS else "")
        sw_week, end_week = f.get("switch_week") or "", f.get("end_week") or ""
        accounts, reason = ",".join(_split(f.get("accounts"))), (f.get("reason") or "").strip()
        known = {r["material_code"] for r in q("select material_code from dims.dim_material")}
        pairs = [(a, b) for a in froms for b in tos]
        if len(shares) == 1:
            shares = shares * len(pairs)
        shape_ok = {"replace": len(froms) == 1 and len(tos) == 1, "replace_gain": len(froms) == 1 and len(tos) == 1, "temporary": len(froms) == 1 and len(tos) == 1,
                    "merge": len(froms) > 1 and len(tos) == 1, "split": len(froms) == 1 and len(tos) > 1}.get(kind, False)
        by_from: dict = {}
        for (a, _), s in zip(pairs, shares):
            by_from[a] = by_from.get(a, 0) + s
        may = roles.may(who, VERB, kind=v.get("version_kind"))
        checks = [
            {"check": "who keeps the links", "ok": may, "says": f"{who} holds {said(VERB)}" if may else f"{who} does not hold {said(VERB)}"},
            {"check": "the plan is open", "ok": v.get("status") == "open", "says": f"{version} is {v.get('status', 'unknown')}"},
            {"check": "a kind", "ok": kind in KINDS, "says": KINDS[kind][0] if kind in KINDS else "Replace, Replace with a gain, Merge, Split or Temporary"},
            {"check": "materials we have", "ok": bool(pairs) and set(froms + tos) <= known and not set(froms) & set(tos),
             "says": f"{', '.join(froms)} → {', '.join(tos)}" if pairs and set(froms + tos) <= known else "from and to are materials of ours, and not the same"},
            {"check": "the kind's shape", "ok": shape_ok, "flag": True, "says": "as the kind says" if shape_ok else "not the kind's usual shape — placed as the settings say"},
            {"check": "the shares", "ok": len(shares) == len(pairs) and all(0 < s <= 1 for s in shares) and all(t <= 1.0 + 1e-9 for t in by_from.values()),
             "says": ", ".join(f"{a}→{b} {s:.0%}" for (a, b), s in zip(pairs, shares)) if len(shares) == len(pairs) else "one share, or one for each pair, each above 0 and at most 1; a predecessor's shares at most 1"},
            {"check": "the switch", "ok": switch == "run_out" or (switch == "date" and bool(sw_week)), "says": "when the predecessor runs out" if switch == "run_out" else (f"on {sw_week}" if sw_week else "a week to switch on")},
            {"check": "an end after the switch", "ok": not end_week or not sw_week or end_week >= sw_week, "says": end_week or "none"},
            {"check": "an uplift has a reason", "ok": not uplift or bool((f.get("uplift_reason") or "").strip()), "says": f"{uplift}% — {f.get('uplift_reason')}" if uplift else "no uplift"},
            {"check": "a reason", "ok": bool(reason), "says": reason or "a link says why"},
        ]
        placed = receipts.judge(checks)
        if placed:
            now = dt.datetime.now()
            link = f"SUP-{now:%Y%m%d%H%M%S%f}"
            ACTS.place([{"act_id": f"{link}-A", "link_id": link, "action": "set", "version_id": version, "kind": kind, "from_material": a, "to_material": b,
                         "share": s, "uplift_pct": uplift, "uplift_reason": f.get("uplift_reason") or "", "switch": switch, "switch_week": sw_week if switch == "date" else "",
                         "end_week": end_week, "accounts": accounts, "reason": reason, "entered_by": who, "entered_at": now.isoformat(timespec="seconds")}
                        for (a, b), s in zip(pairs, shares)], who)
        session.last = receipts.write("supersession.set", who, f"{','.join(froms)}>{','.join(tos)}", checks, placed)
        session.say("link placed — in the plan after the next run" if placed else "refused: " + "; ".join(x["says"] for x in checks if not x["ok"] and not x.get("flag")), placed)
        return redirect(url_for("plan.supersession") + "#link")

    @bp.post("/launches/supersession/withdraw")
    def supersession_withdraw():
        f = request.form; who = who_fn(); version = version_of(); v = reads.version(version) or {}
        rows = q("select * from plan.supersession_link where version_id = ? and link_id = ?", version, f.get("link_id") or "")
        reason = (f.get("reason") or "").strip()
        may = roles.may(who, VERB, kind=v.get("version_kind"))
        checks = [
            {"check": "who keeps the links", "ok": may, "says": f"{who} holds {said(VERB)}" if may else f"{who} does not hold {said(VERB)}"},
            {"check": "a link standing", "ok": bool(rows), "says": f"{rows[0]['link_id']}: {rows[0]['from_material']} → {rows[0]['to_material']}" if rows else "no such link in force"},
            {"check": "the plan is open", "ok": v.get("status") == "open", "says": f"{version} is {v.get('status', 'unknown')}"},
            {"check": "a reason", "ok": bool(reason), "says": reason or "a withdrawal says why"},
        ]
        placed = receipts.judge(checks)
        if placed:
            now = dt.datetime.now()
            ACTS.place([{"act_id": f"{rows[0]['link_id']}-W{now:%H%M%S%f}", "link_id": rows[0]["link_id"], "action": "withdraw", "version_id": version,
                         "reason": reason, "entered_by": who, "entered_at": now.isoformat(timespec="seconds")}], who)
        session.last = receipts.write("supersession.withdraw", who, f.get("link_id") or "", checks, placed)
        session.say("withdrawn — the history goes back after the next run" if placed else "refused: " + "; ".join(x["says"] for x in checks if not x["ok"]), placed)
        return redirect(url_for("plan.supersession"))
