"""The key raw materials' balance (DEC-20261116-04, DEC-20261120-02 point 7) — opening, consumption, contracted and
additional receipts, closing, in volume, value and cost basis — as one table, a material at its plant a row and its
movements beneath it. Two pages over the same function:

- **Material balance**, under Purchasing, is one of the planner's own purchasing plans (DEC-20261121-01,
  face/purchasing_plan.py): its balance over the copies it holds and the receipts typed in it — a quantity and a price
  together. Nothing typed here reaches an IBP plan until a snapshot is sent from My plans.
- **Material stock**, under Financial planning → Cost of goods, is the IBP plan's balance (plan.material_stock), read
  only: the receipts standing there and nothing else; what the costing takes as given.

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
            Measure("additional_quantity", "additional receipts", typed="quantity_typed", input=True, total=False, group="volume"),
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
SOURCE_SAYS = {"contract": "contract — the contract's price fixed, or tied to an index, for its term",
               "spot": "spot — bought at the price in force with its index",
               "campaign": "campaign intake — bought in the input's window for what is needed until the next"}

PAGE = """{% if finance %}<h1>{{ title }}<small>{{ version|plan }} · {{ where }} · the Plan's balance, read only — its additional receipts are the ones purchasing has sent into it and nothing else; the costing takes the consumption cost as given</small></h1>
<p class="hint">Each key raw material's balance, period by period: consumption is valued at the period's opening cost basis, and the material cost of a case uses it. Every other input has no stock and is valued at its price in force.</p>
{% else %}<h1>{{ p.name }}<small>the material balance · actuals to {{ per(p.actuals_to) }} · through {{ per(p.through) }} · {{ where }} · <a href="{{ url_for('plan.purchasing_plans', purchasing=p.id) }}">My plans</a></small></h1>
<p class="hint">Each row has one source. The opening is the stock on hand at the close of {{ per(p.actuals_to) }}; after it, the period before's closing. Consumption is copied from the IBP plan each plant reads — the cases it makes × the bill × the plant's usage — and valued at the opening cost basis. Contracted receipts are what is already on order or under contract, at the contract's price. Additional receipts are the ones you plan and nothing else: the balance buys nothing of its own. The closing is calculated, and is the next period's opening; it is marked <b>short</b> below zero and <b>below cover</b> under the cover the material is meant to hold — its cover periods × the average consumption of the next three periods. {% if may %}Type a quantity in an additional-receipts cell — its price is the price in force unless you type one — and save it with the bar at the foot of the window; a note may be written in a cell, as a comment is in a spreadsheet —  It changes this balance at once and nothing in any IBP plan until you send a snapshot from <a href="{{ url_for('plan.purchasing_plans', purchasing=p.id) }}">My plans</a>.{% endif %}</p>
<div class="card reads"><b>Reads copies, not connections</b> — {% for pl, c in reads.consumption.items() %}consumption at {{ plants.get(pl, pl) }}: {% if c %}{{ c.source|planfull }}, copy of {{ when(c.taken_at) }}{% else %}<b>not received</b>{% endif %}{{ '; ' if not loop.last else '.' }}{% endfor %} A source changing changes nothing here until you refresh.</div>{% endif %}
<div class="cards">{% for c in cards %}{% if c.href %}<a class="card stat link{{ ' on' if c.on }}" href="{{ c.href }}">{% else %}<div class="card stat">{% endif %}<span>{{ c.label }}</span><b>{{ c.show }}</b>{% if c.vs %}<div class="small vs">{{ c.vs }}</div>{% endif %}<div class="small muted">{{ c.says }}</div>{{ '</a>'|safe if c.href else '</div>'|safe }}{% endfor %}</div>
{{ grid_choice(g) }}
{% if g.editable %}<form method="post" action="{{ url_for('plan.purchase_type') }}" id="type">{% if request.args.get('location') %}<input type="hidden" name="location" value="{{ request.args.get('location') }}">{% endif %}{% endif %}
{{ grid_table(g) }}
{% if g.editable %}{{ save_bar(discard='reset', note='saved in this plan by ' ~ who ~ ' · a quantity typed takes the price in force unless you type one · right-click a cell (or Shift+F2) to write a note in it') }}</form>{% endif %}
<p class="hint">A row is a key raw material at the plant that holds it, its balance beneath it in volume (its own unit), value and cost basis. The volumes of different materials do not add, so the first row totals the value only. A name's line says its unit, how it is bought and its cover; choose a commodity above the table to read one alone. The year is its plan periods: movements summed, the opening its first period's, the closing its last's; a cost basis is not added. A typed additional receipt is boxed, and one with a note has its corner marked; a closing below zero is marked short, one under its cover below cover.</p>
{% if others %}<p class="hint">Valued at the price in force, with no stock and no purchase line: {{ others|join(', ') }}.</p>{% endif %}
{% if not finance %}<h2 id="typed">Typed here<span class="count">{{ drafts|length }} receipt{{ '' if drafts|length == 1 else 's' }} in this plan · {{ n_changed }} new or changed since its last snapshot</span></h2>
{% if may and clearable %}<form class="form-row" method="post" action="{{ url_for('plan.purchase_clear') }}"><input type="hidden" name="rows" value="{{ clear_rows|join(',') }}"><button class="act" onclick="this.textContent='Clearing…'">Clear the {{ clearable|length }} receipt{{ '' if clearable|length == 1 else 's' }} typed in the rows shown</button><span class="hint">each cell is emptied{% if clearable|length != drafts|length %}; {{ drafts|length - clearable|length }} typed in rows not shown stay{% endif %} · nothing in an IBP plan changes until you send a snapshot</span></form>{% endif %}
{% if drafts %}<table><thead><tr><th>Material</th><th>Plant</th><th>Period</th><th class="n">Quantity</th><th class="n">Price</th><th>Note</th><th>By</th><th>Since sent</th><th></th></tr></thead><tbody>
{% for t in drafts %}<tr><td>{{ names.get(t.input_code, {}).get('material_name') or t.input_code }}</td><td>{{ plants.get(t.plant_code, t.plant_code) }}</td><td>{{ per(t.period) }}</td><td class="n">{{ q0(t.quantity) }}</td><td class="n">{{ pr(t.price) }}</td><td class="small">{{ t.reason }}</td><td class="small">{{ t.entered_by }}</td><td class="small">{{ t.since }}</td>
<td class="acts">{% if may %}<form class="inline" method="post" action="{{ url_for('plan.purchase_drop') }}"><input type="hidden" name="cell" value="{{ t.input_code }}|{{ t.plant_code }}|{{ t.period }}"><button class="act">Remove</button></form>{% endif %}</td></tr>{% endfor %}</tbody></table>{% else %}<p class="hint">Nothing typed in this plan.</p>{% endif %}
{% if last %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else ('!' if c.flag else '✕') }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}
{% elif typed %}<h2>Standing in the Plan<span class="count">{{ typed|length }} receipt{{ '' if typed|length == 1 else 's' }} on {{ version|plan }}</span></h2><table><thead><tr><th>Material</th><th>Plant</th><th>Period</th><th class="n">Quantity</th><th class="n">Price</th><th>Note</th><th>By</th></tr></thead><tbody>
{% for t in typed %}<tr><td>{{ t.input_code }}</td><td>{{ t.plant_code }}</td><td>{{ t.period }}</td><td class="n">{{ q0(t.quantity) if t.quantity is not none else '' }}</td><td class="n">{{ pr(t.price) if t.price is not none else '' }}</td><td class="small">{{ t.reason }}</td><td class="small">{{ t.entered_by }}</td></tr>{% endfor %}</tbody></table>{% endif %}
{% if not finance %}<script>window.PUR_NOTES = {{ notes|tojson }};</script>{{ note_script|safe }}{% endif %}
{{ grid_style() }}<style>table.fin td.noted{background-image:linear-gradient(225deg,var(--ink) 0 7px,transparent 7px)}
#cellnote{position:absolute;z-index:9;background:var(--panel);border:1px solid var(--ink);padding:.5rem;box-shadow:0 4px 14px rgba(0,0,0,.18);width:17rem}#cellnote textarea{width:100%;height:4.5rem;font:inherit;font-size:.85rem}#cellnote .row{display:flex;gap:.5rem;justify-content:flex-end;margin-top:.3rem}
.card.reads{padding:.6rem .9rem;margin:.4rem 0 1rem}.form-row{display:flex;flex-wrap:wrap;gap:.8rem;align-items:end;margin:.6rem 0}.form-row .grow{flex:1;display:flex;flex-direction:column}
a.card.stat.link{text-decoration:none;color:inherit;cursor:pointer}a.card.stat.link:hover{border-color:var(--ink)}a.card.stat.link.on{box-shadow:inset 0 0 0 1px var(--ink)}a.card.stat.link span::after{content:" ▸";color:var(--muted)}.card.stat .vs{margin-top:.15rem}</style>"""

# A note in a cell, as a comment in a spreadsheet: right-click (or Shift+F2) a typed-in cell, write, and it is saved with
# the table. The note belongs to the receipt — the quantity and the price of the cell share it.
NOTE_SCRIPT = """<script>(function(){
var form=document.getElementById('type'); if(!form) return; var notes=window.PUR_NOTES||{}, box=null;
function key(el){var n=el.name||''; return /^additional_(quantity|price)\\|/.test(n) ? n.slice(n.indexOf('|')+1) : null;}
function cells(k){return [].filter.call(form.querySelectorAll('input.cell'), function(i){return key(i)===k;});}
function mark(k){cells(k).forEach(function(i){var td=i.closest('td'); td.classList.toggle('noted', !!notes[k]); if(notes[k]) td.title='note: '+notes[k]; else if((td.title||'').indexOf('note: ')===0) td.removeAttribute('title');});}
function shut(){if(box){box.remove(); box=null;}}
function open(el){var k=key(el); if(!k) return; shut();
  box=document.createElement('div'); box.id='cellnote';
  box.innerHTML='<textarea placeholder="a note in this cell"></textarea><div class="row"><button type="button" class="act" data-x="0">Cancel</button><button type="button" class="act" data-x="1">Done</button></div>';
  var r=el.getBoundingClientRect(); box.style.left=Math.max(8, Math.min(window.scrollX+r.left, window.scrollX+document.documentElement.clientWidth-290))+'px'; box.style.top=(window.scrollY+r.bottom+4)+'px';
  document.body.appendChild(box); var ta=box.querySelector('textarea'); ta.value=notes[k]||''; ta.focus();
  function done(){var v=ta.value.trim(); notes[k]=v; var h=form.querySelector('input[type=hidden][data-note="'+k+'"]');
    if(!h){h=document.createElement('input'); h.type='hidden'; h.name='note|'+k; h.setAttribute('data-note', k); form.appendChild(h);} h.value=v; mark(k); shut(); el.focus();}
  box.addEventListener('click', function(e){var x=e.target.getAttribute('data-x'); if(x==='1') done(); else if(x==='0'){shut(); el.focus();}});
  ta.addEventListener('keydown', function(e){if(e.key==='Escape'){shut(); el.focus();} else if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)) done();});}
form.addEventListener('contextmenu', function(e){if(e.target.matches&&e.target.matches('input.cell')&&key(e.target)){e.preventDefault(); open(e.target);}});
form.addEventListener('keydown', function(e){if(e.key==='F2'&&e.shiftKey&&e.target.matches&&e.target.matches('input.cell')&&key(e.target)){e.preventDefault(); open(e.target);}});
Object.keys(notes).forEach(mark);
})();</script>"""

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


def _money(x: float) -> str:
    return f"{'−' if x < 0 else ''}${abs(x) / 1e6:,.2f}M"


def _avg_peak(by: dict[str, float]) -> tuple[float, float, str | None]:
    if not by:
        return 0.0, 0.0, None
    pk = max(by, key=lambda p: by[p])
    return sum(by.values()) / len(by), by[pk], pk


def aop() -> str | None:
    """The annual operating plan: the plan of the business-plan kind, the latest named."""
    r = q("select version_id from dims.ctl_version where version_kind = 'business_plan' order by from_period desc, version_id desc limit 1")
    return r[0]["version_id"] if r else None


def headlines(shown: list[dict], plan_periods: list[str], names: dict, plants: dict, version: str | None) -> list[dict]:
    """The balance's headlines over the rows the table shows (DEC-20261124-04; ambiguity #119, #120): storage — pallet
    positions at each period's peak, by the storage page's conversion; working capital — the closing value, with its
    variance to the annual operating plan over the periods both plan; turnover of the fresh materials, fastest and
    slowest. Each an average over the plan periods and a peak with its period."""
    per_pallet = {r["item_code"]: r["units_per_pallet"] for r in q("select item_code, units_per_pallet from dims.ref_storage_attribute where item_kind = 'input'")}
    fresh = {r["material_code"] for r in q("select material_code from dims.dim_input_material where is_perishable")}
    fresh |= {c for c, n in names.items() if str(n.get("is_perishable")).lower() in ("true", "1", "y")}
    pallets: dict[str, float] = {}; value: dict[str, float] = {}; unstored = set(); turns = []; no_stock = 0
    for m in shown:
        i = m["attrs"]["material"]
        for r in m["rows"]:
            if r["period"] not in plan_periods:
                continue
            value[r["period"]] = value.get(r["period"], 0.0) + (r["closing_value"] or 0.0)
            if per_pallet.get(i):
                pallets[r["period"]] = pallets.get(r["period"], 0.0) + ((r["opening_quantity"] or 0.0) + (r["purchase_quantity"] or 0.0)) / per_pallet[i]
            else:
                unstored.add(m["label"])
        if i in fresh:
            rs = [r for r in m["rows"] if r["period"] in plan_periods]
            avg = sum(r["closing_quantity"] or 0.0 for r in rs) / len(rs) if rs else 0.0
            if avg > 1e-9:
                turns.append((sum(r["consumption_quantity"] or 0.0 for r in rs) * 12 / len(rs) / avg, f"{m['label']} · {plants.get(m['attrs']['plant'], m['attrs']['plant'])}"))
            else:
                no_stock += 1
    sa, sp, spp = _avg_peak(pallets)
    wa, wp, wpp = _avg_peak(value)
    vs, says_wc = None, "the key materials' closing value, in stock — what is owed to suppliers is not netted"
    base = aop()
    if base and base != version and value:
        both = sorted(set(value) & {r["period"] for r in q("select distinct period from plan.material_stock where version_id = ?", base)})
        cells = {(m["attrs"]["material"], m["attrs"]["plant"]) for m in shown}
        b: dict[str, float] = {}
        for r in q("select input_code, plant_code, period, closing_value from plan.material_stock where version_id = ?", base):
            if (r["input_code"], r["plant_code"]) in cells and r["period"] in both:
                b[r["period"]] = b.get(r["period"], 0.0) + (r["closing_value"] or 0.0)
        if both:
            pa, pp_, _ = _avg_peak({p: value[p] for p in both})
            ba, bp, _ = _avg_peak({p: b.get(p, 0.0) for p in both})
            vs = f"vs AOP: avg {'+' if pa >= ba else ''}{_money(pa - ba)} · peak {'+' if pp_ >= bp else ''}{_money(pp_ - bp)}"
            says_wc = f"against the annual operating plan over {per(both[0])}–{per(both[-1])}, the periods both plan · " + says_wc
        else:
            vs = "vs AOP: no period in common"
    turns.sort()
    return [{"label": "Storage — avg / peak", "show": f"{sa:,.0f} / {sp:,.0f}" if pallets else "—",
             "says": (f"pallet positions at each period's peak, the peak in {per(spp)}" if pallets else "no pallet positions declared for these materials")
                     + (f" · not counted: {', '.join(sorted(unstored))}" if unstored else "")},
            {"label": "Working capital — avg / peak", "show": f"{_money(wa)} / {_money(wp)}" if value else "—", "vs": vs,
             "says": (f"the peak in {per(wpp)} · " if value else "") + says_wc},
            {"label": "Turnover, fresh — high / low", "show": f"{turns[-1][0]:,.1f} / {turns[0][0]:,.1f}" if turns else "—",
             "says": (f"turns a year: fastest {turns[-1][1]}, slowest {turns[0][1]}" if turns else "no fresh material with stock in the rows shown")
                     + (f" · {no_stock} with no stock on average left out" if no_stock else "")}]


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
                                      "short_note": "short" if r["short"] else (f"below cover {r['cover_target']:,.0f}" if r.get("below_cover") else None),
                                      "closing_quantity_cls": "over" if r["short"] else ("near" if r.get("below_cover") else ""), "typed_title": "sent by purchasing, taken as typed" if finance else "typed in this plan — listed under Typed here"}
            row["rows"].append(r)
        alerts = []                                       # a material at a plant whose closing is short or below cover, and from when
        for m in rows.values():
            sh, bc = [r["period"] for r in m["rows"] if r["short"]], [r["period"] for r in m["rows"] if r.get("below_cover")]
            if sh or bc:
                alerts.append({"code": m["code"], "short": bool(sh)})
        n_short = sum(a["short"] for a in alerts)
        alerted = request.args.get("alerted") == "1"
        if alerted:                                       # the alerts total, clicked: the table narrowed to the materials alerted
            rows = {k: m for k, m in rows.items() if m["code"] in {a["code"] for a in alerts}}
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
        shown_rows = sorted({r["code"] for r in g["rows"] if not r["current"]})           # the rows the table shows: plant, filters, find
        clearable = [d for d in drafts if f"{d['input_code']}~{d['plant_code']}" in shown_rows]
        shown = [rows[tuple(c.split("~", 1))] for c in shown_rows if tuple(c.split("~", 1)) in rows]
        cards = headlines(shown, vp["plan"], names, plants, version) + [
            {"label": "Closing alerts", "show": str(len(alerts)), "href": figures.here(alerted=None if alerted else "1"), "on": alerted,
             "says": ((f"{n_short} short, {len(alerts) - n_short} below cover — " + ("the table shows only these; click to show every material" if alerted else "click to show only these in the table"))
                      if alerts else "no closing is short or below its cover")}]
        where = plants.get(loc, loc) if loc != "ALL" else ("both plants" if finance else ", ".join(plants.get(x, x) for x in p["plants"]))
        return page(figures.MACROS + MACRO + PAGE, title="Material stock" if finance else "Material balance", active="material_stock" if finance else "purchases", width="none",
                    finance=finance, version=version, p=p, where=where, g=g, others=others, typed=typed, cards=cards, source_says=SOURCE_SAYS, may=may,
                    n_rows=len(rows), last=session.last, receipt_acts=("purchase.type", "purchase.clear"), drafts=drafts, clearable=clearable,
                    clear_rows=sorted({f"{d['input_code']}~{d['plant_code']}" for d in clearable}), n_changed=n_changed, names=names, plants=plants,
                    reads=purchasing_plan.reads_of(p) if p else None, per=per, when=when, note_script=NOTE_SCRIPT,
                    notes={f"{d['input_code']}~{d['plant_code']}|{d['period']}": d["reason"] for d in drafts if d.get("reason")})

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
            {"check": "a quantity and a price together", "ok": bool(changed) and not bad, "says": "; ".join(bad) if bad else (cells or "nothing typed differs from what the table showed")},
        ]
        kept = receipts.judge(checks)
        if kept:
            purchasing_plan.type_cells(p["id"], changed, reason, who)
        session.last = receipts.write("purchase.type", who, f"{len(changed)} cells", checks, kept)
        session.say(f"{len(changed)} receipt{'s' if len(changed) != 1 else ''} kept in {p['name']} — send a snapshot from My plans to put {'them' if len(changed) != 1 else 'it'} into an IBP plan" if kept
                    else "refused: " + "; ".join(x["says"] for x in checks if not x["ok"]), kept)
        return redirect(figures.back(url_for("plan.material_purchases", location=request.form.get("location") or None) + "#typed"))

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
        have = {purchasing_plan._cell(t): t.get("reason") or "" for t in purchasing_plan.typed(p["id"])}
        notes = {}
        for name, raw in f.items():                        # a note written in a cell: note|<row>|<period>
            tag, _, rest = name.partition("|")
            code, _, period = rest.rpartition("|")
            inp, _, plant = code.partition("~")
            cell = (inp, plant, period)
            if tag == "note" and cell in now and period in plan_periods and raw.strip() != have.get(cell, ""):
                notes[cell] = raw.strip()
                if cell in have or raw.strip():            # on a cell not typed, the note keeps the receipt as the cell shows it
                    changed.setdefault(cell, {"quantity": None, "price": None})
        for cell, d in changed.items():                    # the half not typed is the figure the cell shows (#115)
            for field, k in (("quantity", "additional_quantity"), ("price", "additional_price")):
                shown = now[cell].get(k)
                if d[field] is None and shown is not None and (shown > 0 or field == "quantity"):
                    d[field] = shown
        return keep(p, changed, bad, notes, who)

    @bp.post("/purchasing/balance/clear")
    def purchase_clear():
        """Every receipt typed in the plan for the rows the page showed, cleared in one act — the only way receipts go
        together without being replaced; each cell is empty again (DEC-20261121-02 (d))."""
        who = who_fn()
        p = _plan_posted(who)
        rows = {tuple(x.split("~", 1)) for x in (request.form.get("rows") or "").split(",") if "~" in x}
        n = purchasing_plan.clear(p["id"], rows) if p and roles.may(who, VERB) and rows else 0
        checks = [{"check": "who may plan purchases", "ok": roles.may(who, VERB), "says": f"{who} holds {said(VERB)}" if roles.may(who, VERB) else f"{who} does not hold {said(VERB)}"},
                  {"check": "a plan of yours", "ok": bool(p), "says": p["name"] if p else "no plan of yours is chosen"},
                  {"check": "receipts typed in the rows shown", "ok": n > 0, "says": f"{n} cleared — each cell is empty" if n else "nothing typed there"}]
        session.last = receipts.write("purchase.clear", who, f"{n} receipts", checks, n > 0)
        session.say(f"{n} typed receipt{'s' if n != 1 else ''} cleared from {p['name']} — what stands in an IBP plan changes only when a snapshot is sent" if n
                    else "nothing cleared", bool(n))
        return redirect(url_for("plan.material_purchases") + "#typed")

    @bp.post("/purchasing/balance/drop")
    def purchase_drop():
        who = who_fn()
        p = _plan_posted(who)
        cell = tuple((request.form.get("cell") or "").split("|"))
        if p and roles.may(who, VERB) and len(cell) == 3:
            purchasing_plan.drop(p["id"], cell)
            session.say(f"removed from {p['name']} — what stands in an IBP plan changes only when a snapshot is sent", True)
        return redirect(url_for("plan.material_purchases") + "#typed")
