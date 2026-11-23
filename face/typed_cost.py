"""Typed over the drivers (DEC-20261116-02 point 7): a planned unit cost component typed where its drivers are missing —
a figure per case at a material × plant × period, by whoever holds Finance's entry right, an act on the record like any
other figure and withdrawn the same way. A typed component replaces its driver-based figure, is marked, and shows its
variance against the standard whole: it has no price and usage, or rate and efficiency, to split. Driver-based stays the
default; this tab of Standard by plant lists and counts what is typed.

Registered on the plan's blueprint by `register(...)`, called once from `face/__main__.py`."""
from __future__ import annotations

import datetime as dt

from chassis import receipts
from chassis.landing import LogLanding
from chassis.warehouse import Busy, q
from flask import redirect, request, url_for

from . import overrides
from .words import said

VERB = "overlay.finance.enter"
ACT_COLUMNS = ["act_id", "action", "withdraws", "version_id", "material_code", "plant_code", "period", "component", "per_case", "reason", "entered_by", "entered_at"]
ACTS = LogLanding("plan", "reg_unit_cost_act", ACT_COLUMNS)
COMPONENTS = [("material", "Material", "material_driven"), ("labour", "Labour", "labour_driven"),
              ("variable_overhead", "Variable overhead", "variable_driven"), ("fixed_overhead", "Fixed overhead", "fixed_driven")]

PAGE = """<h1>Typed over the drivers<small>{{ version|plan }} · a component of the planned unit cost typed where its drivers are missing — {{ typed|length }} standing</small></h1>
<p class="hint">The planned unit cost is rolled up from the model that holds each component. Where a component's drivers are missing — a bill not yet released, a route not yet timed — Finance types it per case at a material, its plant and a period: the typed figure replaces the driver-based one, is marked as typed, and its variance against the standard is read whole, with no price and usage or rate and efficiency to split. It is an act on the record: withdrawn here, the driver-based figure stands again after the next run. {% if may and is_open %}You type it.{% elif not is_open %}{{ version|plan }} is {{ status }} — nothing is typed on it.{% else %}Typed by {{ holders|join(', ') or 'nobody yet' }}.{% endif %}</p>
<table><thead><tr><th>Material</th><th>Plant</th><th>Period</th><th>Component</th><th class="n">Typed a case</th><th class="n">From the drivers</th><th class="n">Standard</th><th>Why</th><th>By</th><th></th></tr></thead><tbody>
{% for t in typed %}<tr><td>{{ t.material_name }} <span class="small muted">{{ t.material_code }}</span></td><td>{{ t.plant_code }}</td><td>{{ t.period }}</td><td>{{ t.component_label }}</td>
<td class="n"><b>{{ '%.4f'|format(t.per_case) }}</b> ◆</td><td class="n">{{ '%.4f'|format(t.driven) if t.driven is not none else '—' }}</td><td class="n">{{ '%.4f'|format(t.std) if t.std is not none else '—' }}</td>
<td class="small">{{ t.reason }}</td><td class="small">{{ t.entered_by }} · {{ t.entered_at[:10] }}</td>
<td>{% if may and is_open %}<form class="inline" method="post" action="{{ url_for('plan.unit_cost_withdraw') }}"><input type="hidden" name="act_id" value="{{ t.act_id }}"><input name="reason" required placeholder="why" size="10"> <button class="act">Withdraw</button></form>{% endif %}</td></tr>
{% else %}<tr><td colspan="10" class="muted">Nothing typed on {{ version|plan }}: every component is from its drivers.</td></tr>{% endfor %}</tbody></table>
{% if may and is_open %}<h2 id="type">Type a component<span class="count">a figure per case at a material's plant in a plan period</span></h2>
<form class="entry" method="post" action="{{ url_for('plan.unit_cost_type') }}">
<label class="wide">material<select name="material_code">{% for m in materials %}<option value="{{ m.material_code }}">{{ m.material_name }} · {{ m.plant_code }}</option>{% endfor %}</select></label>
<label>period<select name="period">{% for x in plan_periods %}<option>{{ x }}</option>{% endfor %}</select></label>
<label>component<select name="component">{% for c, label, _ in components %}<option value="{{ c }}">{{ label }}</option>{% endfor %}</select></label>
<label>per case<input name="per_case" type="number" step="any" min="0" required></label>
<label class="wide">why<input name="reason" required placeholder="what the drivers are missing"></label>
<div class="actions"><button class="primary">Save changes</button><span class="hint">by {{ who }} — in the plan after the next run</span></div></form>{% endif %}
{% if last %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else ('!' if c.flag else '✕') }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}"""


def register(bp, page, who_fn, ctx_fn, busy, session, roles) -> None:
    from . import reads

    def version_of() -> str:
        return ctx_fn().get("version") or reads.default_version()

    @bp.get("/standard/typed")
    def unit_cost_typed():
        try:
            who = who_fn(); version = version_of(); v = reads.version(version) or {}
            labels = {c: (label, col) for c, label, col in COMPONENTS}
            names = {r["material_code"]: r["material_name"] for r in q("select material_code, material_name from dims.dim_material")}
            typed = []
            for t in q("""select a.*, u.material_driven, u.labour_driven, u.variable_driven, u.fixed_driven,
                                 s.std_material, s.std_labour, s.std_variable, s.std_fixed
                          from plan.unit_cost_act a
                          left join plan.planned_unit_cost u on u.version_id = a.version_id and u.material_code = a.material_code and u.period = a.period
                          left join dims.dim_period p on p.period = a.period
                          left join plan.standard_cost s on s.material_code = a.material_code and s.plant_code = a.plant_code and s.fiscal_year = p.fiscal_year
                          where a.version_id = ? order by a.material_code, a.period, a.component""", version):
                label, col = labels[t["component"]]
                std_col = {"material": "std_material", "labour": "std_labour", "variable_overhead": "std_variable", "fixed_overhead": "std_fixed"}[t["component"]]
                typed.append({**t, "component_label": label, "driven": t[col], "std": t[std_col], "material_name": names.get(t["material_code"], t["material_code"])})
            materials = q("""select distinct u.material_code, m.material_name, u.plant_code from plan.planned_unit_cost u
                             join dims.dim_material m using (material_code) where u.version_id = ? order by m.material_name""", version)
            kind = v.get("version_kind")
            return page(PAGE, title="Standard by plant · Typed", active="std_typed", width="none", version=version, typed=typed, materials=materials,
                        components=COMPONENTS, plan_periods=reads.version_periods(version)["plan"], may=roles.may(who, VERB, kind=kind),
                        holders=reads.holders(VERB), is_open=v.get("status") == "open", status=v.get("status", "unknown"),
                        last=session.last, receipt_acts=("unit_cost",))
        except Busy as e:
            return busy("Typed over the drivers", e)

    @bp.post("/standard/typed/type")
    def unit_cost_type():
        f = request.form; who = who_fn(); version = version_of(); v = reads.version(version) or {}
        mat, period, comp = f.get("material_code") or "", f.get("period") or "", f.get("component") or ""
        reason = (f.get("reason") or "").strip()
        try:
            per_case = float(f.get("per_case") or "")
        except ValueError:
            per_case = None
        cell = q("select plant_code from plan.planned_unit_cost where version_id = ? and material_code = ? limit 1", version, mat)
        plan_periods = reads.version_periods(version)["plan"]
        may = roles.may(who, VERB, kind=v.get("version_kind"))
        checks = [
            {"check": "who may type it", "ok": may, "says": f"{who} holds {said(VERB)}" if may else f"{who} does not hold {said(VERB)} — typed by {', '.join(reads.holders(VERB))}"},
            {"check": "the plan is open", "ok": v.get("status") == "open", "says": f"{version} is {v.get('status', 'unknown')}"},
            {"check": "a material with a planned unit cost", "ok": bool(cell), "says": f"{mat} at {cell[0]['plant_code']}" if cell else f"{mat or 'nothing'} has no planned unit cost on {version}"},
            {"check": "a plan period", "ok": period in plan_periods, "says": period if period in plan_periods else f"{period or 'no period'} is not a plan period of {version} — an actual period takes nothing"},
            {"check": "a component", "ok": comp in {c for c, _, _ in COMPONENTS}, "says": comp or "material, labour, variable or fixed overhead"},
            {"check": "a figure per case", "ok": per_case is not None and per_case >= 0, "says": f"{per_case:,.4f} a case" if per_case is not None and per_case >= 0 else "a number, not below zero"},
            {"check": "a reason", "ok": bool(reason), "says": reason or "a typed figure says why its drivers are missing"},
        ]
        placed = receipts.judge(checks)
        if placed:
            now = dt.datetime.now()
            ACTS.place([{"act_id": f"UCA-{now:%Y%m%d%H%M%S%f}", "action": "set", "withdraws": "", "version_id": version, "material_code": mat,
                         "plant_code": cell[0]["plant_code"], "period": period, "component": comp, "per_case": per_case, "reason": reason,
                         "entered_by": who, "entered_at": now.isoformat(timespec="seconds")}], who)
        session.last = receipts.write("unit_cost.type", who, f"{mat}:{period}:{comp}", checks, placed)
        if overrides.released(who, "unit_cost", session, f"{mat} {comp} in {period} placed", placed):
            return redirect(url_for("plan.run"))
        if not placed:
            session.say("refused: " + "; ".join(x["says"] for x in checks if not x["ok"]), False)
        return redirect(url_for("plan.unit_cost_typed") + "#type")

    @bp.post("/standard/typed/withdraw")
    def unit_cost_withdraw():
        f = request.form; who = who_fn()
        act = q("select * from plan.unit_cost_act where act_id = ?", f.get("act_id") or "")
        reason = (f.get("reason") or "").strip()
        v = (reads.version(act[0]["version_id"]) or {}) if act else {}
        may = roles.may(who, VERB, kind=v.get("version_kind"))
        checks = [
            {"check": "who may withdraw it", "ok": may, "says": f"{who} holds {said(VERB)}" if may else f"{who} does not hold {said(VERB)}"},
            {"check": "a typed figure standing", "ok": bool(act), "says": f"{act[0]['act_id']}: {act[0]['material_code']} {act[0]['component']} in {act[0]['period']}" if act else "no such typed figure in force"},
            {"check": "the plan is open", "ok": v.get("status") == "open", "says": f"{v.get('version_id', '—')} is {v.get('status', 'unknown')}"},
            {"check": "a reason", "ok": bool(reason), "says": reason or "a withdrawal says why"},
        ]
        placed = receipts.judge(checks)
        if placed:
            now = dt.datetime.now(); a = act[0]
            ACTS.place([{"act_id": f"UCA-{now:%Y%m%d%H%M%S%f}", "action": "withdraw", "withdraws": a["act_id"], "version_id": a["version_id"],
                         "material_code": a["material_code"], "plant_code": a["plant_code"], "period": a["period"], "component": a["component"],
                         "per_case": "", "reason": reason, "entered_by": who, "entered_at": now.isoformat(timespec="seconds")}], who)
        session.last = receipts.write("unit_cost.withdraw", who, f.get("act_id") or "", checks, placed)
        if overrides.released(who, "unit_cost", session, "withdrawn — the driver-based figure stands again", placed):
            return redirect(url_for("plan.run"))
        if not placed:
            session.say("refused: " + "; ".join(x["says"] for x in checks if not x["ok"]), False)
        return redirect(url_for("plan.unit_cost_typed"))
