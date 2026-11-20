"""Material purchases (DEC-20261116-04, DEC-20261120-02 point 7, DEC-20261120-04): the key raw materials' balance —
opening, consumption, contracted and additional receipts, closing, in volume, value and cost basis — as one table, a
material at its plant a row and its movements beneath it.

Two sides of the same figures:
- **Material purchases**, under Supply, is the purchasing plan, worked apart from the Plan (face/purchasing_plan.py): it
  reads consumption from the revision it has taken, the buyer types additional receipts in the workspace, and publishes
  them; only what is published reaches the Plan, and the rest of its additional receipts the Plan proposes again.
- **Material stock**, under Financial planning → Cost of goods, is the Plan's balance (plan.material_stock), read only:
  what the costing takes as given.

Registered on the plan's blueprint by `register(...)`, called once from `face/__main__.py`."""
from __future__ import annotations

import datetime as dt

from chassis import receipts
from chassis.landing import LogLanding
from chassis.warehouse import Busy, q
from flask import redirect, request, url_for

from . import figures, overrides, purchasing_plan
from .figures import Filter, Measure
from .words import said

VERB = "register.supply_plan.maintain"
ACT_COLUMNS = ["act_id", "action", "withdraws", "version_id", "input_code", "plant_code", "period", "quantity", "price", "reason", "entered_by", "entered_at"]
ACTS = LogLanding("plan", "reg_purchase_act", ACT_COLUMNS)
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

PAGE = """<h1>{{ title }}<small>{{ version|plan }} · {{ where }} · {% if finance %}the Plan's balance, read only — additional receipts planned under Integrated business planning → Supply → <a href="{{ url_for('plan.material_purchases') }}">Material purchases</a> and published into it; the costing takes the consumption cost as given{% else %}the purchasing plan: the key raw materials' balance, worked apart from the Plan and published into it{% endif %}</small></h1>
<p class="hint">{% if finance %}Each key raw material's balance, period by period: consumption is valued at the period's opening cost basis, and the material cost of a case uses it. Every other input has no stock and is valued at its price in force.{% else %}Each row has one source. The opening is the stock on hand when the plan opens; after it, the period before's closing. Consumption is the cases the plant makes — the <a href="{{ url_for('plan.supply_plan') }}">supply plan</a>'s production requirement — × the bill × the plant's usage assumption, valued at the opening cost basis. Contracted receipts are what is already on order or under contract, at the contract's price. Additional receipts are proposed by how the material is bought — {% for k, v in source_says.items() %}<b>{{ v.split(' — ')[0] }}</b>: {{ v.split(' — ')[1] }}{{ '; ' if not loop.last else '.' }}{% endfor %} The closing is calculated, and is the next period's opening. {% if may %}You plan the additional receipts: type a quantity or a price in its cell over the proposal and keep it with a reason — it changes this balance at once and nothing in the Plan until you publish it. The Plan takes what you typed as typed and proposes the rest of its additional receipts again from its own consumption.{% else %}Additional receipts are planned by {{ holders|join(', ') or 'nobody yet' }}.{% endif %}{% endif %}</p>
{% if ws %}<div class="pin {{ 'behind' if ws.behind }}"><b>Consumption as of {{ ws.pinned.published_at.replace('T', ' ') if ws.pinned else ws.pin.consumption }}</b> — taken by {{ ws.pin.taken_by }}. {% if ws.behind %}The Plan has published a later consumption ({{ ws.latest.published_at.replace('T', ' ') }}): this balance does not read it until you take it.{% if may %} <form class="inline" method="post" action="{{ url_for('plan.purchase_take') }}"><input type="hidden" name="version" value="{{ version }}"><input type="hidden" name="revision" value="{{ ws.latest.revision }}"><button class="act">Take the latest</button></form>{% endif %}{% else %}It is the latest the Plan has published.{% endif %}</div>{% endif %}
<div class="cards">{% for c in cards %}<div class="card stat"><span>{{ c.label }}</span><b>{{ c.show }}</b><div class="small muted">{{ c.says }}</div></div>{% endfor %}</div>
{{ grid_choice(g) }}
{% if g.editable %}<form method="post" action="{{ url_for('plan.purchase_type') }}" id="type">{% for k in ('version', 'location') %}{% if request.args.get(k) %}<input type="hidden" name="{{ k }}" value="{{ request.args.get(k) }}">{% endif %}{% endfor %}{% endif %}
{{ grid_table(g) }}
{% if g.editable %}<div class="form-row"><label class="small grow">why <input name="reason" placeholder="the quote, the order, the change"></label><button class="primary">Place</button><span class="hint">kept in this purchasing plan by {{ who }}; publish to send it to the Plan</span></div></form>{% endif %}
<p class="hint">A row is a key raw material at the plant that holds it, its balance beneath it in volume (its own unit), value and cost basis. The volumes of different materials do not add, so the first row totals the value only. A name's line says its unit, how it is bought and its cover; choose a commodity above the table to read one alone. The year is its plan periods: movements summed, the opening its first period's, the closing its last's; a cost basis is not added. A typed additional receipt is boxed with the proposal beneath it; a closing below zero is marked short. The balance walks from the Plan's first plan period: an actual period holds no figure here.</p>
{% if others %}<p class="hint">Valued at the price in force, with no stock and no purchase line: {{ others|join(', ') }}.</p>{% endif %}
{% if ws %}<h2 id="publish">Typed here<span class="count">{{ drafts|length }} in this purchasing plan · {{ drafts|selectattr('published', 'equalto', '')|list|length }} not yet published</span></h2>
{% if drafts %}<table><thead><tr><th>Material</th><th>Plant</th><th>Period</th><th class="n">Quantity</th><th class="n">Price</th><th>Why</th><th>By</th><th>Published</th><th></th></tr></thead><tbody>
{% for t in drafts %}<tr><td>{{ t.input_code }}</td><td>{{ t.plant_code }}</td><td>{{ t.period }}</td><td class="n">{{ q0(t.quantity) }}</td><td class="n">{{ p(t.price) }}</td><td class="small">{{ t.reason }}</td><td class="small">{{ t.entered_by }}</td><td class="small">{{ t.published or 'not yet' }}</td>
<td>{% if may %}<form class="inline" method="post" action="{{ url_for('plan.purchase_drop') }}"><input type="hidden" name="version" value="{{ version }}"><input type="hidden" name="cell" value="{{ t.input_code }}|{{ t.plant_code }}|{{ t.period }}"><button class="act">Remove</button></form>{% endif %}</td></tr>{% endfor %}</tbody></table>{% else %}<p class="hint">Nothing typed in this purchasing plan.</p>{% endif %}
{% if may and is_open %}<form class="form-row" method="post" action="{{ url_for('plan.purchase_publish') }}"><input type="hidden" name="version" value="{{ version }}"><button class="primary" {{ 'disabled' if not drafts|selectattr('published', 'equalto', '')|list }}>Publish to the Plan</button><span class="hint">sends what is not yet published, with what this balance was made against; the Plan proposes the rest again on its next run</span></form>
<form class="form-row" method="post" enctype="multipart/form-data" action="{{ url_for('plan.purchase_sheet') }}"><input type="hidden" name="version" value="{{ version }}"><label class="small">or receipts from a spreadsheet, saved as CSV — {{ sheet_columns|join(', ') }} <input type="file" name="sheet" accept=".csv"></label><button class="act">Publish the spreadsheet</button></form>{% endif %}{% endif %}
{% if typed %}<h2>{{ 'In the Plan' if ws else 'Typed' }}<span class="count">{{ typed|length }} standing on {{ version|plan }}</span></h2><table><thead><tr><th>Material</th><th>Plant</th><th>Period</th><th class="n">Quantity</th><th class="n">Price</th><th>Why</th><th>By</th><th></th></tr></thead><tbody>
{% for t in typed %}<tr><td>{{ t.input_code }}</td><td>{{ t.plant_code }}</td><td>{{ t.period }}</td><td class="n">{{ q0(t.quantity) if t.quantity is not none else '' }}</td><td class="n">{{ p(t.price) if t.price is not none else '' }}</td><td class="small">{{ t.reason }}</td><td class="small">{{ t.entered_by }}</td>
<td>{% if not finance and may and is_open %}<form class="inline" method="post" action="{{ url_for('plan.purchase_withdraw') }}"><input type="hidden" name="act_id" value="{{ t.act_id }}"><input name="reason" required placeholder="why" size="10"> <button class="act">Withdraw</button></form>{% endif %}</td></tr>{% endfor %}</tbody></table>{% endif %}
{% if arrivals %}<h2>Published into the Plan<span class="count">the last {{ arrivals|length }}</span></h2><table><thead><tr><th>When</th><th>From</th><th>By</th><th class="n">Taken</th><th>Made against</th><th>Dropped · clashes</th></tr></thead><tbody>
{% for a in arrivals %}<tr><td class="small">{{ a.at.replace('T', ' ') }}</td><td>{{ a.source }}</td><td class="small">{{ a.by }}</td><td class="n">{{ a.taken|length if a.placed else 'refused' }}</td><td class="small">{{ 'consumption of ' ~ a.made_against[:15] if a.made_against else 'nothing stated' }} · actuals to {{ a.cutoff }}</td><td class="small">{{ (a.dropped + a.clashes)|join('; ') or (a.refused|join('; ')) }}</td></tr>{% endfor %}</tbody></table>{% endif %}
{% if last and not finance %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else ('!' if c.flag else '✕') }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}
{{ grid_style() }}<style>.pin{border:1px solid var(--rule);padding:.5rem .7rem;margin:.4rem 0}.pin.behind{border-color:var(--ink)}.pin form{display:inline}.form-row{display:flex;flex-wrap:wrap;gap:.8rem;align-items:end;margin:.6rem 0}.form-row .grow{flex:1;display:flex;flex-direction:column}</style>"""

MACRO = """{% macro q0(x) %}{{ '' if x is none else '{:,.0f}'.format(x) }}{% endmacro %}{% macro p(x) %}{{ '' if x is none else ('{:,.4f}'.format(x) if x < 1 else '{:,.2f}'.format(x)) }}{% endmacro %}"""


def register(bp, page, who_fn, ctx_fn, busy, session, roles) -> None:
    from . import reads

    def view(finance: bool):
        c = ctx_fn(); who = who_fn()
        version = c.get("version") or reads.default_version()
        loc = c.get("location") or "ALL"
        v = reads.version(version) or {}
        ws = None
        if finance:                                       # the Plan's balance
            stock = q("select * from plan.material_stock where version_id = ? order by input_code, plant_code, period", version)
        else:                                             # the purchasing plan's own, over the consumption it has taken
            stock, ws = purchasing_plan.balance(version, who)
            stock = sorted(stock, key=lambda r: (r["input_code"], r["plant_code"], r["period"]))
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
                "attrs": {"material": r["input_code"], "plant": r["plant_code"], "type": nm.get("material_type") or "", "source": k.get("source") or "", "category": ""},
                "cats": cats.get(r["input_code"], set()), "source": k.get("source"), "by": {}, "rows": []})
            row["by"][r["period"]] = {**r, "consumption_out": -(r["consumption_quantity"] or 0.0), "consumption_value_out": -(r["consumption_value"] or 0.0),
                                      "proposed_note": f"proposed {r['proposed_quantity']:,.0f}" if r["quantity_typed"] and r.get("proposed_quantity") is not None else None,
                                      "short_note": "short" if r["short"] else None, "typed_title": "typed over the proposal" + (" — published into the Plan" if finance else " — listed under Typed here")}
            row["rows"].append(r)
        # a category filter matches an input its materials' bill uses: the row carries the chosen category when it is one of its
        chosen_cat = request.args.get("f_category") or ""
        for row in rows.values():
            row["attrs"]["category"] = chosen_cat if chosen_cat in row["cats"] else ""
        used = sorted({ct for row in rows.values() for ct in row["cats"]}, key=lambda x: cat_names.get(x, x))
        filters = [Filter("material", "commodity", tuple(sorted({(r["attrs"]["material"], r["label"]) for r in rows.values()}, key=lambda x: x[1]))),
                   Filter("plant", "plant", tuple((p, plants.get(p, p)) for p in sorted({r["attrs"]["plant"] for r in rows.values()}))),
                   Filter("category", "used by", tuple((ct, cat_names.get(ct, ct)) for ct in used)),
                   Filter("type", "type", tuple((t, t.replace("_", " ")) for t in sorted({r["attrs"]["type"] for r in rows.values() if r["attrs"]["type"]}))),
                   Filter("source", "bought", tuple((x, x) for x in sorted({r["attrs"]["source"] for r in rows.values() if r["attrs"]["source"]})))]
        vp = reads.version_periods(version)
        may, is_open = roles.may(who, VERB), v.get("status") == "open"
        g = figures.table("pur", list(rows.values()), MEASURES, "closing_quantity",
                          figures.columns(vp, actuals=False, quarters=False), row_head="Key raw materials", filters=filters, total="Key raw materials",
                          editable=not finance and may, plan_periods=set(vp["plan"]),
                          year_says="plan periods", empty=f"No key raw material at {plants.get(loc, loc) if loc != 'ALL' else 'either plant'}.", movement=True)
        others = sorted({names[i]["material_name"] for i in names if i not in {k[0] for k in keys}
                         and i in {r["component_material"] for r in q("select distinct component_material from dims.ref_bom")}
                         and names[i]["material_name"]})
        typed = q("select * from plan.purchase_act where version_id = ? order by input_code, plant_code, period", version)
        drafts = purchasing_plan.typed(version) if not finance else []
        buy = sum(r["purchase_value"] or 0 for m in rows.values() for r in m["rows"])        # contracted and additional receipts
        close = [m["rows"][-1]["closing_value"] or 0 for m in rows.values() if m["rows"]]
        cards = [{"label": "Receipts", "show": f"${buy / 1e6:,.2f}M", "says": f"contracted and additional, {len(rows)} key materials over {version}'s plan periods"},
                 {"label": "Stock at the end", "show": f"${sum(close) / 1e6:,.2f}M", "says": "the key materials' closing value at the last plan period"},
                 {"label": "Typed", "show": str(len(drafts) if not finance else len(typed)), "says": "additional receipts typed over the proposals" + (" in this purchasing plan" if not finance else ", published into the Plan")}]
        return page(figures.MACROS + MACRO + PAGE, title="Material stock" if finance else "Material purchases", active="material_stock" if finance else "purchases", width="none",
                    finance=finance, version=version, where=plants.get(loc, "both plants") if loc != "ALL" else "both plants", g=g,
                    others=others, typed=typed, cards=cards, source_says=SOURCE_SAYS, may=may, holders=reads.holders(VERB),
                    is_open=is_open, last=session.last, receipt_acts=("purchase",), ws=ws, drafts=drafts, arrivals=purchasing_plan.arrivals(version),
                    sheet_columns=purchasing_plan.SHEET_COLUMNS)

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

    def keep(version: str, changed: dict, bad: list, reason: str, who: str):
        """Typed cells kept in the purchasing plan's workspace — never the Plan's register; publishing sends them."""
        cells = "; ".join(f"{i} at {pl} in {per}: " + " · ".join(x for x in [f"quantity {d['quantity']:,.0f}" if d.get("quantity") is not None else "",
                                                                             f"price {d['price']:,.4f}" if d.get("price") is not None else ""] if x)
                          for (i, pl, per), d in sorted(changed.items()))
        checks = [
            {"check": "who may plan purchases", "ok": roles.may(who, VERB), "says": f"{who} holds {said(VERB)}" if roles.may(who, VERB) else f"{who} does not hold {said(VERB)} — purchases are planned by {', '.join(reads.holders(VERB))}"},
            {"check": "figures typed", "ok": bool(changed) and not bad, "says": ("refused: " + "; ".join(bad)) if bad else (cells or "no cell differs from the figure it was drawn with")},
            {"check": "a reason", "ok": bool(reason), "says": reason or "a purchase typed says why"},
        ]
        kept = receipts.judge(checks)
        if kept:
            purchasing_plan.type_cells(version, changed, reason, who)
        session.last = receipts.write("purchase.type", who, f"{len(changed)} cells", checks, kept)
        session.say(f"{len(changed)} figure{'s' if len(changed) != 1 else ''} kept in the purchasing plan — publish to send {'them' if len(changed) != 1 else 'it'} to the Plan" if kept
                    else "refused: " + "; ".join(x["says"] for x in checks if not x["ok"]), kept)
        return redirect(url_for("plan.material_purchases", version=version, location=request.form.get("location") or None) + "#publish")

    @bp.post("/supply/purchases/type")
    def purchase_type():
        f = request.form
        if not f.get("key"):
            return typed_in_cells()
        who = who_fn(); c = ctx_fn()
        version = f.get("version") or c.get("version") or reads.default_version()
        inp, _, plant = (f.get("key") or "").partition("|")
        period = f.get("period") or ""
        qty, price = _num(f.get("quantity")), _num(f.get("price"))
        ok = q("select 1 ok from dims.ref_key_material where input_code = ? and plant_code = ?", inp, plant) and period in reads.version_periods(version)["plan"] \
            and qty != "bad" and price != "bad" and (qty is not None or price is not None) and (qty or 0) >= 0 and (price is None or price > 0)
        return keep(version, {(inp, plant, period): {"quantity": qty, "price": price}} if ok else {}, [] if ok else [f"{inp or 'nothing'} at {plant or '—'} in {period or 'no period'}: a key material, a plan period and a quantity or a price"],
                    (f.get("reason") or "").strip(), who)

    def typed_in_cells():
        """The table posted back: every quantity or price whose cell differs from the figure it was drawn with is kept in
        the workspace — the quantity and the price of a cell together, all with the one reason, or none."""
        f = request.form; who = who_fn(); c = ctx_fn()
        version = f.get("version") or c.get("version") or reads.default_version()
        plan_periods = set(reads.version_periods(version)["plan"])
        now = {(r["input_code"], r["plant_code"], r["period"]): r for r in purchasing_plan.balance(version, who)[0]}
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
        return keep(version, changed, bad, (f.get("reason") or "").strip(), who)

    def _version_posted() -> str:
        return request.form.get("version") or ctx_fn().get("version") or reads.default_version()

    def _publish(version: str, who: str, checks: list, placed: bool, what: str):
        checks = [{"check": "who may plan purchases", "ok": roles.may(who, VERB), "says": f"{who} holds {said(VERB)}" if roles.may(who, VERB) else f"{who} does not hold {said(VERB)}"}] + checks
        session.last = receipts.write("purchase.publish", who, what, checks, placed)
        if overrides.released(who, "purchase", session, f"{what} published into the Plan", placed):
            return redirect(url_for("plan.run"))
        if not placed:
            session.say("refused: " + "; ".join(x["says"] for x in checks if not x["ok"]), False)
        return redirect(url_for("plan.material_purchases", version=version) + "#publish")

    @bp.post("/supply/purchases/publish")
    def purchase_publish():
        """The workspace's unpublished receipts sent to the Plan through the contract (DEC-20261120-04)."""
        who = who_fn(); version = _version_posted()
        if not roles.may(who, VERB):
            return _publish(version, who, [], False, "nothing")
        checks, placed, arrival = purchasing_plan.publish_workspace(version, who)
        return _publish(version, who, checks, placed, f"{len(arrival['taken'])} receipt{'s' if len(arrival['taken']) != 1 else ''} from the purchasing plan")

    @bp.post("/supply/purchases/sheet")
    def purchase_sheet():
        """Receipts from a spreadsheet: the same contract, the same checks — only where they came from differs."""
        who = who_fn(); version = _version_posted()
        fs = request.files.get("sheet")
        rows = purchasing_plan.read_sheet(fs.read().decode("utf-8-sig")) if fs else []
        if not roles.may(who, VERB):
            return _publish(version, who, [], False, "nothing")
        checks, placed, arrival = purchasing_plan.arrive(version, rows, "a spreadsheet", who)
        return _publish(version, who, checks, placed, f"{len(arrival['taken'])} receipt{'s' if len(arrival['taken']) != 1 else ''} from a spreadsheet")

    @bp.post("/supply/purchases/take")
    def purchase_take():
        """The purchasing plan takes the Plan's latest consumption: its pin moves, and its balance reads it."""
        who = who_fn(); version = _version_posted()
        if roles.may(who, VERB):
            try:
                purchasing_plan.take(version, request.form.get("revision") or "", who)
                session.say("the purchasing plan reads the Plan's latest consumption now", True)
            except ValueError as e:
                session.say(str(e), False)
        else:
            session.say(f"{who} does not hold {said(VERB)}", False)
        return redirect(url_for("plan.material_purchases", version=version))

    @bp.post("/supply/purchases/drop")
    def purchase_drop():
        who = who_fn(); version = _version_posted()
        cell = tuple((request.form.get("cell") or "").split("|"))
        if roles.may(who, VERB) and len(cell) == 3:
            purchasing_plan.drop(version, cell)
            session.say("removed from the purchasing plan; the proposal stands again here — a figure already published stays in the Plan until withdrawn", True)
        return redirect(url_for("plan.material_purchases", version=version) + "#publish")

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
