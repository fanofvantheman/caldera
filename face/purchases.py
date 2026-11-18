"""Material purchases (DEC-20261116-04): the purchase plan of the key raw materials and the stock it makes, on the IBP side
under Supply — requirement from production through the bill, purchases by their declared source with a price, stock and
its weighted-average cost by period, a buyer's typed quantity or price marked — and the same figures read only under
Financial planning → Cost of goods as *Material stock*, naming where they are planned. Finance takes them as given.

Registered on the plan's blueprint by `register(...)`, called once from `face/__main__.py`."""
from __future__ import annotations

import datetime as dt

from chassis import receipts
from chassis.landing import LogLanding
from chassis.warehouse import Busy, q
from flask import redirect, request, url_for

from . import overrides
from .words import said

VERB = "register.supply_plan.maintain"
ACT_COLUMNS = ["act_id", "action", "withdraws", "version_id", "input_code", "plant_code", "period", "quantity", "price", "reason", "entered_by", "entered_at"]
ACTS = LogLanding("plan", "reg_purchase_act", ACT_COLUMNS)
SOURCE_SAYS = {"contract": "contract — a price fixed, or tied to an index, for its term", "spot": "spot — the price in force with its index",
               "campaign": "campaign intake — bought in the input's window for what is needed until the next"}

PAGE = """<h1>{{ title }}<small>{{ version|plan }} · {{ where }} · {% if finance %}read only — planned under Integrated business planning → Supply → <a href="{{ url_for('plan.material_purchases') }}">Material purchases</a>; the costing takes the average cost as given{% else %}the key raw materials: requirement from production, purchases and their price, stock at a weighted average{% endif %}</small></h1>
<p class="hint">{% if finance %}Each key raw material's stock, valued at a monthly weighted average: the material cost of a case uses the average of the period it is consumed in. Every other input has no stock and is valued at its price in force.{% else %}Requirement is the cases the plant makes — the <a href="{{ url_for('plan.supply_plan') }}">supply plan</a>'s production requirement — × the bill × the plant's usage assumption. A purchase is calculated by its source: {% for k, v in source_says.items() %}<b>{{ v.split(' — ')[0] }}</b> — {{ v.split(' — ')[1] }}{{ '; ' if not loop.last else '.' }}{% endfor %} {% if may %}You plan purchases: type a quantity or a price over a period's calculated one — it is in the plan after the next run, marked ◆.{% else %}Purchases are planned by {{ holders|join(', ') or 'nobody yet' }}.{% endif %}{% endif %}</p>
<div class="cards">{% for c in cards %}<div class="card stat"><span>{{ c.label }}</span><b>{{ c.show }}</b><div class="small muted">{{ c.says }}</div></div>{% endfor %}</div>
{% for m in materials %}<h2 id="{{ m.input_code }}-{{ m.plant_code }}">{{ m.name }} · {{ m.plant_name }}<span class="count">{{ m.uom }} · {{ m.source_says }}{% if m.cover %} · cover {{ m.cover }} period{{ 's' if m.cover != 1 }}{% endif %}{% if m.note %} · {{ m.note }}{% endif %}</span></h2>
<div style="overflow-x:auto"><table class="stock"><thead><tr><th></th>{% for r in m.rows %}<th class="n">{{ r.period[2:4] }}·{{ r.period[5:] }}</th>{% endfor %}<th class="n">Total</th></tr></thead><tbody>
<tr><td>Requirement</td>{% for r in m.rows %}<td class="n">{{ q0(r.requirement) }}</td>{% endfor %}<td class="n">{{ q0(m.tot.requirement) }}</td></tr>
<tr><td>Opening</td>{% for r in m.rows %}<td class="n">{{ q0(r.opening_quantity) }}</td>{% endfor %}<td></td></tr>
<tr><td>Purchases</td>{% for r in m.rows %}<td class="n {{ 'typed' if r.quantity_typed }}">{{ q0(r.purchase_quantity) }}{% if r.quantity_typed %} ◆{% endif %}{% if r.source != m.source %}<span class="src">{{ r.source }}</span>{% endif %}</td>{% endfor %}<td class="n">{{ q0(m.tot.purchase_quantity) }}</td></tr>
<tr><td>Price</td>{% for r in m.rows %}<td class="n {{ 'typed' if r.price_typed }}">{{ p(r.purchase_price) }}{% if r.price_typed %} ◆{% endif %}</td>{% endfor %}<td></td></tr>
<tr><td>Purchases, value</td>{% for r in m.rows %}<td class="n">{{ q0(r.purchase_value) }}</td>{% endfor %}<td class="n">{{ q0(m.tot.purchase_value) }}</td></tr>
<tr class="avg"><td><b>Average cost</b></td>{% for r in m.rows %}<td class="n"><b>{{ p(r.average_cost) }}</b></td>{% endfor %}<td></td></tr>
<tr><td>Consumption, value</td>{% for r in m.rows %}<td class="n">{{ q0(r.consumption_value) }}</td>{% endfor %}<td class="n">{{ q0(m.tot.consumption_value) }}</td></tr>
<tr><td>Closing</td>{% for r in m.rows %}<td class="n {{ 'short' if r.short }}">{{ q0(r.closing_quantity) }}{% if r.short %} short{% endif %}</td>{% endfor %}<td></td></tr>
<tr><td>Closing, value</td>{% for r in m.rows %}<td class="n">{{ q0(r.closing_value) }}</td>{% endfor %}<td></td></tr>
</tbody></table></div>{% else %}<p class="muted">No key raw material at {{ where }}.</p>{% endfor %}
{% if others %}<p class="hint">Valued at the price in force, with no stock and no purchase line: {{ others|join(', ') }}.</p>{% endif %}
{% if not finance and may and is_open %}<h2 id="type">Type a purchase<span class="count">a quantity, a price or both over a period's calculated figures — the rest stays calculated</span></h2>
<form class="entry" method="post" action="{{ url_for('plan.purchase_type') }}">
<label class="wide">material at a plant<select name="key">{% for m in materials %}<option value="{{ m.input_code }}|{{ m.plant_code }}">{{ m.name }} · {{ m.plant_name }}</option>{% endfor %}</select></label>
<label>period<select name="period">{% for x in plan_periods %}<option>{{ x }}</option>{% endfor %}</select></label>
<label>quantity<input name="quantity" type="number" step="any" min="0" placeholder="leave blank to keep"></label>
<label>price<input name="price" type="number" step="any" min="0" placeholder="leave blank to keep"></label>
<label class="wide">why<input name="reason" required placeholder="the quote, the order, the change"></label>
<div class="actions"><button class="primary">Place</button><span class="hint">by {{ who }} — in the plan after the next run</span></div></form>{% endif %}
{% if typed %}<h2>Typed<span class="count">{{ typed|length }} standing on {{ version|plan }}</span></h2><table><thead><tr><th>Material</th><th>Plant</th><th>Period</th><th class="n">Quantity</th><th class="n">Price</th><th>Why</th><th>By</th><th></th></tr></thead><tbody>
{% for t in typed %}<tr><td>{{ t.input_code }}</td><td>{{ t.plant_code }}</td><td>{{ t.period }}</td><td class="n">{{ q0(t.quantity) if t.quantity is not none else '' }}</td><td class="n">{{ p(t.price) if t.price is not none else '' }}</td><td class="small">{{ t.reason }}</td><td class="small">{{ t.entered_by }}</td>
<td>{% if not finance and may and is_open %}<form class="inline" method="post" action="{{ url_for('plan.purchase_withdraw') }}"><input type="hidden" name="act_id" value="{{ t.act_id }}"><input name="reason" required placeholder="why" size="10"> <button class="act">Withdraw</button></form>{% endif %}</td></tr>{% endfor %}</tbody></table>{% endif %}
{% if last and not finance %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else ('!' if c.flag else '✕') }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}
<style>table.stock td{white-space:nowrap}table.stock td.typed{box-shadow:inset 0 0 0 1px var(--ink)}table.stock td.short{font-weight:600}table.stock .src{display:block;font-size:.7rem;color:var(--muted)}table.stock tr.avg td{border-top:1px solid var(--rule)}</style>"""
MACRO = """{% macro q0(x) %}{{ '' if x is none else '{:,.0f}'.format(x) }}{% endmacro %}{% macro p(x) %}{{ '' if x is none else ('{:,.4f}'.format(x) if x < 1 else '{:,.2f}'.format(x)) }}{% endmacro %}"""


def register(bp, page, who_fn, ctx_fn, busy, session, roles) -> None:
    from . import reads

    def view(finance: bool):
        c = ctx_fn(); who = who_fn()
        version = c.get("version") or reads.default_version()
        loc = c.get("location") or "ALL"
        v = reads.version(version) or {}
        rows = q("select * from plan.material_stock where version_id = ? order by input_code, plant_code, period", version)
        keys = {(k["input_code"], k["plant_code"]): k for k in q("select * from dims.ref_key_material")}
        names = {r["material_code"]: r for r in q("select material_code, material_name, base_uom from dims.dim_input_material")}
        plants = {r["node_code"]: r["node_name"] for r in q("select node_code, node_name from dims.dim_node")}
        mats: dict = {}
        for r in rows:
            if loc != "ALL" and r["plant_code"] != loc:
                continue
            k = keys.get((r["input_code"], r["plant_code"])) or {}
            m = mats.setdefault((r["input_code"], r["plant_code"]), {"input_code": r["input_code"], "plant_code": r["plant_code"],
                                                                   "name": (names.get(r["input_code"]) or {}).get("material_name", r["input_code"]),
                                                                   "uom": (names.get(r["input_code"]) or {}).get("base_uom", ""), "plant_name": plants.get(r["plant_code"], r["plant_code"]),
                                                                   "source": k.get("source"), "source_says": SOURCE_SAYS.get(k.get("source"), ""),
                                                                   "cover": k.get("cover_periods") or 0, "note": k.get("note"), "rows": []})
            m["rows"].append(r)
        for m in mats.values():
            m["tot"] = {x: sum(r[x] or 0 for r in m["rows"]) for x in ("requirement", "purchase_quantity", "purchase_value", "consumption_value")}
        others = sorted({names[i]["material_name"] for i in names if i not in {k[0] for k in keys}
                         and i in {r["component_material"] for r in q("select distinct component_material from dims.ref_bom")}
                         and names[i]["material_name"]} - set())
        typed = q("select * from plan.purchase_act where version_id = ? order by input_code, plant_code, period", version)
        buy = sum(r["purchase_value"] or 0 for m in mats.values() for r in m["rows"])
        close = [m["rows"][-1]["closing_value"] or 0 for m in mats.values() if m["rows"]]
        cards = [{"label": "Purchases", "show": f"${buy / 1e6:,.2f}M", "says": f"{len(mats)} key materials over {version}'s plan periods"},
                 {"label": "Stock at the end", "show": f"${sum(close) / 1e6:,.2f}M", "says": "the key materials' closing value at the last plan period"},
                 {"label": "Typed", "show": str(len(typed)), "says": "quantities or prices typed over the calculated ones"}]
        return page(MACRO + PAGE, title="Material stock" if finance else "Material purchases", active="material_stock" if finance else "purchases", width="none",
                    finance=finance, version=version, where=plants.get(loc, "both plants") if loc != "ALL" else "both plants", materials=list(mats.values()),
                    others=others, typed=typed, cards=cards, source_says=SOURCE_SAYS, may=roles.may(who, VERB), holders=reads.holders(VERB),
                    is_open=v.get("status") == "open", plan_periods=reads.version_periods(version)["plan"], last=session.last, receipt_acts=("purchase",))

    @bp.get("/supply/purchases")
    def material_purchases():
        try:
            return view(False)
        except Busy as e:
            return busy("Material purchases", e)

    @bp.get("/costs/material_stock")
    def material_stock():
        try:
            return view(True)
        except Busy as e:
            return busy("Material stock", e)

    def _num(x):
        try:
            return float(x) if x not in (None, "") else None
        except ValueError:
            return "bad"

    @bp.post("/supply/purchases/type")
    def purchase_type():
        f = request.form; who = who_fn(); c = ctx_fn()
        version = c.get("version") or reads.default_version()
        v = reads.version(version) or {}
        inp, _, plant = (f.get("key") or "").partition("|")
        period, reason = f.get("period") or "", (f.get("reason") or "").strip()
        qty, price = _num(f.get("quantity")), _num(f.get("price"))
        key = q("select * from dims.ref_key_material where input_code = ? and plant_code = ?", inp, plant)
        plan_periods = reads.version_periods(version)["plan"]
        ok_num = qty != "bad" and price != "bad" and (qty is not None or price is not None) and (qty or 0) >= 0 and (price is None or price > 0)
        checks = [
            {"check": "who may plan purchases", "ok": roles.may(who, VERB), "says": f"{who} holds {said(VERB)}" if roles.may(who, VERB) else f"{who} does not hold {said(VERB)} — purchases are planned by {', '.join(reads.holders(VERB))}"},
            {"check": "the plan is open", "ok": v.get("status") == "open", "says": f"{version} is {v.get('status', 'unknown')}"},
            {"check": "a key raw material", "ok": bool(key), "says": f"{inp} at {plant}" if key else f"{inp or 'nothing'} at {plant or '—'} is not a key raw material"},
            {"check": "a plan period", "ok": period in plan_periods, "says": period if period in plan_periods else f"{period or 'no period'} is not a plan period of {version}"},
            {"check": "a quantity or a price", "ok": ok_num, "says": " · ".join(x for x in [f"quantity {qty:,.0f}" if isinstance(qty, float) else "", f"price {price:,.4f}" if isinstance(price, float) else ""] if x) if ok_num else "a number for the quantity or the price, not below zero"},
            {"check": "a reason", "ok": bool(reason), "says": reason or "a purchase typed says why"},
        ]
        placed = receipts.judge(checks)
        if placed:
            now = dt.datetime.now()
            ACTS.place([{"act_id": f"PUR-{now:%Y%m%d%H%M%S%f}", "action": "set", "version_id": version, "input_code": inp, "plant_code": plant, "period": period,
                         "quantity": qty, "price": price, "reason": reason, "entered_by": who, "entered_at": now.isoformat(timespec="seconds")}], who)
        session.last = receipts.write("purchase.type", who, f"{inp}:{plant}:{period}", checks, placed)
        if overrides.released(who, "purchase", session, f"{inp} at {plant} in {period} placed", placed):
            return redirect(url_for("plan.run"))
        if not placed:
            session.say("refused: " + "; ".join(x["says"] for x in checks if not x["ok"]), False)
        return redirect(url_for("plan.material_purchases") + "#type")

    @bp.post("/supply/purchases/withdraw")
    def purchase_withdraw():
        f = request.form; who = who_fn()
        act = q("select * from plan.purchase_act where act_id = ?", f.get("act_id") or "")
        reason = (f.get("reason") or "").strip()
        v = reads.version(act[0]["version_id"]) if act else {}
        checks = [
            {"check": "who may plan purchases", "ok": roles.may(who, VERB), "says": f"{who} holds {said(VERB)}" if roles.may(who, VERB) else f"{who} does not hold {said(VERB)}"},
            {"check": "a typed figure standing", "ok": bool(act), "says": f"{act[0]['act_id']}: {act[0]['input_code']} at {act[0]['plant_code']} in {act[0]['period']}" if act else "no such typed figure in force"},
            {"check": "the plan is open", "ok": bool(v) and v.get("status") == "open", "says": f"{(v or {}).get('version_id', '—')} is {(v or {}).get('status', 'unknown')}"},
            {"check": "a reason", "ok": bool(reason), "says": reason or "a withdrawal says why"},
        ]
        placed = receipts.judge(checks)
        if placed:
            now = dt.datetime.now()
            ACTS.place([{"act_id": f"PUR-{now:%Y%m%d%H%M%S%f}", "action": "withdraw", "withdraws": act[0]["act_id"], "version_id": act[0]["version_id"],
                         "input_code": act[0]["input_code"], "plant_code": act[0]["plant_code"], "period": act[0]["period"], "reason": reason,
                         "entered_by": who, "entered_at": now.isoformat(timespec="seconds")}], who)
        session.last = receipts.write("purchase.withdraw", who, f.get("act_id") or "", checks, placed)
        if overrides.released(who, "purchase", session, "withdrawn — the calculated figure stands again", placed):
            return redirect(url_for("plan.run"))
        if not placed:
            session.say("refused: " + "; ".join(x["says"] for x in checks if not x["ok"]), False)
        return redirect(url_for("plan.material_purchases"))
