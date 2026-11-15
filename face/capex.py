"""Projects and depreciation (DEC-20261115-01): the capital plan on a version — the assets as loaded, the projects with
their spend and in-service dates, the sustaining rates, the leases — walked into cash out, additions, depreciation and
book value by the run (`plan.capex_line`, over `calc/capex.py`), and charged to the opex schedule (`plan.capex_charge`).

Planned, not approved: an item is entered by a holder of the project-entry right at its cost centre and is in the plan
after the run — there is no gate. A withdrawal is a later row naming the item; nothing is deleted.

Registered on the plan's blueprint by `register(...)`, called once from `face/__main__.py`."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

from chassis import receipts
from chassis.landing import LogLanding
from chassis.warehouse import Busy, q
from flask import redirect, request, url_for

from calc.capex import check_item

from .words import said

VERB = "capex.project.enter"
COLUMNS = ["act_id", "action", "withdraws", "version_id", "kind", "item_id", "item_name", "project_kind", "asset_class", "entity_code",
           "cost_centre_code", "plant_code", "spend", "spend_from", "spend_to", "in_service_period", "life_years", "lifetime_units", "rate",
           "lease_charge", "lease_to_period", "tier", "note", "entered_by", "entered_on", "copied_from"]
LANDING = LogLanding("plan", "reg_capex", COLUMNS)
RUN = [["uv", "run", "python", "-m", "ingest.pipeline", "--only", "reg_capex"],
       ["uv", "run", "sqlmesh", "plan", "prod", "--restate-model", "plan.capex_item+", "--auto-apply", "--no-prompts"]]
KIND_SAYS = {"asset": "on the register", "project": "project", "sustaining": "sustaining rate", "lease": "lease"}
PLANT_OF = {"CC_E_": "ECH", "CC_L_": "LOX"}

PAGE = """<h1>Projects and depreciation<small>{{ version }} · FY{{ fy }} · the assets as loaded, the projects, the sustaining rates and the leases — cash out, depreciation and book value</small></h1>
<div class="cards"><div class="card stat"><b>{{ tot.spend|aud }}</b><span>capital spend in FY{{ fy }}'s plan periods · the cash step's capex</span></div>
<div class="card stat"><b>{{ tot.dep|aud }}</b><span>depreciation · {{ tot.dep_factory|aud }} of it at factory cost centres — fixed factory overhead, cost of goods</span></div>
<div class="card stat"><b>{{ tot.lease|aud }}</b><span>lease charges · {{ tot.lease_factory|aud }} at factory cost centres</span></div>
<div class="card stat"><b>{{ tot.close|aud }}</b><span>book value at the end of {{ last_p }}</span></div></div>
{% if not plan_p %}<p class="hint">{{ version }} plans no period in FY{{ fy }}.</p>{% endif %}
<p class="hint">Every charge here lands on the <a href="{{ url_for('plan.schedule') }}">opex schedule</a> — depreciation on 6750, lease charges on 6700 — at its cost centre, as a line the schedule does not type. At a factory cost centre it is fixed factory overhead, and goes to cost of goods with the standard; elsewhere it is a period cost. Nothing here is approved: an item is in the plan from the run after it is entered.</p>
<h2>Book value by class<span class="count">FY{{ fy }}'s plan periods, {{ plan_p[0] if plan_p else '' }}–{{ last_p }}</span></h2>
<table><thead><tr><th>Class</th><th>Method</th><th class="n">Opening</th><th class="n">Additions</th><th class="n">Depreciation</th><th class="n">Closing</th></tr></thead><tbody>
{% for c in by_class %}<tr><td>{{ c.class_name }}</td><td class="small">{{ c.method_says }}</td><td class="n">{{ c.opening|aud }}</td><td class="n">{{ c.additions|aud }}</td><td class="n">{{ c.depreciation|aud }}</td><td class="n">{{ c.closing|aud }}</td></tr>{% endfor %}
<tr class="total"><td colspan="2">Total</td><td class="n">{{ tot.open|aud }}</td><td class="n">{{ tot.add|aud }}</td><td class="n">{{ tot.dep|aud }}</td><td class="n">{{ tot.close|aud }}</td></tr></tbody></table>
<h2>Projects<span class="count">spend even over its periods, capitalised whole when it goes into service, depreciated from then</span></h2>
<table><thead><tr><th>Project</th><th>Kind</th><th>Class</th><th>Cost centre</th><th class="n">Spend</th><th>Spend</th><th>In service</th><th>Life</th><th>The tier it steps</th><th class="n">FY{{ fy }} cash</th><th class="n">FY{{ fy }} depreciation</th><th></th></tr></thead><tbody>
{% for i in items if i.kind == 'project' %}<tr><td>{{ i.item_name }} <span class="small muted">{{ i.item_id }}</span>{% if i.note %}<div class="small muted">{{ i.note }}</div>{% endif %}</td><td class="small">{{ i.project_kind or '' }}</td><td class="small">{{ i.class_name }}</td><td class="small">{{ i.cost_centre_code }} · {{ i.entity_code }}</td>
<td class="n">{{ i.spend|aud }}</td><td class="small">{{ i.spend_from }}–{{ i.spend_to }}</td><td class="small">{{ i.in_service_period }}</td><td class="small">{{ i.life_says }}</td><td class="small">{{ i.tier or '' }}</td><td class="n">{{ i.fy_spend|aud }}</td><td class="n">{{ i.fy_dep|aud }}</td><td>{{ withdraw(i) }}</td></tr>{% else %}<tr><td colspan="12" class="muted">No project on {{ version }}.</td></tr>{% endfor %}</tbody></table>
<h2>Sustaining<span class="count">a rate a year on the gross cost of the cost centre's assets, spent each period and in service as spent</span></h2>
<table><thead><tr><th>Item</th><th>Class</th><th>Cost centre</th><th class="n">Rate a year</th><th class="n">FY{{ fy }} spend</th><th class="n">FY{{ fy }} depreciation</th><th></th></tr></thead><tbody>
{% for i in items if i.kind == 'sustaining' %}<tr><td>{{ i.item_name }}{% if i.note %}<div class="small muted">{{ i.note }}</div>{% endif %}</td><td class="small">{{ i.class_name }}</td><td class="small">{{ i.cost_centre_code }} · {{ i.entity_code }}</td><td class="n">{{ i.rate|pct1 }}</td><td class="n">{{ i.fy_spend|aud }}</td><td class="n">{{ i.fy_dep|aud }}</td><td>{{ withdraw(i) }}</td></tr>{% else %}<tr><td colspan="7" class="muted">No sustaining rate on {{ version }}.</td></tr>{% endfor %}</tbody></table>
<h2>Leases<span class="count">a fixed charge a period over the term — no cash at the start, no asset, no liability</span></h2>
<table><thead><tr><th>Lease</th><th>Cost centre</th><th class="n">A period</th><th>Term</th><th>The tier it steps</th><th class="n">FY{{ fy }} charge</th><th></th></tr></thead><tbody>
{% for i in items if i.kind == 'lease' %}<tr><td>{{ i.item_name }}{% if i.note %}<div class="small muted">{{ i.note }}</div>{% endif %}</td><td class="small">{{ i.cost_centre_code }} · {{ i.entity_code }}</td><td class="n">{{ i.lease_charge|aud }}</td><td class="small">{{ i.in_service_period }}–{{ i.lease_to_period or 'open' }}</td><td class="small">{{ i.tier or '' }}</td><td class="n">{{ i.fy_lease|aud }}</td><td>{{ withdraw(i) }}</td></tr>{% else %}<tr><td colspan="7" class="muted">No lease on {{ version }}.</td></tr>{% endfor %}</tbody></table>
<h2>The register as loaded<span class="count">cost and accumulated depreciation at {{ as_at }}, from the ledgers</span></h2>
<table><thead><tr><th>Asset</th><th>Class</th><th>Cost centre</th><th class="n">Cost</th><th class="n">Accumulated</th><th class="n">Book value</th><th>In service</th><th class="n">FY{{ fy }} depreciation</th></tr></thead><tbody>
{% for a in assets %}<tr><td>{{ a.asset_name }} <span class="small muted">{{ a.asset_id }}</span></td><td class="small">{{ a.class_name }}{% if a.lifetime_units %} · {{ '{:,.0f}'.format(a.lifetime_units) }} cases over its life{% endif %}</td><td class="small">{{ a.cost_centre_code }} · {{ a.entity_code }}</td><td class="n">{{ a.cost|aud }}</td><td class="n">{{ a.accumulated|aud }}</td><td class="n">{{ (a.cost - a.accumulated)|aud }}</td><td class="small">{{ a.in_service_period }}</td><td class="n">{{ a.fy_dep|aud }}</td></tr>{% endfor %}</tbody></table>
<h2>Asset classes<span class="count">the method is declared per class</span></h2>
<table><thead><tr><th>Class</th><th>Method</th><th class="n">Life</th><th class="n">Residual</th></tr></thead><tbody>
{% for c in classes %}<tr><td>{{ c.class_name }}</td><td class="small">{{ c.method_says }}</td><td class="n">{{ '%g'|format(c.life_years) }} years</td><td class="n">{{ c.residual_pct|pct1 }}</td></tr>{% endfor %}</tbody></table>
<p class="hint">Straight-line: (cost − residual) ÷ (life × 12) a period, from the period it goes into service, never below residual. Units of production: (cost − residual) × the period's cases made at the plant ÷ the cases over its life — Caldera plans no production by line yet, so the plant's cases are the units. A tier named on an item is the capacity it steps; capacity is not yet planned, so the step is recorded, not read.</p>
{% if may_enter %}<h2 id="new">New item<span class="count">in the plan after the run; no approval</span></h2>
<form method="post" action="{{ url_for('plan.capex_enter') }}" class="form-row">
<label>kind<select name="kind"><option value="project">project</option><option value="sustaining">sustaining rate</option><option value="lease">lease</option></select></label>
<label class="grow">name<input name="item_name" required></label>
<label>project kind<select name="project_kind"><option value="growth">growth</option><option value="sustaining">sustaining</option></select></label>
<label>class<select name="asset_class">{% for c in classes %}<option value="{{ c.asset_class }}">{{ c.class_name }}</option>{% endfor %}</select></label>
<label>cost centre<select name="cc">{% for c in centres %}<option value="{{ c.entity_code }}|{{ c.code }}">{{ c.name }} · {{ c.entity_code }}</option>{% endfor %}</select></label>
<label>spend<input name="spend" inputmode="decimal" size="10"></label><label>spend from<select name="spend_from"><option></option>{% for p in plan_all %}<option>{{ p }}</option>{% endfor %}</select></label>
<label>spend to<select name="spend_to"><option></option>{% for p in plan_all %}<option>{{ p }}</option>{% endfor %}</select></label>
<label>in service<select name="in_service_period"><option></option>{% for p in plan_all %}<option>{{ p }}</option>{% endfor %}</select></label>
<label>life (years)<input name="life_years" size="4" placeholder="the class's"></label><label>lifetime cases<input name="lifetime_units" size="10" placeholder="units of production"></label>
<label>rate a year<input name="rate" size="5" placeholder="0.03"></label><label>charge a period<input name="lease_charge" size="8"></label>
<label>lease to<select name="lease_to_period"><option></option>{% for p in plan_all %}<option>{{ p }}</option>{% endfor %}</select></label>
<label class="grow">the tier it steps<input name="tier" placeholder="optional"></label><label class="grow">note<input name="note"></label>
<button class="primary">Enter</button></form>{% else %}<p class="hint">Items are entered by the holders of {{ verb_said }} at the cost centre: {{ holders|join(', ') or 'nobody yet' }}.</p>{% endif %}
{% if last and last.act and last.act.startswith('capex') %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else '✕' }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}"""

WITHDRAW = """{% macro withdraw(i) %}{% if i.may %}<form method="post" action="{{ url_for('plan.capex_withdraw') }}" class="inline"><input type="hidden" name="item_id" value="{{ i.item_id }}"><input name="reason" placeholder="reason" size="10" required><button class="act small">withdraw</button></form>{% endif %}{% endmacro %}"""

METHOD_SAYS = {"straight_line": "straight-line", "units_of_production": "units of production"}


def plant_of(cc: str) -> str:
    return next((p for k, p in PLANT_OF.items() if cc.startswith(k)), "")


def view(version: str, fy: int) -> dict:
    from . import reads
    vp = reads.version_periods(version)
    plan_all = vp["plan"]
    plan_p = [p for p in plan_all if int(p[:4]) == fy]
    classes = [{**c, "method_says": METHOD_SAYS.get(c["method"], c["method"])} for c in q("select * from dims.ref_asset_class order by ord")]
    cls = {c["asset_class"]: c for c in classes}
    lines = q("select * from plan.capex_line where version_id = ?", version)
    fy_lines = [l for l in lines if l["period"] in plan_p]
    factory = {r["cost_centre_code"] for r in q("select cost_centre_code from dims.dim_cost_centre where kind = 'factory'")}
    by_item: dict = defaultdict(lambda: {"fy_spend": 0.0, "fy_dep": 0.0, "fy_lease": 0.0})
    for l in fy_lines:
        b = by_item[l["item_id"]]
        b["fy_spend"] += l["spend"] or 0; b["fy_dep"] += l["depreciation"] or 0; b["fy_lease"] += l["lease_charge"] or 0
    by_class: dict = {}
    first, last = (plan_p[0], plan_p[-1]) if plan_p else ("", "")
    for l in fy_lines:
        if l["kind"] == "lease":
            continue
        c = by_class.setdefault(l["asset_class"], {**cls.get(l["asset_class"], {"class_name": l["asset_class"], "method_says": ""}),
                                                   "opening": 0.0, "additions": 0.0, "depreciation": 0.0, "closing": 0.0})
        c["additions"] += l["additions"] or 0; c["depreciation"] += l["depreciation"] or 0
        if l["period"] == first:
            c["opening"] += l["opening_nbv"] or 0
        if l["period"] == last:
            c["closing"] += l["closing_nbv"] or 0
    # an item that starts inside the year opens at nothing; one that ended before the year's end closes at what it left
    rows = sorted(by_class.values(), key=lambda c: c.get("ord") or 99)
    items = q("""select i.*, c.class_name from plan.capex_item i left join dims.ref_asset_class c using (asset_class)
                 where i.version_id = ? and i.standing = 'stands' order by i.kind, i.entered_on""", version)
    for i in items:
        i.update(by_item.get(i["item_id"], {"fy_spend": 0.0, "fy_dep": 0.0, "fy_lease": 0.0}))
        c = cls.get(i["asset_class"] or "", {})
        i["life_says"] = (f"{i['lifetime_units']:,.0f} cases" if c.get("method") == "units_of_production" and i.get("lifetime_units")
                          else f"{(i.get('life_years') or c.get('life_years') or 0):g} years")
    assets = q("""select a.*, c.class_name from dims.reg_asset a left join dims.ref_asset_class c using (asset_class) order by a.asset_id""")
    for a in assets:
        a["fy_dep"] = by_item.get(a["asset_id"], {}).get("fy_dep", 0.0)
    tot = {"spend": sum(l["spend"] or 0 for l in fy_lines), "dep": sum(l["depreciation"] or 0 for l in fy_lines),
           "dep_factory": sum(l["depreciation"] or 0 for l in fy_lines if l["cost_centre_code"] in factory),
           "lease": sum(l["lease_charge"] or 0 for l in fy_lines), "lease_factory": sum(l["lease_charge"] or 0 for l in fy_lines if l["cost_centre_code"] in factory),
           "open": sum(c["opening"] for c in rows), "add": sum(c["additions"] for c in rows), "close": sum(c["closing"] for c in rows)}
    return {"plan_p": plan_p, "plan_all": plan_all, "last_p": last, "classes": classes, "by_class": rows, "items": items, "assets": assets, "tot": tot,
            "as_at": assets[0]["as_at_period"] if assets else ""}


def register(bp, page, who_fn, ctx_fn, busy, session, roles, run_plan, scoped: dict) -> None:
    from . import costs, reads
    scoped["capex"] = {"commands": RUN, "pending": LANDING.pending, "what": "capital plan",
                       "says": "run completed — the capital plan, and the schedule lines it charges, read what was entered"}

    def _where() -> tuple[str, int]:
        c = ctx_fn()
        version = c.get("version") or reads.default_version()
        return version, int(c.get("fy") or (reads.version(version) or {}).get("fiscal_year") or 0)

    def _may(who: str, cc: str, version: str) -> bool:
        v = reads.version(version) or {}
        return v.get("status") == "open" and roles.may(who, VERB, cc, dimension="organisation", kind=v.get("version_kind"))

    @bp.get("/capex")
    def capex():
        try:
            who = who_fn(); version, fy = _where()
            s = view(version, fy)
            for i in s["items"]:
                i["may"] = _may(who, i["cost_centre_code"], version)
            centres = [{"code": c["code"], "name": c["name"], "entity_code": e["entity_code"]} for c in costs.planning_cost_centres()
                       if c["kind"] not in ("company", "function") for e in costs.entities() if _may(who, c["code"], version)
                       and q("select 1 ok from plan.cost_actual where cost_centre_code = ? and entity_code = ? limit 1", c["code"], e["entity_code"])]
            return page(WITHDRAW + PAGE, title="Projects and depreciation", active="capex", version=version, fy=fy, **s, centres=centres,
                        may_enter=bool(centres), holders=reads.holders(VERB), verb_said=said(VERB), last=session.last, receipt_acts=("capex",))
        except Busy as e:
            return busy("Projects and depreciation", e)

    def _place(who: str, row: dict, checks: list[dict], what: str):
        placed = receipts.judge(checks)
        stamp = dt.datetime.now()
        act_id = f"CX-{stamp.strftime('%Y%m%d-%H%M%S-%f')}"
        if placed:
            LANDING.place([{**{c: "" for c in COLUMNS}, **row, "act_id": act_id, "entered_by": who, "entered_on": stamp.isoformat(timespec="microseconds")}], who)
        session.last = receipts.write(f"capex.{what}", who, act_id, checks, placed)
        if not placed:
            session.say(f"{what} refused: " + "; ".join(c["says"] for c in checks if not c["ok"]), False)
            return redirect(url_for("plan.capex"))
        if run_plan(who, "capex"):
            session.say(f"{act_id} placed and in the plan — the capital plan and the schedule lines it charges are recalculated", True)
            return redirect(url_for("plan.capex"))
        return redirect(url_for("plan.run"))

    @bp.post("/capex/enter")
    def capex_enter():
        f = request.form; who = who_fn(); version, _ = _where()
        v = reads.version(version) or {}
        ent, _, cc = (f.get("cc") or "").partition("|")
        kind = f.get("kind") or ""
        stamp = dt.datetime.now().strftime("%Y%m%d%H%M%S")
        row = {"action": "enter", "version_id": version, "kind": kind, "item_id": f"{ {'project': 'P', 'sustaining': 'S', 'lease': 'L'}.get(kind, 'X') }-{stamp}",
               "item_name": (f.get("item_name") or "").strip(), "project_kind": f.get("project_kind") if kind == "project" else "",
               "asset_class": f.get("asset_class") if kind != "lease" else "", "entity_code": ent, "cost_centre_code": cc, "plant_code": plant_of(cc),
               "spend": f.get("spend") or "", "spend_from": f.get("spend_from") or "", "spend_to": f.get("spend_to") or "",
               "in_service_period": f.get("in_service_period") or "", "life_years": f.get("life_years") or "", "lifetime_units": f.get("lifetime_units") or "",
               "rate": f.get("rate") or "", "lease_charge": f.get("lease_charge") or "", "lease_to_period": f.get("lease_to_period") or "",
               "tier": (f.get("tier") or "").strip(), "note": (f.get("note") or "").strip()}
        vp = reads.version_periods(version)
        periods = [r["period"] for r in q("select period from dims.dim_period order by period")]
        plan_all = vp["plan"]
        classes = {c["asset_class"]: c for c in q("select * from dims.ref_asset_class")}
        checks = [{"check": "who may enter", "ok": _may(who, cc, version),
                   "says": f"{who} holds {said(VERB)} at {cc}" if _may(who, cc, version) else f"{who} does not hold {said(VERB)} at {cc or 'no cost centre'}"},
                  {"check": "version open", "ok": v.get("status") == "open", "says": f"{version} is {v.get('status', 'unknown')}"}]
        checks += check_item(row, classes, periods, plan_all)
        from .workflow import locked
        why = locked(version, "capital", cc) if cc else None
        checks.append({"check": "the cost centre's capital plan not handed over", "ok": not why, "says": why or "open"})
        return _place(who, row, checks, "enter")

    @bp.post("/capex/withdraw")
    def capex_withdraw():
        f = request.form; who = who_fn(); version, _ = _where()
        item = q("select * from plan.capex_item where version_id = ? and item_id = ? and standing = 'stands'", version, f.get("item_id") or "")
        it = item[0] if item else {}
        reason = (f.get("reason") or "").strip()
        checks = [{"check": "an item that stands", "ok": bool(it), "says": it.get("item_name") or f"{f.get('item_id')} is not an item standing on {version}"},
                  {"check": "who may withdraw", "ok": bool(it) and (_may(who, it["cost_centre_code"], version)),
                   "says": f"{who} holds {said(VERB)} at {it.get('cost_centre_code')}" if it and _may(who, it["cost_centre_code"], version) else f"{who} may not withdraw it"},
                  {"check": "a reason", "ok": bool(reason), "says": reason or "no reason given"}]
        row = {"action": "withdraw", "withdraws": it.get("item_id", ""), "version_id": version, "kind": it.get("kind", ""), "item_id": it.get("item_id", ""),
               "item_name": it.get("item_name", ""), "entity_code": it.get("entity_code", ""), "cost_centre_code": it.get("cost_centre_code", ""), "note": reason}
        return _place(who, row, checks, "withdraw")
