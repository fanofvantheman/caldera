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

from . import figures, overrides
from .figures import Filter, Measure
from .words import said

VERB = "register.supply_plan.maintain"
ACT_COLUMNS = ["act_id", "action", "withdraws", "version_id", "input_code", "plant_code", "period", "quantity", "price", "reason", "entered_by", "entered_at"]
ACTS = LogLanding("plan", "reg_purchase_act", ACT_COLUMNS)
# one table, a key raw material at its plant a row (DEC-20261119-05): the measures in the order the stock walks
MEASURES = [Measure("requirement", "requirement", total=False), Measure("opening_quantity", "opening", year="first", total=False),
            Measure("purchase_quantity", "purchases", typed="quantity_typed", note="source_note", input=True, total=False),
            Measure("purchase_price", "price", shown="price", year=None, typed="price_typed", input=True, total=False),
            Measure("purchase_value", "purchases, value", shown="money"), Measure("average_cost", "average cost", shown="price", year=None, total=False),
            Measure("consumption_value", "consumption, value", shown="money"), Measure("closing_quantity", "closing", year="last", note="short_note", total=False),
            Measure("closing_value", "closing, value", shown="money", year="last")]
SOURCE_SAYS = {"contract": "contract — a price fixed, or tied to an index, for its term", "spot": "spot — the price in force with its index",
               "campaign": "campaign intake — bought in the input's window for what is needed until the next"}

PAGE = """<h1>{{ title }}<small>{{ version|plan }} · {{ where }} · {% if finance %}read only — planned under Integrated business planning → Supply → <a href="{{ url_for('plan.material_purchases') }}">Material purchases</a>; the costing takes the average cost as given{% else %}the key raw materials: requirement from production, purchases and their price, stock at a weighted average{% endif %}</small></h1>
<p class="hint">{% if finance %}Each key raw material's stock, valued at a monthly weighted average: the material cost of a case uses the average of the period it is consumed in. Every other input has no stock and is valued at its price in force.{% else %}Requirement is the cases the plant makes — the <a href="{{ url_for('plan.supply_plan') }}">supply plan</a>'s production requirement — × the bill × the plant's usage assumption. A purchase is calculated by its source: {% for k, v in source_says.items() %}<b>{{ v.split(' — ')[0] }}</b> — {{ v.split(' — ')[1] }}{{ '; ' if not loop.last else '.' }}{% endfor %} {% if may %}You plan purchases: type a quantity or a price in its cell over the calculated one and place it with a reason — it is in the plan after the next run, boxed.{% else %}Purchases are planned by {{ holders|join(', ') or 'nobody yet' }}.{% endif %}{% endif %}</p>
<div class="cards">{% for c in cards %}<div class="card stat"><span>{{ c.label }}</span><b>{{ c.show }}</b><div class="small muted">{{ c.says }}</div></div>{% endfor %}</div>
{{ grid_choice(g) }}
{% if g.editable %}<form method="post" action="{{ url_for('plan.purchase_type') }}" id="type">{% for k in ('version', 'location') %}{% if request.args.get(k) %}<input type="hidden" name="{{ k }}" value="{{ request.args.get(k) }}">{% endif %}{% endfor %}{% endif %}
{{ grid_table(g) }}
{% if g.editable %}<div class="form-row"><label class="small grow">why <input name="reason" placeholder="the quote, the order, the change"></label><button class="primary">Place</button><span class="hint">each figure changed is placed as one act, by {{ who }} — in the plan after the next run</span></div></form>{% endif %}
<p class="hint">A row is a key raw material at the plant that holds it, in its own unit: the quantities of different materials do not add, so the first row totals the money only. A name's line says its unit, how it is bought and its cover. A row's other figures open beneath it, in the order the stock walks — requirement, opening, purchases, price, average cost, consumption, closing. The year is its plan periods: flows summed, the opening its first period's, the closing its last's; a price and an average are not added. A purchase bought other than by the material's source names its source beneath it; a closing below the cover is marked short. The stock walks from the Plan's first plan period: an actual period holds no stock figure here.</p>
{% if others %}<p class="hint">Valued at the price in force, with no stock and no purchase line: {{ others|join(', ') }}.</p>{% endif %}
{% if typed %}<h2>Typed<span class="count">{{ typed|length }} standing on {{ version|plan }}</span></h2><table><thead><tr><th>Material</th><th>Plant</th><th>Period</th><th class="n">Quantity</th><th class="n">Price</th><th>Why</th><th>By</th><th></th></tr></thead><tbody>
{% for t in typed %}<tr><td>{{ t.input_code }}</td><td>{{ t.plant_code }}</td><td>{{ t.period }}</td><td class="n">{{ q0(t.quantity) if t.quantity is not none else '' }}</td><td class="n">{{ p(t.price) if t.price is not none else '' }}</td><td class="small">{{ t.reason }}</td><td class="small">{{ t.entered_by }}</td>
<td>{% if not finance and may and is_open %}<form class="inline" method="post" action="{{ url_for('plan.purchase_withdraw') }}"><input type="hidden" name="act_id" value="{{ t.act_id }}"><input name="reason" required placeholder="why" size="10"> <button class="act">Withdraw</button></form>{% endif %}</td></tr>{% endfor %}</tbody></table>{% endif %}
{% if last and not finance %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else ('!' if c.flag else '✕') }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}
{{ grid_style() }}<style>.form-row{display:flex;flex-wrap:wrap;gap:.8rem;align-items:end;margin:.6rem 0}.form-row .grow{flex:1;display:flex;flex-direction:column}</style>"""

MACRO = """{% macro q0(x) %}{{ '' if x is none else '{:,.0f}'.format(x) }}{% endmacro %}{% macro p(x) %}{{ '' if x is none else ('{:,.4f}'.format(x) if x < 1 else '{:,.2f}'.format(x)) }}{% endmacro %}"""


def register(bp, page, who_fn, ctx_fn, busy, session, roles) -> None:
    from . import reads

    def view(finance: bool):
        c = ctx_fn(); who = who_fn()
        version = c.get("version") or reads.default_version()
        loc = c.get("location") or "ALL"
        v = reads.version(version) or {}
        stock = q("select * from plan.material_stock where version_id = ? order by input_code, plant_code, period", version)
        keys = {(k["input_code"], k["plant_code"]): k for k in q("select * from dims.ref_key_material")}
        names = {r["material_code"]: r for r in q("select material_code, material_name, material_type, base_uom from dims.dim_input_material")}
        plants = {r["node_code"]: r["node_name"] for r in q("select node_code, node_name from dims.dim_node")}
        # the categories whose materials' bill uses each input — what the category filter reads
        cats: dict = {}
        for r in q("""select distinct b.component_material i, h.ancestor_code c from dims.ref_bom b
                      join dims.dim_material_hierarchy h on h.descendant_code = b.parent_material and h.ancestor_level = 'category'"""):
            cats.setdefault(r["i"], set()).add(r["c"])
        cat_names = {ct: reads.node_label("material", ct) or ct for ct in {x for v in cats.values() for x in v}}
        rows: dict = {}
        for r in stock:
            if loc != "ALL" and r["plant_code"] != loc:
                continue
            k = keys.get((r["input_code"], r["plant_code"])) or {}
            nm = names.get(r["input_code"]) or {}
            row = rows.setdefault((r["input_code"], r["plant_code"]), {
                "code": f"{r['input_code']}~{r['plant_code']}", "label": nm.get("material_name") or r["input_code"],
                "level": " · ".join(x for x in [plants.get(r["plant_code"], r["plant_code"]), nm.get("base_uom") or "", (SOURCE_SAYS.get(k.get("source")) or "").split(" — ")[0],
                                                 f"cover {k['cover_periods']:g} period{'s' if k['cover_periods'] != 1 else ''}" if k.get("cover_periods") else "", k.get("note") or ""] if x),
                "attrs": {"plant": r["plant_code"], "type": nm.get("material_type") or "", "source": k.get("source") or "", "category": ""},
                "cats": cats.get(r["input_code"], set()), "source": k.get("source"), "by": {}, "rows": []})
            row["by"][r["period"]] = {**r, "source_note": r["source"] if r["source"] != row["source"] else None, "short_note": "short" if r["short"] else None,
                                      "typed_title": "typed over the calculated figure — listed under Typed"}
            row["rows"].append(r)
        # a category filter matches an input its materials' bill uses: the row carries the chosen category when it is one of its
        chosen_cat = request.args.get("f_category") or ""
        for row in rows.values():
            row["attrs"]["category"] = chosen_cat if chosen_cat in row["cats"] else ""
        used = sorted({ct for row in rows.values() for ct in row["cats"]}, key=lambda x: cat_names.get(x, x))
        filters = [Filter("plant", "plant", tuple((p, plants.get(p, p)) for p in sorted({r["attrs"]["plant"] for r in rows.values()}))),
                   Filter("category", "used by", tuple((ct, cat_names.get(ct, ct)) for ct in used)),
                   Filter("type", "type", tuple((t, t.replace("_", " ")) for t in sorted({r["attrs"]["type"] for r in rows.values() if r["attrs"]["type"]}))),
                   Filter("source", "bought", tuple((x, x) for x in sorted({r["attrs"]["source"] for r in rows.values() if r["attrs"]["source"]})))]
        vp = reads.version_periods(version)
        may, is_open = roles.may(who, VERB), v.get("status") == "open"
        g = figures.table("pur", list(rows.values()), MEASURES, "closing_quantity" if finance else "purchase_quantity",
                          figures.columns(vp, actuals=False, quarters=False), row_head="Key raw materials", filters=filters, total="Key raw materials",
                          editable=not finance and may and is_open, plan_periods=set(vp["plan"]),
                          year_says="plan periods", empty=f"No key raw material at {plants.get(loc, loc) if loc != 'ALL' else 'either plant'}.")
        others = sorted({names[i]["material_name"] for i in names if i not in {k[0] for k in keys}
                         and i in {r["component_material"] for r in q("select distinct component_material from dims.ref_bom")}
                         and names[i]["material_name"]})
        typed = q("select * from plan.purchase_act where version_id = ? order by input_code, plant_code, period", version)
        buy = sum(r["purchase_value"] or 0 for m in rows.values() for r in m["rows"])
        close = [m["rows"][-1]["closing_value"] or 0 for m in rows.values() if m["rows"]]
        cards = [{"label": "Purchases", "show": f"${buy / 1e6:,.2f}M", "says": f"{len(rows)} key materials over {version}'s plan periods"},
                 {"label": "Stock at the end", "show": f"${sum(close) / 1e6:,.2f}M", "says": "the key materials' closing value at the last plan period"},
                 {"label": "Typed", "show": str(len(typed)), "says": "quantities or prices typed over the calculated ones"}]
        return page(figures.MACROS + MACRO + PAGE, title="Material stock" if finance else "Material purchases", active="material_stock" if finance else "purchases", width="none",
                    finance=finance, version=version, where=plants.get(loc, "both plants") if loc != "ALL" else "both plants", g=g,
                    others=others, typed=typed, cards=cards, source_says=SOURCE_SAYS, may=may, holders=reads.holders(VERB),
                    is_open=is_open, last=session.last, receipt_acts=("purchase",))

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
        f = request.form
        if not f.get("key"):
            return typed_in_cells()
        who = who_fn(); c = ctx_fn()
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

    def typed_in_cells():
        """The table posted back: every quantity or price whose cell differs from the figure it was drawn with is placed —
        one act a material at a plant in a period, the quantity and the price together, all with the one reason, or none."""
        f = request.form; who = who_fn(); c = ctx_fn()
        version = f.get("version") or c.get("version") or reads.default_version()
        v = reads.version(version) or {}
        reason = (f.get("reason") or "").strip()
        plan_periods = set(reads.version_periods(version)["plan"])
        now = {(r["input_code"], r["plant_code"], r["period"]): r for r in q("select * from plan.material_stock where version_id = ?", version)}
        keys = {(k["input_code"], k["plant_code"]) for k in q("select input_code, plant_code from dims.ref_key_material")}
        by = {m.key: m for m in MEASURES}
        changed: dict = {}
        bad = []
        for k, code, period, raw in figures.posted(f, MEASURES):
            inp, _, plant = code.partition("~")
            r = now.get((inp, plant, period))
            if raw == "" or (r is not None and raw == figures.input_value(by[k], r[k])):
                continue                                   # left as drawn, or emptied: nothing typed
            x = _num(raw)
            field = "quantity" if k == "purchase_quantity" else "price"
            if x == "bad" or x is None or x < 0 or (field == "price" and x <= 0) or (inp, plant) not in keys or period not in plan_periods:
                bad.append(f"{field} {raw!r} for {inp} at {plant} in {period}")
                continue
            changed.setdefault((inp, plant, period), {"quantity": None, "price": None})[field] = x
        cells = "; ".join(f"{i} at {pl} in {per}: " + " · ".join(x for x in [f"quantity {d['quantity']:,.0f}" if d["quantity"] is not None else "",
                                                                             f"price {d['price']:,.4f}" if d["price"] is not None else ""] if x)
                          for (i, pl, per), d in sorted(changed.items()))
        checks = [
            {"check": "who may plan purchases", "ok": roles.may(who, VERB), "says": f"{who} holds {said(VERB)}" if roles.may(who, VERB) else f"{who} does not hold {said(VERB)} — purchases are planned by {', '.join(reads.holders(VERB))}"},
            {"check": "the plan is open", "ok": v.get("status") == "open", "says": f"{version} is {v.get('status', 'unknown')}"},
            {"check": "figures typed", "ok": bool(changed) and not bad, "says": ("refused: " + "; ".join(bad)) if bad else (cells or "no cell differs from the figure it was drawn with")},
            {"check": "a reason", "ok": bool(reason), "says": reason or "a purchase typed says why"},
        ]
        placed = receipts.judge(checks)
        if placed:
            now_ = dt.datetime.now()
            ACTS.place([{"act_id": f"PUR-{now_:%Y%m%d%H%M%S%f}-{i:03d}", "action": "set", "version_id": version, "input_code": inp, "plant_code": plant, "period": period,
                         "quantity": d["quantity"], "price": d["price"], "reason": reason, "entered_by": who, "entered_at": now_.isoformat(timespec="seconds")}
                        for i, ((inp, plant, period), d) in enumerate(sorted(changed.items()), start=1)], who)
        session.last = receipts.write("purchase.type", who, f"{len(changed)} cells", checks, placed)
        if overrides.released(who, "purchase", session, f"{len(changed)} purchase figure{'s' if len(changed) != 1 else ''} placed", placed):
            return redirect(url_for("plan.run"))
        if not placed:
            session.say("refused: " + "; ".join(x["says"] for x in checks if not x["ok"]), False)
        return redirect(url_for("plan.material_purchases", version=version, location=f.get("location") or None) + "#type")

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
