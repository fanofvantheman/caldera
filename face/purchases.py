"""The key raw materials' balance (DEC-20261116-04, DEC-20261120-02 point 7) — opening, consumption, contracted and
additional receipts, closing, in volume, value and cost basis — as one table, a material at its plant a row and its
movements beneath it. Two pages over the same function:

- **Material balance**, under Purchasing, is one of the planner's own purchasing plans (DEC-20261121-01,
  face/purchasing_plan.py): its balance over the copies it holds and the receipts typed in it — a quantity and a price
  together. Nothing typed here reaches an IBP plan until a snapshot is sent from My plans.
- **Material stock**, under Financial planning → Cost of goods, is the IBP plan's balance (plan.material_stock), read
  only: the receipts standing there taken as fixed, the rest proposed again; what the costing takes as given.

Registered on the plan's blueprint by `register(...)`, called once from `face/__main__.py`."""
from __future__ import annotations

from chassis import receipts
from chassis.warehouse import Busy, q
from flask import redirect, request, url_for

from . import figures, purchasing_plan
from .figures import Filter, Measure
from .words import said

VERB = "register.supply_plan.maintain"
# one table, a key raw material at its plant a row (DEC-20261119-05), each a movement table — each element a row, in volume,
# value and cost basis (DEC-20261120-02 point 7, CH's mock); consumption shown as it leaves the stock, below zero
MEASURES = [Measure("opening_quantity", "opening", year="first", total=False, group="volume"),
            Measure("consumption_out", "consumption", total=False, group="volume"),
            Measure("contracted_quantity", "contracted receipts", total=False, group="volume"),
            Measure("additional_quantity", "additional receipts", typed="quantity_typed", note="proposed_note", input=True, total=False, group="volume"),
            Measure("closing_quantity", "projected closing", year="last", note="short_note", total=False, group="volume"),
            Measure("opening_value", "opening", shown="money", year="first", group="value"),
            Measure("consumption_value_out", "consumption", shown="money", group="value"),
            Measure("contracted_value", "contracted receipts", shown="money", group="value"),
            Measure("additional_value", "additional receipts", shown="money", group="value"),
            Measure("closing_value", "projected closing", shown="money", year="last", group="value"),
            Measure("opening_cost", "opening", shown="price", year=None, total=False, group="cost basis"),
            Measure("average_cost", "consumption", shown="price", year=None, total=False, group="cost basis"),
            Measure("contracted_price", "contracted receipts", shown="price", year=None, total=False, group="cost basis"),
            Measure("additional_price", "additional receipts", shown="price", year=None, typed="price_typed", input=True, total=False, group="cost basis"),
            Measure("closing_cost", "projected closing", shown="price", year=None, total=False, group="cost basis")]
SOURCE_SAYS = {"contract": "contract — what keeps the cover beyond the contracted receipts, at the price in force; the contract's price fixed, or tied to an index, for its term",
               "spot": "spot — what keeps the cover, at the price in force with its index",
               "campaign": "campaign intake — bought in the input's window for what is needed until the next, beyond what is contracted"}

PAGE = """{% if finance %}<h1>{{ title }}<small>{{ version|plan }} · {{ where }} · the Plan's balance, read only — its additional receipts are the ones purchasing has sent into it, taken as typed, and the rest proposed again; the costing takes the consumption cost as given</small></h1>
<p class="hint">Each key raw material's balance, period by period: consumption is valued at the period's opening cost basis, and the material cost of a case uses it. Every other input has no stock and is valued at its price in force.</p>
{% else %}<h1>{{ p.name }}<small>the material balance · actuals to {{ per(p.actuals_to) }} · through {{ per(p.through) }} · {{ where }} · <a href="{{ url_for('plan.purchasing_plans', purchasing=p.id) }}">My plans</a></small></h1>
<p class="hint">Each row has one source. The opening is the stock on hand at the close of {{ per(p.actuals_to) }}; after it, the period before's closing. Consumption is copied from the IBP plan each plant reads — the cases it makes × the bill × the plant's usage — and valued at the opening cost basis. Contracted receipts are what is already on order or under contract, at the contract's price. Additional receipts are proposed by how the material is bought — {% for k, v in source_says.items() %}<b>{{ v.split(' — ')[0] }}</b>: {{ v.split(' — ')[1] }}{{ '; ' if not loop.last else '.' }}{% endfor %} The closing is calculated, and is the next period's opening. {% if may %}You plan the additional receipts: type a quantity and a price in a cell over the proposal and keep it with a reason — a receipt is a quantity and a price together; one without the other is not taken. It changes this balance at once and nothing in any IBP plan until you send a snapshot from <a href="{{ url_for('plan.purchasing_plans', purchasing=p.id) }}">My plans</a>.{% endif %}</p>
<div class="card reads"><b>Reads copies, not connections</b> — {% for pl, c in reads.consumption.items() %}consumption at {{ plants.get(pl, pl) }}: {% if c %}{{ c.source|planfull }}, copy of {{ when(c.taken_at) }}{% else %}<b>not received</b>{% endif %}{{ '; ' if not loop.last else '.' }}{% endfor %} A source changing changes nothing here until you refresh.</div>{% endif %}
<div class="cards">{% for c in cards %}<div class="card stat"><span>{{ c.label }}</span><b>{{ c.show }}</b><div class="small muted">{{ c.says }}</div></div>{% endfor %}</div>
{{ grid_choice(g) }}
{% if g.editable %}<form method="post" action="{{ url_for('plan.purchase_type') }}" id="type">{% if request.args.get('location') %}<input type="hidden" name="location" value="{{ request.args.get('location') }}">{% endif %}{% endif %}
{{ grid_table(g) }}
{% if g.editable %}<div class="form-row"><label class="small grow">why <input name="reason" placeholder="the quote, the order, the change"></label><button class="primary">Keep</button><span class="hint">kept in this plan by {{ who }}; a quantity and a price together</span></div></form>{% endif %}
<p class="hint">A row is a key raw material at the plant that holds it, its balance beneath it in volume (its own unit), value and cost basis. The volumes of different materials do not add, so the first row totals the value only. A name's line says its unit, how it is bought and its cover; choose a commodity above the table to read one alone. The year is its plan periods: movements summed, the opening its first period's, the closing its last's; a cost basis is not added. A typed additional receipt is boxed with the proposal beneath it; a closing below zero is marked short.</p>
{% if others %}<p class="hint">Valued at the price in force, with no stock and no purchase line: {{ others|join(', ') }}.</p>{% endif %}
{% if not finance %}<h2 id="typed">Typed here<span class="count">{{ drafts|length }} receipt{{ '' if drafts|length == 1 else 's' }} in this plan · {{ n_changed }} new or changed since its last snapshot</span></h2>
{% if drafts %}<table><thead><tr><th>Material</th><th>Plant</th><th>Period</th><th class="n">Quantity</th><th class="n">Price</th><th>Why</th><th>By</th><th>Since sent</th><th></th></tr></thead><tbody>
{% for t in drafts %}<tr><td>{{ names.get(t.input_code, {}).get('material_name') or t.input_code }}</td><td>{{ plants.get(t.plant_code, t.plant_code) }}</td><td>{{ per(t.period) }}</td><td class="n">{{ q0(t.quantity) }}</td><td class="n">{{ pr(t.price) }}</td><td class="small">{{ t.reason }}</td><td class="small">{{ t.entered_by }}</td><td class="small">{{ t.since }}</td>
<td class="acts">{% if may %}<form class="inline" method="post" action="{{ url_for('plan.purchase_drop') }}"><input type="hidden" name="cell" value="{{ t.input_code }}|{{ t.plant_code }}|{{ t.period }}"><button class="act">Remove</button></form>{% endif %}</td></tr>{% endfor %}</tbody></table>{% else %}<p class="hint">Nothing typed in this plan.</p>{% endif %}
{% if last %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else ('!' if c.flag else '✕') }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}
{% elif typed %}<h2>Standing in the Plan<span class="count">{{ typed|length }} receipt{{ '' if typed|length == 1 else 's' }} on {{ version|plan }}</span></h2><table><thead><tr><th>Material</th><th>Plant</th><th>Period</th><th class="n">Quantity</th><th class="n">Price</th><th>Why</th><th>By</th></tr></thead><tbody>
{% for t in typed %}<tr><td>{{ t.input_code }}</td><td>{{ t.plant_code }}</td><td>{{ t.period }}</td><td class="n">{{ q0(t.quantity) if t.quantity is not none else '' }}</td><td class="n">{{ pr(t.price) if t.price is not none else '' }}</td><td class="small">{{ t.reason }}</td><td class="small">{{ t.entered_by }}</td></tr>{% endfor %}</tbody></table>{% endif %}
{{ grid_style() }}<style>.card.reads{padding:.6rem .9rem;margin:.4rem 0 1rem}.form-row{display:flex;flex-wrap:wrap;gap:.8rem;align-items:end;margin:.6rem 0}.form-row .grow{flex:1;display:flex;flex-direction:column}</style>"""

NONE = """<h1>Material balance<small>a purchasing plan's balance</small></h1>
<p class="lede">You have no purchasing plan yet. Make one on <a href="{{ url_for('plan.purchasing_plans') }}">My plans</a>; it opens here.</p>"""

MACRO = """{% macro q0(x) %}{{ '' if x is none else '{:,.0f}'.format(x) }}{% endmacro %}{% macro pr(x) %}{{ '' if x is none else ('{:,.4f}'.format(x) if x < 1 else '{:,.2f}'.format(x)) }}{% endmacro %}"""


def per(x: str | None) -> str:
    """A period as a planner reads it: 2027P04 → 2027 P04."""
    return (x or "").replace("P", " P", 1)


def when(x: str | None) -> str:
    """A moment as a planner reads it: 2026-11-21T10:31:07 → 21 Nov 10:31."""
    import datetime as dt
    try:
        t = dt.datetime.fromisoformat(x or "")
    except ValueError:
        return x or ""
    return f"{t.day} {t:%b %H:%M}"


def register(bp, page, who_fn, ctx_fn, busy, session, roles) -> None:
    from . import reads

    def view(finance: bool):
        c = ctx_fn(); who = who_fn()
        loc = request.args.get("location") or "ALL"
        p = None
        if finance:                                       # the Plan's balance
            version = c.get("version") or reads.default_version()
            stock = q("select * from plan.material_stock where version_id = ? order by input_code, plant_code, period", version)
            keys = {(k["input_code"], k["plant_code"]): k for k in q("select * from dims.ref_key_material")}
            names = {r["material_code"]: r for r in q("select material_code, material_name, material_type, base_uom from dims.dim_input_material")}
            vp = reads.version_periods(version)
        else:                                             # the purchasing plan's own, over the copies it holds
            p = purchasing_plan.plan(c.get("purchasing"))
            if not p or p["owner"] != who:
                return page(NONE, title="Material balance", active="purchases")
            version = None
            stock = sorted(purchasing_plan.balance(p), key=lambda r: (r["input_code"], r["plant_code"], r["period"]))
            keys = {(k["input_code"], k["plant_code"]): {**k, "cover_periods": purchasing_plan._num(k.get("cover_periods"))} for k in purchasing_plan.structures(p, "dims.ref_key_material")}
            names = {r["material_code"]: r for r in purchasing_plan.structures(p, "dims.dim_input_material")}
            vp = purchasing_plan.periods(p)
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
                "attrs": {"material": r["input_code"], "plant": r["plant_code"], "type": nm.get("material_type") or "", "source": k.get("source") or "", "category": ""},
                "cats": cats.get(r["input_code"], set()), "source": k.get("source"), "by": {}, "rows": []})
            row["by"][r["period"]] = {**r, "consumption_out": -(r["consumption_quantity"] or 0.0), "consumption_value_out": -(r["consumption_value"] or 0.0),
                                      "proposed_note": f"proposed {r['proposed_quantity']:,.0f}" if r["quantity_typed"] and r.get("proposed_quantity") is not None else None,
                                      "short_note": "short" if r["short"] else None, "typed_title": "sent by purchasing, taken as typed" if finance else "typed in this plan — listed under Typed here"}
            row["rows"].append(r)
        # a category filter matches an input its materials' bill uses: the row carries the chosen category when it is one of its
        chosen_cat = request.args.get("f_category") or ""
        for row in rows.values():
            row["attrs"]["category"] = chosen_cat if chosen_cat in row["cats"] else ""
        used = sorted({ct for row in rows.values() for ct in row["cats"]}, key=lambda x: cat_names.get(x, x))
        filters = [Filter("material", "commodity", tuple(sorted({(r["attrs"]["material"], r["label"]) for r in rows.values()}, key=lambda x: x[1]))),
                   Filter("plant", "plant", tuple((pl, plants.get(pl, pl)) for pl in sorted({r["attrs"]["plant"] for r in rows.values()}))),
                   Filter("category", "used by", tuple((ct, cat_names.get(ct, ct)) for ct in used)),
                   Filter("type", "type", tuple((t, t.replace("_", " ")) for t in sorted({r["attrs"]["type"] for r in rows.values() if r["attrs"]["type"]}))),
                   Filter("source", "bought", tuple((x, x) for x in sorted({r["attrs"]["source"] for r in rows.values() if r["attrs"]["source"]})))]
        may = roles.may(who, VERB)
        g = figures.table("pur", list(rows.values()), MEASURES, "closing_quantity",
                          figures.columns(vp, actuals=False, quarters=False), row_head="Key raw materials", filters=filters, total="Key raw materials",
                          editable=not finance and may, plan_periods=set(vp["plan"]),
                          year_says="plan periods", empty=f"No key raw material at {plants.get(loc, loc) if loc != 'ALL' else 'the plants this plan buys for'}.", movement=True)
        bom = {r["component_material"] for r in q("select distinct component_material from dims.ref_bom")}
        others = sorted({names[i]["material_name"] for i in names if i not in {k[0] for k in keys} and i in bom and names[i].get("material_name")})
        typed = q("select * from plan.purchase_act where version_id = ? order by input_code, plant_code, period", version) if finance else []
        drafts, n_changed = [], 0
        if p:
            ch = {purchasing_plan._cell(r) for r in purchasing_plan.changed(p["id"])}
            before = {purchasing_plan._cell(r) for r in (purchasing_plan.sent(p["id"]) or {}).get("receipts", [])}
            drafts = [{**t, "since": ("changed" if purchasing_plan._cell(t) in before else "new") if purchasing_plan._cell(t) in ch else "as last sent"}
                      for t in purchasing_plan.typed(p["id"])]
            n_changed = len(ch)
        buy = sum(r["purchase_value"] or 0 for m in rows.values() for r in m["rows"])        # contracted and additional receipts
        close = [m["rows"][-1]["closing_value"] or 0 for m in rows.values() if m["rows"]]
        cards = [{"label": "Receipts", "show": f"${buy / 1e6:,.2f}M", "says": f"contracted and additional, {len(rows)} key materials over the plan periods"},
                 {"label": "Stock at the end", "show": f"${sum(close) / 1e6:,.2f}M", "says": "the key materials' closing value at the last plan period"},
                 {"label": "Typed", "show": str(len(typed) if finance else len(drafts)),
                  "says": "additional receipts standing in the Plan, sent by purchasing" if finance else "additional receipts typed in this plan"}]
        where = plants.get(loc, loc) if loc != "ALL" else ("both plants" if finance else ", ".join(plants.get(x, x) for x in p["plants"]))
        return page(figures.MACROS + MACRO + PAGE, title="Material stock" if finance else "Material balance", active="material_stock" if finance else "purchases", width="none",
                    finance=finance, version=version, p=p, where=where, g=g, others=others, typed=typed, cards=cards, source_says=SOURCE_SAYS, may=may,
                    last=session.last, receipt_acts=("purchase.type",), drafts=drafts, n_changed=n_changed, names=names, plants=plants,
                    reads=purchasing_plan.reads_of(p) if p else None, per=per, when=when)

    @bp.get("/purchasing/balance")
    def material_purchases():
        try:
            return view(False)
        except Busy as e:
            return busy("Material balance", e)

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

    def _plan_posted(who: str) -> dict | None:
        p = purchasing_plan.plan(ctx_fn().get("purchasing"))
        return p if p and p["owner"] == who else None

    def keep(p: dict | None, changed: dict, bad: list, reason: str, who: str):
        """Typed cells kept in the plan — never an IBP plan's register; a snapshot sends them. A cell kept must come out
        with a quantity and a price (DEC-20261121-01 point 10)."""
        if p:
            for (i, pl, per_), d in purchasing_plan.merged(p["id"], changed).items():
                if d["quantity"] is None or d["price"] is None:
                    bad.append(f"{i} at {pl} in {per(per_)}: {'a price' if d['price'] is None else 'a quantity'} as well — a receipt is a quantity and a price together")
        cells = "; ".join(f"{i} at {pl} in {per_}: " + " · ".join(x for x in [f"quantity {d['quantity']:,.0f}" if d.get("quantity") is not None else "",
                                                                              f"price {d['price']:,.4f}" if d.get("price") is not None else ""] if x)
                          for (i, pl, per_), d in sorted(changed.items()))
        checks = [
            {"check": "who may plan purchases", "ok": roles.may(who, VERB), "says": f"{who} holds {said(VERB)}" if roles.may(who, VERB) else f"{who} does not hold {said(VERB)} — purchases are planned by {', '.join(reads.holders(VERB))}"},
            {"check": "a plan of yours", "ok": bool(p), "says": p["name"] if p else "no plan of yours is chosen"},
            {"check": "a quantity and a price together", "ok": bool(changed) and not bad, "says": "; ".join(bad) if bad else (cells or "no cell differs from the figure it was drawn with")},
            {"check": "a reason", "ok": bool(reason), "says": reason or "a receipt typed says why"},
        ]
        kept = receipts.judge(checks)
        if kept:
            purchasing_plan.type_cells(p["id"], changed, reason, who)
        session.last = receipts.write("purchase.type", who, f"{len(changed)} cells", checks, kept)
        session.say(f"{len(changed)} receipt{'s' if len(changed) != 1 else ''} kept in {p['name']} — send a snapshot from My plans to put {'them' if len(changed) != 1 else 'it'} into an IBP plan" if kept
                    else "refused: " + "; ".join(x["says"] for x in checks if not x["ok"]), kept)
        return redirect(url_for("plan.material_purchases", location=request.form.get("location") or None) + "#typed")

    @bp.post("/purchasing/balance/type")
    def purchase_type():
        f = request.form
        who = who_fn()
        p = _plan_posted(who)
        if f.get("key"):                                  # one cell, posted on its own
            inp, _, plant = (f.get("key") or "").partition("|")
            period = f.get("period") or ""
            qty, price = _num(f.get("quantity")), _num(f.get("price"))
            ok = p and plant in p["plants"] and period in purchasing_plan.periods(p)["plan"] and qty != "bad" and price != "bad" \
                and (qty is not None or price is not None) and (qty or 0) >= 0 and (price is None or price > 0)
            return keep(p, {(inp, plant, period): {"quantity": qty, "price": price}} if ok else {},
                        [] if ok else [f"{inp or 'nothing'} at {plant or '—'} in {period or 'no period'}: a key material of this plan, a plan period and a figure"],
                        (f.get("reason") or "").strip(), who)
        return typed_in_cells(p, who)

    def typed_in_cells(p: dict | None, who: str):
        """The table posted back: every quantity or price whose cell differs from the figure it was drawn with — the
        quantity and the price of a cell together, all with the one reason, or none."""
        f = request.form
        if not p:
            return keep(None, {}, [], (f.get("reason") or "").strip(), who)
        plan_periods = set(purchasing_plan.periods(p)["plan"])
        now = {(r["input_code"], r["plant_code"], r["period"]): r for r in purchasing_plan.balance(p)}
        by = {m.key: m for m in MEASURES}
        changed: dict = {}
        bad = []
        for k, code, period, raw in figures.posted(f, MEASURES):
            inp, _, plant = code.partition("~")
            r = now.get((inp, plant, period))
            if raw == "" or (r is not None and raw == figures.input_value(by[k], r[k])):
                continue                                   # left as drawn, or emptied: nothing typed
            x = _num(raw)
            field = "quantity" if k == "additional_quantity" else "price"
            if x == "bad" or x is None or x < 0 or (field == "price" and x <= 0) or r is None or period not in plan_periods:
                bad.append(f"{field} {raw!r} for {inp} at {plant} in {period}")
                continue
            changed.setdefault((inp, plant, period), {"quantity": None, "price": None})[field] = x
        return keep(p, changed, bad, (f.get("reason") or "").strip(), who)

    @bp.post("/purchasing/balance/drop")
    def purchase_drop():
        who = who_fn()
        p = _plan_posted(who)
        cell = tuple((request.form.get("cell") or "").split("|"))
        if p and roles.may(who, VERB) and len(cell) == 3:
            purchasing_plan.drop(p["id"], cell)
            session.say(f"removed from {p['name']}; the proposal stands again here — what stands in an IBP plan changes only when a snapshot is sent", True)
        return redirect(url_for("plan.material_purchases") + "#typed")
