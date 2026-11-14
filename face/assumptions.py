"""The assumptions every plan on a version is valued with (DEC-20261113-10): one page for the one set — rows are the
assumptions, columns the periods of the year in context, the reference version's value beneath each — and beside each
assumption what reads it, so a person changing one sees what will move before they save.

Changed by an amendment: a value from a period on one version, placed as a file in the landing by the holders of
`register.assumptions.maintain`, with a receipt — never an edit of the value in force — and in the plan after the next
run, as the terms and price lists are. Global means not owned by a step: a line's driver, a history window, a resolution
rule stay on their own step's page. Registered on the plan's blueprint by `register(...)`, called from
`face/__main__.py`."""
from __future__ import annotations

import csv
import datetime as dt
import math

from chassis import receipts
from chassis.landing import LogLanding
from chassis.warehouse import Busy, q
from flask import redirect, request, url_for

from .words import said

VERB = "register.assumptions.maintain"
COLUMNS = ["amend_id", "version_id", "assumption_code", "valid_from", "value", "note", "entered_by", "entered_on"]
LANDING = LogLanding("plan", "reg_assumption_amend", COLUMNS)
# what a value of each kind may be: a slip is refused, a real figure never is
BOUNDS = {"rate": (0.0001, 1000.0), "pct": (-0.5, 1.0), "index": (1.0, 10000.0)}
SAY_KIND = {"rate": "a rate", "pct": "a share — 0.032 is 3.2%", "index": "an index"}

PAGE = """<h1>Assumptions<small>FY{{ fy }} · {{ version }} · the one set every plan on the version is valued with{% if ref %}, {{ ref }}'s beneath each{% endif %}</small></h1>
<p class="hint">{% if may_edit and open %}You maintain the assumptions: an amendment is a value from a period on {{ version }} — the value in force is never edited — and takes effect on the next run.{% elif may_edit %}{{ version }} is {{ status }} — its assumptions are not changed.{% else %}You read the assumptions; they are maintained by {{ holders|join(', ') or 'nobody yet' }}.{% endif %}
A figure that differs from {{ ref or 'the reference' }} is marked ≠; one amended from a period is boxed. What a step sets for itself — a schedule line's driver, a history window — stays on that step's page.</p>
{% if waiting %}<p class="hint"><b>{{ waiting|length }} amendment{{ 's' if waiting|length != 1 }} placed and waiting for the next run</b> — {% for w in waiting %}{{ w.assumption_code }} from {{ w.valid_from }} = {{ w.value }}{{ '; ' if not loop.last }}{% endfor %}. The grid shows the plan as last run.</p>{% endif %}
<div class="finwrap"><table class="assume"><thead><tr><th>Assumption</th>{% for p in periods %}<th class="n {{ 'closed' if p.closed }}">{{ p.label }}{% if p.closed %}<div class="small muted">actual</div>{% endif %}</th>{% endfor %}<th>What reads it</th></tr></thead><tbody>
{% for a in rows %}<tr><td class="node"><b>{{ a.name }}</b><div class="small muted">{{ a.code }} · {{ a.kind_said }}</div></td>
{% for c in a.cells %}<td class="n {{ 'amended' if c.amended }} {{ 'differs' if c.differs }}"{% if c.title %} title="{{ c.title }}"{% endif %}>{{ c.show }}{% if c.differs %} <span class="small">≠</span>{% endif %}{% if c.ref is not none %}<span class="src">{{ c.ref_show }}</span>{% endif %}</td>{% endfor %}
<td class="small reads">{% for r in a.readers %}<div>{% if r.href %}<a href="{{ r.href }}">{{ r.page_label }}</a>{% else %}{{ r.page_label }}{% endif %}{% if not r.built %} <span class="muted">(not yet built)</span>{% endif %} — {{ r.how }}{% if r.inputs %} ({{ r.inputs }} input material{{ 's' if r.inputs != 1 }}){% endif %}</div>{% else %}<span class="muted">Nothing reads it yet{% if a.code == 'WAGE_INDEX' %} — the labour model uses each agreement's own increase{% endif %}: a change here moves no figure.</span>{% endfor %}</td></tr>
{% else %}<tr><td colspan="{{ periods|length + 2 }}" class="muted">{{ version }} carries no assumptions in FY{{ fy }}.</td></tr>{% endfor %}</tbody></table></div>
{% if may_edit and open %}<h2 id="amend">Amend an assumption<span class="count">a value from a period on {{ version }} — what reads it is listed above</span></h2>
<form class="entry" method="post" action="{{ url_for('plan.assumption_amend') }}"><input type="hidden" name="version" value="{{ version }}"><input type="hidden" name="fy" value="{{ fy }}">
<label>assumption<select name="assumption_code">{% for a in all_codes %}<option value="{{ a.code }}">{{ a.name }}</option>{% endfor %}</select></label>
<label>from period<select name="valid_from">{% for p in amendable %}<option>{{ p }}</option>{% endfor %}</select></label>
<label>value<input name="value" inputmode="decimal" required placeholder="0.035 for 3.5%; 0.66; 108"></label>
<label class="wide">note — why<input name="note" required placeholder="the outlook, the contract, the source"></label>
<div class="actions"><button class="primary">Place amendment</button><span class="hint">in force from the period chosen until a later amendment, after the next run</span></div></form>{% endif %}
<h2>Amendments<span class="count">{{ version }} · each a value from a period; the latest for a period stands</span></h2>
<table><thead><tr><th>Assumption</th><th>From</th><th class="n">Value</th><th class="n">Was</th><th>Note</th><th>By</th><th>When</th></tr></thead><tbody>
{% for m in amendments %}<tr><td>{{ m.assumption_name }}</td><td>{{ m.amended_from }}</td><td class="n">{{ m.value_show }}</td><td class="n">{{ m.was_show }}</td><td class="small">{{ m.amend_note or '' }}</td><td class="small">{{ m.amended_by }}</td><td class="small">{{ (m.amended_on or '')[:16].replace('T', ' ') }}</td></tr>
{% else %}<tr><td colspan="7" class="muted">None on {{ version }}: every period reads the version's own values.</td></tr>{% endfor %}</tbody></table>
{% if last and last.act == 'assumption.amend' %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else '✕' }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}
<style>.finwrap{overflow-x:auto}table.assume td.n{vertical-align:top;white-space:nowrap}table.assume td.node{min-width:13rem;vertical-align:top}table.assume td.reads{min-width:20rem;vertical-align:top}
table.assume .src{display:block;font-size:.72rem;color:var(--muted)}table.assume td.amended{box-shadow:inset 0 0 0 1px var(--ink)}table.assume td.closed,table.assume th.closed{color:var(--muted)}</style>"""


def _show(kind: str, x) -> str:
    if x is None:
        return ""
    return f"{x:.1%}" if kind == "pct" else (f"{x:,.1f}" if kind == "index" else f"{x:,.4f}")


def _num(raw) -> float | None:
    try:
        v = float(str(raw or "").strip().replace(",", ""))
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def waiting(version: str | None = None) -> list[dict]:
    """Amendments placed since the last run, in the order placed."""
    out = []
    for p in LANDING.pending():
        with open(p, newline="") as fh:
            out += [r for r in csv.DictReader(fh) if version is None or r.get("version_id") == version]
    return out


def register(bp, page, who_fn, ctx_fn, busy, session, roles) -> None:
    from . import reads

    def _where() -> tuple[str | None, int]:
        c = ctx_fn(); version = request.args.get("version") or c.get("version")
        v = reads.version(version or "") or {}
        return version, int(c.get("fy") or v.get("fiscal_year") or 0)

    @bp.get("/assumptions")
    def assumptions():
        try:
            who = who_fn(); version, fy = _where()
            v = reads.version(version or "") or {}
            ref = v.get("reference_version")
            per = q("select period, fiscal_period, period_state from dims.dim_period where fiscal_year = ? order by period", fy)
            upto = v.get("from_period") or ""             # the version's actual periods, not the calendar's closed ones
            periods = [{"period": p["period"], "label": f"P{p['fiscal_period']:02d}", "closed": p["period"] <= upto} for p in per]
            inforce = q("select * from plan.assumption_in_force where version_id = ? and fiscal_year = ?", version, fy)
            refs = {(r["assumption_code"], r["period"]): r["value"] for r in q("select assumption_code, period, value from plan.assumption_in_force where version_id = ? and fiscal_year = ?", ref, fy)} if ref else {}
            by: dict = {}
            for r in inforce:
                by.setdefault(r["assumption_code"], {"code": r["assumption_code"], "name": r["assumption_name"], "kind": r["kind"], "cells": {}})["cells"][r["period"]] = r
            linked = {r["c"]: r["n"] for r in q("select commodity_link c, count(*) n from dims.dim_input_material where coalesce(commodity_link, '') <> '' group by 1")}
            readers: dict = {}
            for r in q("select * from plan.ref_assumption_reader order by built desc, reader"):
                href = url_for(r["page"], slug=r["page_slug"]) if r["page"] == "plan.rung" and r["page_slug"] else (url_for(r["page"]) if r["page"] else None)
                readers.setdefault(r["assumption_code"], []).append({**r, "href": href, "inputs": linked.get(r["assumption_code"]) if r["page_slug"] == "standard" else None})
            rows = []
            for code, a in sorted(by.items(), key=lambda kv: kv[1]["name"]):
                cells = []
                for p in periods:
                    r = a["cells"].get(p["period"]); x = r["value"] if r else None; rv = refs.get((code, p["period"]))
                    amended = bool(r and r["source"] == "amended")
                    cells.append({"show": _show(a["kind"], x), "ref": rv, "ref_show": _show(a["kind"], rv), "amended": amended,
                                  "differs": x is not None and rv is not None and abs(x - rv) > 1e-9,
                                  "title": (f"amended from {r['amended_from']} by {r['amended_by']}: {r['amend_note'] or ''} — {version}'s own value is {_show(a['kind'], r['version_value'])}"
                                            if amended else "")})
                rows.append({**a, "kind_said": SAY_KIND.get(a["kind"], a["kind"]), "cells": cells, "readers": readers.get(code, [])})
            amendments = [{**m, "value_show": _show(m["kind"], m["value"]), "was_show": _show(m["kind"], m["version_value"])}
                          for m in q("""select assumption_code, any_value(assumption_name) assumption_name, any_value(kind) "kind", amended_from, any_value("value") "value",
                                               any_value(version_value) version_value, any_value(amend_note) amend_note, any_value(amended_by) amended_by, any_value(amended_on) amended_on
                                        from plan.assumption_in_force where version_id = ? and source = 'amended' and period = amended_from
                                        group by assumption_code, amended_from order by amended_from, assumption_code""", version)]
            closed = {r["period"] for r in q("select period from dims.dim_period where period <= ?", v.get("from_period") or "")}
            amendable = [r["period"] for r in q("select distinct period from plan.assumption_in_force where version_id = ? order by 1", version) if r["period"] not in closed]
            all_codes = [{"code": r["assumption_code"], "name": r["assumption_name"]}
                         for r in q("select distinct assumption_code, assumption_name from dims.reg_assumption where version_id = ? order by 2", version)]
            return page(PAGE, title="Assumptions", active="assumptions", width="none", version=version, fy=fy, ref=ref, periods=periods, rows=rows,
                        amendments=amendments, amendable=amendable, all_codes=all_codes, waiting=waiting(version),
                        may_edit=roles.may(who, VERB), open=v.get("status") == "open", status=v.get("status", "unknown"),
                        holders=reads.holders(VERB), last=session.last, receipt_acts=("assumption.",))
        except Busy as e:
            return busy("Assumptions", e)

    @bp.post("/assumptions/amend")
    def assumption_amend():
        """An assumption amended from a period on one version: a new row in the landing, checked and receipted; the value
        in force is never edited, and the next run reads the new row from its period."""
        f = request.form; who = who_fn(); version = f.get("version") or ctx_fn().get("version")
        v = reads.version(version or "") or {}
        code, start, raw, note = f.get("assumption_code", ""), f.get("valid_from", ""), f.get("value"), (f.get("note") or "").strip()
        a = (q("select assumption_name, kind from dims.reg_assumption where version_id = ? and assumption_code = ? limit 1", version, code) or [None])[0]
        horizon = {r["period"] for r in q("select period from plan.assumption_in_force where version_id = ? and assumption_code = ?", version, code)}
        closed = {r["period"] for r in q("select period from dims.dim_period where period <= ?", v.get("from_period") or "")}
        value = _num(raw); lo, hi = BOUNDS.get((a or {}).get("kind"), (-1e12, 1e12))
        may = roles.may(who, VERB)
        checks = [
            {"check": "who may amend", "ok": may, "says": f"{who} holds {said(VERB)}" if may else f"{who} does not hold {said(VERB)} — the assumptions are maintained by {', '.join(reads.holders(VERB))}"},
            {"check": "version open", "ok": v.get("status") == "open", "says": f"{version} is {v.get('status', 'unknown')}" + ("" if v.get("status") == "open" else " — its assumptions are not changed")},
            {"check": "an assumption of the version", "ok": a is not None, "says": f"{code} · {a['assumption_name']}" if a else f"{code or 'nothing'} is not an assumption on {version}"},
            {"check": "from an open period of the version", "ok": start in horizon and start not in closed,
             "says": f"from {start}" if start in horizon and start not in closed else f"{start or 'no period'} is an actual period of {version} or outside its horizon"},
            {"check": "a value it can be", "ok": value is not None and lo <= value <= hi,
             "says": (_show((a or {}).get("kind", "rate"), value) if value is not None and lo <= value <= hi
                      else f"{raw!r} is not {SAY_KIND.get((a or {}).get('kind'), 'a number')} between {lo:g} and {hi:g}")},
            {"check": "a note says why", "ok": bool(note), "says": note or "an amendment says why"},
        ]
        placed = receipts.judge(checks)
        stamp = dt.datetime.now()
        if placed:
            LANDING.place([{"amend_id": f"AA-{stamp.strftime('%Y%m%d-%H%M%S-%f')}", "version_id": version, "assumption_code": code, "valid_from": start,
                            "value": repr(value), "note": note, "entered_by": who, "entered_on": stamp.isoformat(timespec="seconds")}], who)
        session.last = receipts.write("assumption.amend", who, f"{version}:{code}@{start}", checks, placed)
        session.say(f"{a['assumption_name']} on {version} amended from {start} — in the plan after the next run" if placed
                    else "amendment refused: " + "; ".join(c["says"] for c in checks if not c["ok"]), placed)
        return redirect(url_for("plan.assumptions", version=version, fy=f.get("fy") or None) + "#amend")
