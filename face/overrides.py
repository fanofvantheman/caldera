"""Override points, the port and recalculation (DEC-20261119-01).

A Plan has one figure for each cell. A figure is calculated unless an override stands on it, at a point the model declares
(`dims.ref_override_point`): the production quantity, a key material's purchase, a component of the planned unit cost,
Finance's volume or price, an opex month locked at a figure — each typed with a reason, the calculated figure kept beside.

People work in a **sandbox** — a what-if named from its Plan, carrying its code with a letter — so one planner's working moves
neither the Plan nor anyone else's sandbox. **Porting** is the act that changes the Plan: a planner ports overrides from a
sandbox into its Plan, or from one Plan into the next for the periods still planned. Only overrides are ported, onto the
declared points, as the figure typed; calculated figures never are. All of them or a chosen set; where the receiving Plan
already holds a different override on the cell both are shown and the person porting chooses. A port is an act with a
receipt.

**Recalculation** after an override or a port is a setting, one for every Plan, beside the compression of stages:
automatic runs every model after it at once; manual places it and marks the stages after it behind — not yet
recalculated — until someone recalculates. Behind is read from what waits for a run, never stored.

Registered on the plan's blueprint by `register(...)`, called once from `face/__main__.py`; the override pages call
`released(...)` after placing an act."""
from __future__ import annotations

import csv
import datetime as dt

from chassis import receipts
from chassis.landing import LogLanding
from chassis.warehouse import Busy, q
from flask import redirect, request, url_for

from .words import said

SETTING_VERB = "version.name"
RUN_VERB = "run.plan"
SETTING = LogLanding("plan", "reg_recalc_setting", ["act_id", "mode", "reason", "entered_by", "entered_at"])
# the receiving Plan's figure as it stands, by point: the calculated figure and the figure in force (an override where one stands)
NOW = {
    "production": ("""select material_code, plant_code, period, proposed calc_quantity, quantity now_quantity
                      from plan.production_requirement where version_id = ?"""),
    "purchase": ("""select input_code, plant_code, period, purchase_quantity now_quantity, purchase_price now_price
                    from plan.material_stock where version_id = ?"""),
    "unit_cost": ("""select material_code, plant_code, period, c.component,
                            case c.component when 'material' then material_driven when 'labour' then labour_driven
                                 when 'variable_overhead' then variable_driven else fixed_driven end calc_per_case,
                            case c.component when 'material' then material_cost when 'labour' then labour_cost
                                 when 'variable_overhead' then variable_overhead else fixed_overhead end now_per_case
                     from plan.planned_unit_cost, (values ('material'), ('labour'), ('variable_overhead'), ('fixed_overhead')) c(component)
                     where version_id = ?"""),
}
_RUN: dict = {}


def points(ported_only: bool = False) -> list[dict]:
    rows = q("select * from dims.ref_override_point order by ord")
    for r in rows:
        r["cells"] = r["cell"].split(",")
        r["values"] = r["figures"].split(",")
    return [r for r in rows if r["ports"] or not ported_only]


def _columns(table: str) -> list[str]:
    cols = [r["column_name"] for r in q(f"select column_name from (describe bronze.{table})")
            if not r["column_name"].startswith("_dlt") and r["column_name"] not in ("source_file", "file_row_number")]
    return cols + [c for c in ("copied_from", "ported_from") if c not in cols]


def landing(point: dict) -> LogLanding:
    return LogLanding("plan", point["register"], _columns(point["register"]))


def mode() -> str:
    try:
        return (q("select mode from plan.recalc_setting") or [{"mode": "manual"}])[0]["mode"]
    except Exception:                                           # a warehouse built before the setting: manual
        return "manual"


def waiting(version: str) -> dict[str, int]:
    """The overrides and ports placed on a Plan that no run has taken in yet, by stage: what makes the stages after them
    behind under manual recalculation."""
    out: dict[str, int] = {}
    for p in points():
        for path in LogLanding("plan", p["register"], []).pending():
            with open(path, newline="") as fh:
                n = sum(1 for r in csv.DictReader(fh) if r.get("version_id") == version)
            if n:
                out[p["stage"]] = out.get(p["stage"], 0) + n
    return out


def behind(version: str) -> dict[str, str]:
    """Each stage's recalculation on a Plan: '' (recalculated), 'overrides waiting' (its own override or port is placed and
    not yet run) or 'behind' (a stage before it has one)."""
    w = waiting(version)
    ords = {r["stage"]: r["ord"] for r in q("select stage, ord from dims.ref_stage")}
    first = min((ords[s] for s in w), default=None)
    out = {}
    for s, o in ords.items():
        out[s] = "overrides waiting" if s in w else ("behind" if first is not None and o > first else "")
    return out


def released(who: str, point: str, session, placed_says: str, placed: bool) -> bool:
    """After an override is placed: automatic recalculation runs every model after it at once; manual leaves it placed and
    the stages after it behind. Returns whether a run was attempted and failed (the caller sends the person to the run page)."""
    if not placed:
        return False
    if mode() == "automatic" and _RUN.get("run"):
        ok = _RUN["run"](who, f"override.{point}")
        if ok:
            session.say(f"{placed_says} — recalculated: every stage after it reads it now", True)
        return not ok
    session.say(f"{placed_says} — recalculation is manual: the stages after it read behind until someone recalculates (Plan administration → Stages)", True)
    return False


# ── the port ────────────────────────────────────────────────────────────────────────────────────────────────────────────

def pair(src: dict, dst: dict) -> tuple[bool, str, str]:
    """Whether overrides may port from `src` into `dst`, and what kind of port it is: a sandbox into the Plan it was named
    from, or a Plan into the next — a Plan with a later from point, for the periods it still plans."""
    if not src or not dst or src.get("version_kind") == "actual" or dst.get("version_kind") == "actual":
        return False, "two Plans", ""
    if src["version_id"] == dst["version_id"]:
        return False, "a Plan does not port into itself", ""
    if src.get("base_version") == dst["version_id"] and src.get("from_period") == dst.get("from_period"):
        return True, f"a sandbox into the Plan it was named from", "sandbox"
    if (dst.get("from_period") or "") > (src.get("from_period") or ""):
        return True, f"into the next Plan, for the periods it still plans — after {dst['from_period']}", "next"
    if dst.get("base_version") == src["version_id"] and dst.get("from_period") == src.get("from_period"):
        return False, f"{dst['version_id']} is a sandbox of {src['version_id']}: nothing ports into a sandbox", ""
    return False, f"{src['version_id']} → {dst['version_id']}: a sandbox ports into the Plan it was named from, a Plan into one with a later from point", ""


def _num(x):
    try:
        return None if x in (None, "") else float(x)
    except (TypeError, ValueError):
        return None


def _same(a: dict, b: dict, values: list[str]) -> bool:
    return all((_num(a.get(v)) is None and _num(b.get(v)) is None) or
               (_num(a.get(v)) is not None and _num(b.get(v)) is not None and abs(_num(a[v]) - _num(b[v])) < 1e-9) for v in values)


def offer(src: dict, dst: dict, kind: str) -> list[dict]:
    """Every override the port offers, with what the receiving Plan holds on its cell: `port` (nothing there), `clash` (a
    different override stands), `same` (the same figure already stands — not ported again). A sandbox offers what was
    typed on it since it was named; a Plan offers every override standing on it in the periods the next still plans."""
    out = []
    plan_through = dst.get("plan_through") or ""
    for p in points(ported_only=True):
        rows = q(f"select b.* from bronze.{p['register']} b join {p['act_model']} a on a.act_id = b.act_id where b.version_id = ?", src["version_id"])
        held = {tuple(str(r[c]) for c in p["cells"]): r for r in q(f"select * from {p['act_model']} where version_id = ?", dst["version_id"])}
        now = {tuple(str(r[c]) for c in p["cells"]): r for r in q(NOW[p["point"]], dst["version_id"])} if p["point"] in NOW else {}
        for r in rows:
            if kind == "sandbox" and (r.get("copied_from") or ""):
                continue                                   # a copy of the Plan's own override, not the sandbox's
            per = str(r.get("period") or "")
            if per <= (dst.get("from_period") or "") or (plan_through and per > plan_through):
                continue                                   # not a period the receiving Plan plans
            key = tuple(str(r[c]) for c in p["cells"])
            h = held.get(key)
            status = "port" if not h else ("same" if _same(r, h, p["values"]) else "clash")
            out.append({"id": f"{p['point']}|{r['act_id']}", "point": p["point"], "point_name": p["point_name"], "stage": p["stage"], "verb": p["verb"],
                        "register": p["register"], "act_id": r["act_id"], "cell": dict(zip(p["cells"], key)), "figures": {v: _num(r.get(v)) for v in p["values"]},
                        "by": r.get("entered_by"), "at": str(r.get("entered_at") or "")[:16].replace("T", " "), "reason": r.get("reason"),
                        "held": ({v: _num(h.get(v)) for v in p["values"]} | {"by": h.get("entered_by"), "reason": h.get("reason"), "act_id": h.get("act_id")}) if h else None,
                        "now": now.get(key) or {}, "status": status, "row": r})
    return out


PAGE = """{% macro n(x) %}{{ '{:,.0f}'.format(x) if x|abs >= 100 else '{:,.4g}'.format(x) }}{% endmacro %}<h1>Port<small>{{ dst_code }} · overrides move into a Plan only by a port — calculated figures never; the receiving Plan calculates its own</small></h1>
<p class="hint">Work is done in a sandbox — a what-if named from its Plan on <a href="{{ url_for('plan.versions') }}">Plans</a>, carrying its code with a letter — so one planner's working moves neither the Plan nor anyone else's sandbox. A port carries the overrides typed there into the Plan it was named from; or a Plan's overrides into the next Plan, for the periods it still plans. Each ports as the figure typed and reads against the receiving Plan's own calculated figure. Where the Plan already holds a different figure on the cell, both are shown and you choose.</p>
<form class="toolbar" method="get" action="{{ url_for('plan.port') }}"><label>from <select name="from">{% for v in plans %}<option value="{{ v.version_id }}" {{ 'selected' if v.version_id == src_id }}>{{ v.version_id|plan }} · {{ v.status }}</option>{% endfor %}</select></label>
<label>into <select name="to">{% for v in plans %}<option value="{{ v.version_id }}" {{ 'selected' if v.version_id == dst_id }}>{{ v.version_id|plan }} · {{ v.status }}</option>{% endfor %}</select></label> <button class="act">show</button></form>
<p class="{{ 'hint' if ok else 'no' }}">{{ src_code }} → {{ dst_code }}: {{ pair_says }}.{% if ok and dst_status != 'open' %} {{ dst_code }} is {{ dst_status }} — nothing ports into it.{% endif %}</p>
{% if ok %}<form method="post" action="{{ url_for('plan.port_act') }}"><input type="hidden" name="from" value="{{ src_id }}"><input type="hidden" name="to" value="{{ dst_id }}">
<table><thead><tr><th><input type="checkbox" checked onclick="document.querySelectorAll('input[name=take]').forEach(x=>{if(!x.disabled)x.checked=this.checked})" aria-label="all"></th><th>Override</th><th>Cell</th><th class="n">Typed</th><th>By · why</th><th class="n">{{ dst_code }} calculates</th><th>{{ dst_code }} holds</th></tr></thead><tbody>
{% for r in rows %}<tr class="{{ 'off' if r.status == 'same' }}"><td>{% if r.status != 'same' %}<input type="checkbox" name="take" value="{{ r.id }}" {{ 'checked' if r.may }} {{ 'disabled' if not r.may }}>{% endif %}</td>
<td>{{ r.point_name }}<div class="small muted">{{ r.stage_name }}</div></td><td class="small">{{ r.cell.values()|join(' · ') }}</td>
<td class="n">{% for k, x in r.figures.items() if x is not none %}{{ n(x) }} <span class="small muted">{{ k.replace('_', ' ') }}</span><br>{% endfor %}</td>
<td class="small">{{ r.by }} · {{ r.at }}<div class="muted">{{ r.reason or '' }}</div>{% if not r.may %}<div class="no">ported by {{ r.holders }}</div>{% endif %}</td>
<td class="n small">{% for k, x in r.now.items() if k.startswith('calc_') and x is not none %}{{ n(x) }}{% else %}<span class="muted">as it stands: {% for k, x in r.now.items() if k.startswith('now_') and x is not none %}{{ n(x) }} {% endfor %}</span>{% endfor %}</td>
<td class="small">{% if r.status == 'port' %}<span class="muted">no override — the calculated figure</span>{% elif r.status == 'same' %}the same figure already stands — not ported again{% else %}
<b>a different override:</b> {% for k in r.figures %}{% if r.held[k] is not none %}{{ n(r.held[k]) }} {% endif %}{% endfor %}<span class="muted">by {{ r.held.by }} — {{ r.held.reason or '' }}</span>
<div><label><input type="radio" name="choose:{{ r.id }}" value="keep" checked> keep {{ dst_code }}'s</label> <label><input type="radio" name="choose:{{ r.id }}" value="take"> take the ported</label></div>{% endif %}</td></tr>
{% else %}<tr><td colspan="7" class="muted">{{ src_code }} holds no override to port into {{ dst_code }}{{ ' — a sandbox ports what was typed on it since it was named' if kind == 'sandbox' }}.</td></tr>{% endfor %}</tbody></table>
{% if rows and dst_status == 'open' %}<div class="actions"><input name="reason" required size="40" placeholder="why these go into {{ dst_code }}"> <button class="primary" onclick="this.textContent='Porting…'">Port</button>
<span class="hint">recalculation is {{ mode }}{{ ': every stage after the overrides recalculates at once' if mode == 'automatic' else ': the stages after them read behind until someone recalculates' }}</span></div>{% endif %}</form>{% endif %}
<h2>Override points<span class="count">where the model lets a person's figure replace the calculated one — the only figures a port carries</span></h2>
<table><thead><tr><th>Stage</th><th>Override</th><th>Replaces</th><th>Typed on</th><th>Typed by</th><th>Ports</th></tr></thead><tbody>
{% for p in all_points %}<tr><td class="small">{{ p.stage_name }}</td><td>{{ p.point_name }}</td><td class="small">{{ p.replaces }}</td><td class="small">{{ p.typed_on }}</td><td class="small">{{ p.holders }}</td><td class="small">{{ 'yes' if p.ports else p.port_says }}</td></tr>{% endfor %}</tbody></table>
<p class="hint">A demand plan entry is a line on a layer of the stack, not a figure that replaces a calculated one, and the opex schedule's typed month an adjustment on top of its driver: neither is an override point.</p>
{% if last %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else ('!' if c.flag else '✕') }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}"""


def register(bp, page, who_fn, ctx_fn, busy, session, roles, run_plan, scoped: dict) -> None:
    from . import reads
    from .versions import LANDING as VERSION_ACTS
    _RUN["run"] = run_plan
    try:
        pts = points()
    except Exception:                                           # the warehouse is not built yet: the scopes come with it
        pts = []
    for p in pts:
        scoped[f"override.{p['point']}"] = {
            "commands": [["uv", "run", "python", "-m", "ingest.pipeline", "--only", p["register"]],
                         ["uv", "run", "sqlmesh", "plan", "prod", "--restate-model", f"{p['act_model']}+", "--auto-apply", "--no-prompts"]],
            "pending": LogLanding("plan", p["register"], []).pending, "what": p["point_name"].lower(),
            "says": "run completed — every stage after the override reads it"}
    ported = [p for p in pts if p["ports"]]
    port_pending = lambda: [f for p in ported for f in LogLanding("plan", p["register"], []).pending()] + VERSION_ACTS.pending()
    scoped["port"] = {"commands": [["uv", "run", "python", "-m", "ingest.pipeline", "--only", *[p["register"] for p in ported], "reg_version_act"],
                                   ["uv", "run", "sqlmesh", "plan", "prod", *[x for p in ported for x in ("--restate-model", f"{p['act_model']}+")],
                                    "--restate-model", "plan.version_act+", "--auto-apply", "--no-prompts"]],
                      "pending": port_pending, "what": "port", "says": "run completed — the Plan reads the ported overrides and every stage after them is recalculated"}
    scoped["recalc_setting"] = {"commands": [["uv", "run", "python", "-m", "ingest.pipeline", "--only", "reg_recalc_setting"],
                                             ["uv", "run", "sqlmesh", "plan", "prod", "--restate-model", "plan.recalc_setting", "--auto-apply", "--no-prompts"]],
                                "pending": SETTING.pending, "what": "recalculation setting", "says": "run completed — the setting is in force"}

    def plans() -> list[dict]:
        return [v for v in reads.versions() if v.get("version_kind") != "actual"]

    def ends(args) -> tuple[dict, dict]:
        vs = {v["version_id"]: v for v in plans()}
        src = vs.get(args.get("from") or ctx_fn().get("version") or reads.default_version() or "") or {}
        dst_id = args.get("to") or ""
        if not dst_id and src:                                  # a sandbox ports into its Plan; a Plan into the next one
            dst_id = src.get("base_version") if src.get("base_version") in vs and vs[src["base_version"]].get("from_period") == src.get("from_period") else \
                next((v["version_id"] for v in sorted(vs.values(), key=lambda v: v.get("from_period") or "") if (v.get("from_period") or "") > (src.get("from_period") or "")), "")
        return src, vs.get(dst_id) or {}

    @bp.get("/port")
    def port():
        try:
            who = who_fn(); src, dst = ends(request.args)
            ok, says, kind = pair(src, dst)
            stage_name = {r["stage"]: r["stage_name"] for r in q("select stage, stage_name from dims.ref_stage")}
            rows = [{**r, "stage_name": stage_name.get(r["stage"]), "may": roles.may(who, r["verb"]),
                     "holders": ", ".join(reads.holders(r["verb"])) or "nobody yet"} for r in (offer(src, dst, kind) if ok else [])]
            allp = [{**p, "stage_name": stage_name.get(p["stage"]), "holders": ", ".join(reads.holders(p["verb"])) or "nobody yet"} for p in points()]
            codes = reads.plan_codes()
            plan_code = lambda v: codes.get(v["version_id"], (v["version_id"],))[0] if v else "—"
            return page(PAGE, title="Port", active="port", width="none", plans=plans(), src_id=src.get("version_id"), dst_id=dst.get("version_id"),
                        src_code=plan_code(src), dst_code=plan_code(dst), ok=ok, pair_says=says, kind=kind, rows=rows, dst_status=dst.get("status", "unknown"),
                        all_points=allp, mode=mode(), last=session.last, receipt_acts=("port",))
        except Busy as e:
            return busy("Port", e)

    @bp.post("/port")
    def port_act():
        f = request.form; who = who_fn(); reason = (f.get("reason") or "").strip()
        src, dst = ends(f)
        ok, says, kind = pair(src, dst)
        rows = {r["id"]: r for r in (offer(src, dst, kind) if ok else [])}
        chosen = [rows[i] for i in f.getlist("take") if i in rows and rows[i]["status"] != "same"]
        kept = [r for r in chosen if r["status"] == "clash" and f.get(f"choose:{r['id']}") != "take"]
        going = [r for r in chosen if r not in kept]
        refused = [r for r in going if not roles.may(who, r["verb"])]
        unknown = [i for i in f.getlist("take") if i not in rows]
        checks = [
            {"check": "a port", "ok": ok, "says": f"{src.get('version_id', '—')} → {dst.get('version_id', '—')}: {says}"},
            {"check": "the receiving Plan is open", "ok": dst.get("status") == "open", "says": f"{dst.get('version_id', '—')} is {dst.get('status', 'unknown')}"},
            {"check": "overrides chosen", "ok": bool(going) and not unknown,
             "says": (f"{len(going)} to port" + (f" · {len(kept)} clash{'es' if len(kept) != 1 else ''} kept as {dst.get('version_id')} holds them" if kept else "")
                      + (f" · {sum(1 for r in rows.values() if r['status'] == 'same')} already standing, not ported again" if any(r['status'] == 'same' for r in rows.values()) else ""))
                     if going and not unknown else (f"{len(unknown)} chosen no longer offered — show the port again" if unknown else "nothing chosen to port")},
            {"check": "who ports them", "ok": not refused,
             "says": f"{who} holds the right of every override chosen" if not refused else
                     "; ".join(sorted({f"{r['point_name']} is ported by holders of {said(r['verb'])}" for r in refused}))},
            {"check": "a reason", "ok": bool(reason), "says": reason or "a port says why"},
        ]
        placed = receipts.judge(checks)
        if placed:
            now = dt.datetime.now(); stamp = f"{now:%Y%m%d%H%M%S%f}"; when = now.isoformat(timespec="seconds")
            by_point: dict[str, list[dict]] = {}
            for i, r in enumerate(going, start=1):
                src_row = {k: v for k, v in r["row"].items() if not k.startswith("_dlt") and k not in ("source_file", "file_row_number")}
                prefix = (r["act_id"].split("-")[0] or "ACT")
                by_point.setdefault(r["point"], []).append({**src_row, "act_id": f"{prefix}-{stamp}-P{i:03d}", "action": "set", "withdraws": "",
                                                            "version_id": dst["version_id"], "entered_by": who, "entered_at": when,
                                                            "copied_from": "", "ported_from": r["act_id"]})
            for p in points(ported_only=True):
                if by_point.get(p["point"]):
                    landing(p).place(by_point[p["point"]], who)
            VERSION_ACTS.place([{"act_id": f"VA-{now.strftime('%Y%m%d-%H%M%S-%f')}", "version_id": dst["version_id"], "act": "port",
                                 "reason": f"{reason} — {len(going)} override{'s' if len(going) != 1 else ''} from {src['version_id']}"
                                           + (f", {len(kept)} of {dst['version_id']}'s kept" if kept else ""),
                                 "entered_by": who, "entered_on": when, "horizon_periods": "", "base_version": src["version_id"]}], who)
        session.last = receipts.write("port", who, f"{src.get('version_id')}>{dst.get('version_id')}", checks, placed)
        back = redirect(url_for("plan.port", **{"from": src.get("version_id") or "", "to": dst.get("version_id") or ""}))
        if not placed:
            session.say("not ported: " + "; ".join(c["says"] for c in checks if not c["ok"]), False)
            return back
        if mode() == "automatic":
            if run_plan(who, "port"):
                session.say(f"{len(going)} override{'s' if len(going) != 1 else ''} ported into {dst['version_id']} — recalculated", True)
                return back
            return redirect(url_for("plan.run"))
        session.say(f"{len(going)} override{'s' if len(going) != 1 else ''} ported into {dst['version_id']} — recalculation is manual: the stages after them read behind until someone recalculates", True)
        return back

    @bp.post("/stages/recalc_setting")
    def recalc_setting():
        f = request.form; who = who_fn(); m, reason = f.get("mode") or "", (f.get("reason") or "").strip()
        may = roles.may(who, SETTING_VERB)
        checks = [
            {"check": "who keeps the setting", "ok": may, "says": f"{who} holds {said(SETTING_VERB)}" if may else f"{who} does not hold {said(SETTING_VERB)}"},
            {"check": "automatic or manual", "ok": m in ("automatic", "manual"), "says": m or "automatic or manual"},
            {"check": "a change", "ok": m != mode(), "says": f"{mode()} → {m}" if m != mode() else f"recalculation is {m} already"},
            {"check": "a reason", "ok": bool(reason), "says": reason or "a setting says why"},
        ]
        placed = receipts.judge(checks)
        if placed:
            now = dt.datetime.now()
            SETTING.place([{"act_id": f"RCS-{now:%Y%m%d%H%M%S%f}", "mode": m, "reason": reason, "entered_by": who,
                            "entered_at": now.isoformat(timespec="seconds")}], who)
        session.last = receipts.write("stage.recalc_setting", who, m, checks, placed)
        if not placed:
            session.say("refused: " + "; ".join(x["says"] for x in checks if not x["ok"]), False)
            return redirect(url_for("plan.stages") + "#setting")
        if run_plan(who, "recalc_setting"):
            session.say(f"recalculation is {m} on every Plan", True)
            return redirect(url_for("plan.stages") + "#setting")
        return redirect(url_for("plan.run"))

    @bp.post("/stages/recalculate")
    def recalculate():
        """Manual recalculation, asked for: the whole run, by a holder of run.plan — every stage behind reads what was placed."""
        who = who_fn()
        if not roles.may(who, RUN_VERB):
            session.say(f"{who} does not hold {said(RUN_VERB)} — the plan is recalculated by {', '.join(reads.holders(RUN_VERB)) or 'nobody yet'}", False)
            return redirect(url_for("plan.stages"))
        if run_plan(who, ""):
            return redirect(url_for("plan.stages"))
        return redirect(url_for("plan.run"))
