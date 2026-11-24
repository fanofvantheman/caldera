"""One table of figures: the rows down — each row one thing, held where it is held — the plan's periods across, one
measure a line. A page declares what it shows; this module draws it, and knows nothing of what the figures are.

The columns are a plan's periods (`columns`): the actual periods of the year it is named for, marked; its plan periods
of that year; the year; the plan periods past it; then a column a quarter where the plan reaches by quarter.

A page declares to it (`table`):
- its **rows** — a code, a name, the line beneath the name, the attributes a filter reads, and the figures by period;
- its **measures** — what each is called, how it is shown, how the year and a quarter read it (a sum, the last period,
  the first, or nothing), whether the rows add up to a total, which field says it was typed, and whether it is typed
  here; one **leads**, and a row opens to the rest in their order — or, as a **movement** table, every row shows every
  measure, each a line under its group (volume, value, …), and no measure is chosen;
- its **filters** — a choice on what the rows carry, and part of a name typed; a filter narrows the rows and never
  changes a figure;
- whether its cells may be typed, and where a typed figure goes (`posted` reads the form back);
- a mark on a figure: a row's `<measure>_cls` in a period is added to the cell's class (over, near).

A page whose rows are made its own way (a working copy that recalculates as it is typed) builds the same row and cell
dicts and draws them with the same macros (`MACROS`):

  row  — code, label, level (the line under the name), depth (0 the total, 1, 2), lvl, href (opens one level down, ▸),
         current, built, toggle ({href, label}: the row's other measures), lines [{key, label}], cells {key: [cell, …]}
  cell — show, cls, title, src (a small line beneath the figure), built, input/value/live (a typed cell), undo/withdraw
         (the mark on a typed figure), moved (◆)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from flask import request, url_for


@dataclass(frozen=True)
class Measure:
    key: str                          # the field on a row's figures
    label: str                        # the line's name, lower case
    shown: str = "count"              # count | money | price | pct
    year: str | None = "sum"          # how the year and a quarter read it: sum | last | first | None (left empty)
    total: bool = True                # the rows add up to the total row
    typed: str | None = None          # the field that says the figure was typed in the period (boxed)
    note: str | None = None           # a field whose words are shown beneath the figure
    input: bool = False               # typed here, in a plan period, where the page lets its reader type
    group: str | None = None          # the heading the line sits under in a movement table (volume, value, cost basis)


@dataclass(frozen=True)
class Filter:
    key: str
    label: str
    options: tuple                    # ((value, label), …)


def columns(vp: dict, fy: int | None = None, actuals: bool = True, quarters: bool = True) -> dict:
    """The columns of a plan (`vp`, as `reads.version_periods` gives it): its actual periods of the year it is named for,
    marked and never typed, then its plan periods for the horizon — past the year end — with the year's total after the
    year's last period, then a column a quarter past the months — the sum of its periods; a part quarter holds the
    periods the months leave in it."""
    fy = vp.get("fy") or fy
    periods = [{"period": p["period"], "label": f"P{p['fiscal_period']:02d}" if p["fiscal_year"] == fy else f"FY{str(p['fiscal_year'])[2:]} P{p['fiscal_period']:02d}",
                "actual": p["actual"], "fy": p["fiscal_year"]} for p in vp["periods"] if actuals or not p["actual"]]
    in_fy = [p for p in periods if p["fy"] == fy]
    cols = in_fy + [{"period": "FY", "label": f"FY{fy}", "total": True}] + [p for p in periods if p["fy"] != fy]
    qcols = [{"period": x["id"], "label": x["label"], "quarter": True, "periods": x["periods"], "fy": x["fiscal_year"], "part": x["part"],
              "title": f"{x['label']} — {', '.join(x['periods'])}: the sum of {'its periods' if not x['part'] else 'the ' + str(len(x['periods'])) + ' periods past the months'}"}
             for x in vp["quarter_cols"]] if quarters else []
    return {"fy": fy, "periods": periods, "in_fy": in_fy, "cols": cols + qcols, "qcols": qcols, "q_periods": [per for x in qcols for per in x["periods"]]}


def show(m: Measure, x) -> str:
    if x is None:
        return ""
    if m.shown == "price":
        return f"{x:,.4f}" if abs(x) < 1 else f"{x:,.2f}"
    if m.shown == "pct":
        return f"{x:.0%}"
    return f"{x:,.0f}"


def input_value(m: Measure, x) -> str:
    """A typed cell's figure as its input holds it — what `posted` compares against to know it was changed."""
    if x is None:
        return ""
    return (f"{x:.4f}" if abs(x) < 1 else f"{x:.2f}") if m.shown == "price" else f"{x:.0f}"


def _read(m: Measure, xs: list) -> float | None:
    vals = [x for x in xs if x is not None]
    if not vals or m.year is None:
        return None
    return sum(vals) if m.year == "sum" else vals[-1] if m.year == "last" else vals[0]


def here(**kw) -> str:
    """This page's address with some of its arguments changed — the context and every filter carried."""
    args = request.args.to_dict()
    args.update(kw)
    return url_for(request.endpoint, **{k: v for k, v in args.items() if v not in (None, "")})


def back(default: str) -> str:
    """Where a save returns to: the address its page was posted from (the bar's `back`, same filters), else `default`."""
    b = (request.form.get("back") or "").strip()
    return b if b.startswith("/") and not b.startswith("//") else default


def chosen(filters: list[Filter]) -> tuple[dict, str]:
    """The filters as the address holds them: each filter's value, and the part of a name typed."""
    return ({f.key: request.args.get(f"f_{f.key}", "") for f in filters if request.args.get(f"f_{f.key}", "") in {v for v, _ in f.options}},
            (request.args.get("find") or "").strip())


def table(id: str, rows: list[dict], measures: list[Measure], lead: str, cols: dict, *, row_head: str, filters: list[Filter] = (),
          total: str | None = None, editable: bool = False, plan_periods: set | frozenset = frozenset(), actual_title: str = "",
          year_says: str | None = None, empty: str = "Nothing to show.", movement: bool = False) -> dict:
    """The table a page declares, ready to draw with `grid_table`. `rows`: [{code, label, level, attrs: {filter key: value},
    by: {period: {field: value}}}]. The measure chosen above the table (`?measure=`) leads, or the page's own; a row opened
    (`?open=`) shows every measure in its order; in a `movement` table every row shows every measure. A cell may be typed where `editable`, its measure is typed here and the
    period is one of `plan_periods`."""
    by_key = {m.key: m for m in measures}
    lead = request.args.get("measure") if request.args.get("measure") in by_key else lead
    picked, find = chosen(list(filters))
    shown = [r for r in rows if all((r.get("attrs") or {}).get(k) == v for k, v in picked.items())
             and (not find or find.lower() in f"{r['label']} {r['code']}".lower())]
    opened = {c for c in (request.args.get("open") or "").split(",") if c}
    fy_periods = [p["period"] for p in cols["in_fy"]]

    def cells(r: dict, m: Measure) -> list[dict]:
        out = []
        for p in cols["cols"]:
            x = {"show": "", "cls": "", "title": "", "src": None, "built": None, "input": None, "moved": False}
            if p.get("total") or p.get("quarter"):
                x["cls"] = "tot" if p.get("total") else "qtr"
                ps = fy_periods if p.get("total") else p["periods"]
                x["show"] = show(m, _read(m, [(r["by"].get(per) or {}).get(m.key) for per in ps]))
                if m.year == "last" and ps:               # a year or quarter read as its last period carries that period's mark
                    mk = (r["by"].get(ps[-1]) or {}).get(m.key + "_cls")
                    if mk:
                        x["cls"] += " " + mk
            else:
                f = r["by"].get(p["period"]) or {}
                v = f.get(m.key)
                if p.get("actual"):
                    x["cls"] = "actual"
                x["show"] = show(m, v)
                if m.typed and f.get(m.typed):
                    x["cls"] += " typed"
                    x["title"] = f.get("typed_title") or "typed over the calculated figure"
                if m.note and f.get(m.note):
                    x["src"] = f[m.note]
                if f.get(m.key + "_cls"):                # a mark the page puts on a figure (over, near)
                    x["cls"] += " " + f[m.key + "_cls"]
                if editable and m.input and r.get("typed_here", True) and p["period"] in plan_periods and f:
                    x["input"], x["value"], x["live"] = f"{m.key}|{r['code']}|{p['period']}", input_value(m, v), None
            out.append(x)
        return out

    def line(r: dict, total_row: bool = False) -> dict:
        open_ = r["code"] in opened or (movement and not total_row)
        # the total carries what adds up: the lead where it does, else every measure that does (quantities in different units do not)
        ms = measures if open_ else ([by_key[lead]] if not (total_row and movement) and (not total_row or by_key[lead].total) else [m for m in measures if m.total])
        others = len(measures) - len(ms)
        toggle = {"href": here(open=",".join(sorted(opened - {r["code"]})) if open_ else ",".join(sorted(opened | {r["code"]}))),
                  "label": "close" if open_ else f"{others} more"} if (others or open_) and not movement else None
        return {"code": r["code"], "label": r["label"], "current": total_row, "href": r.get("href"), "depth": 0 if total_row else 1, "lvl": r.get("lvl"),
                "level": r.get("level", ""), "built": "", "toggle": toggle,
                "lines": [{"key": m.key, "label": m.label, "group": m.group if movement and (i == 0 or ms[i - 1].group != m.group) else None} for i, m in enumerate(ms)],
                "cells": {m.key: cells(r, m) if (not total_row or m.total) else [{"show": "", "cls": "tot" if p.get("total") else "", "title": "", "src": None,
                                                                                    "built": None, "input": None, "moved": False} for p in cols["cols"]] for m in ms}}

    out = []
    if total and shown:
        tot_by: dict = {}
        for r in shown:
            for per, f in r["by"].items():
                t = tot_by.setdefault(per, {})
                for m in measures:
                    if m.total and f.get(m.key) is not None:
                        t[m.key] = (t.get(m.key) or 0.0) + f[m.key]
        out.append(line({"code": "ALL", "label": total, "level": f"the total of the {len(shown)} rows beneath", "by": tot_by}, total_row=True))
    out += [line(r) for r in shown]
    return {"id": id, "row_head": row_head, "periods": cols["cols"], "rows": out, "actual_title": actual_title, "year_says": year_says,
            "measures": [{"key": m.key, "label": m.label, "on": m.key == lead, "href": here(measure=m.key)} for m in measures], "lead": lead,
            "filters": [{"key": f.key, "label": f.label, "options": f.options, "value": picked.get(f.key, "")} for f in filters], "find": find,
            "n_shown": len(shown), "n_all": len(rows), "empty": empty, "editable": editable, "movement": movement}


def posted(form, measures: list[Measure]) -> list[tuple[str, str, str, str]]:
    """The typed cells a form sent: (measure, row code, period, the figure as typed), for the measures typed here."""
    keys = {m.key for m in measures if m.input}
    out = []
    for name, raw in form.items():
        k, _, rest = name.partition("|")
        code, _, period = rest.rpartition("|")
        if k in keys and code and period:
            out.append((k, code, period, raw.strip()))
    return out


# The one save bar (DEC-20261124-03): a page where figures are typed in a table saves with it, pinned to the foot of the
# window — "Save changes", "Discard changes" beside it where the page holds typed work, and how many figures are typed and
# not saved. A page puts what it asks for with a save (a reason, a note) inside it with {% call %}. A form of its own that
# holds only the bar takes the class `savebar-form`, so it stays pinned. After a save the handler returns to `back(...)`
# and the page to where it was scrolled.
SAVE_BAR = """{% macro save_bar(discard=none, held=0, note='') %}<div class="savebar" data-held="{{ held or 0 }}">{% if caller %}{{ caller() }}{% endif %}<button class="primary" data-save>Save changes</button>{% if discard %}<button class="act" {% if discard == 'reset' %}type="button"{% else %}formaction="{{ discard }}" formnovalidate{% endif %} data-discard="{{ discard }}">Discard changes</button>{% endif %}<span class="hint savecount" aria-live="polite"></span>{% if note %}<span class="hint grow">{{ note }}</span>{% endif %}<input type="hidden" name="back" data-back></div><style>.savebar{position:sticky;bottom:0;z-index:3;display:flex;flex-wrap:wrap;gap:.8rem;align-items:end;background:var(--panel);border-top:1px solid var(--ink);padding:.6rem .9rem;margin:0 0 .6rem}.savebar .grow{flex:1}.savebar .savecount{align-self:center}.savebar.dirty .savecount{font-weight:600;color:var(--ink)}form.savebar-form{position:sticky;bottom:0;z-index:3}form.savebar-form .savebar{margin:0}</style>
<script>(function(){if(window.__savebar)return;window.__savebar=1;
function n(b){var f=b.closest('form'),c=0;if(f)[].forEach.call(f.querySelectorAll('input.cell'),function(i){if(i.value!==i.defaultValue)c++;});var x=document.querySelectorAll('form input.cell');if(f&&!f.querySelector('input.cell'))[].forEach.call(x,function(i){if(i.value!==i.defaultValue)c++;});return c+(+b.getAttribute('data-held')||0);}
function say(){[].forEach.call(document.querySelectorAll('.savebar'),function(b){var k=n(b),s=b.querySelector('.savecount');s.textContent=k?k+' figure'+(k==1?'':'s')+' typed and not saved':'nothing typed and not saved';b.classList.toggle('dirty',k>0);});}
document.addEventListener('input',function(e){if(e.target.matches&&e.target.matches('input.cell'))say();});
function line(n){var k=n.lastIndexOf('|');return k>0?n.slice(0,k):null;}
document.addEventListener('focusin',function(e){var i=e.target;if(i.matches&&i.matches('input.cell'))i.setAttribute('data-was',i.value);});
document.addEventListener('input',function(e){var i=e.target;if(!(i.matches&&i.matches('input.cell')))return;if(i.value.indexOf('>')<0){i.setAttribute('data-was',i.value);return;}var v=i.value.replace(/>/g,'').trim();if(v==='')v=i.hasAttribute('data-was')?i.getAttribute('data-was'):i.defaultValue;i.value=v;var tr=i.closest('tr'),me=line(i.name||'');if(!tr||!me)return;var all=[].slice.call(tr.querySelectorAll('input.cell')),right=all.slice(all.indexOf(i)+1).filter(function(x){return line(x.name||'')===me&&!x.disabled&&!x.readOnly;});right.forEach(function(x){x.value=v;x.dispatchEvent(new Event('input',{bubbles:true}));});[i].concat(right).forEach(function(x){x.dispatchEvent(new Event('change',{bubbles:true}));});say();});
document.addEventListener('click',function(e){var d=e.target.closest&&e.target.closest('[data-discard="reset"]');if(!d)return;var f=d.closest('form');[].forEach.call(f.querySelectorAll('input.cell'),function(i){i.value=i.defaultValue;});[].forEach.call(f.querySelectorAll('input[data-note]'),function(h){h.remove();});say();});
document.addEventListener('submit',function(e){var b=e.target.querySelector('.savebar [data-back]');if(!b)return;b.value=location.pathname+location.search;try{sessionStorage.setItem('savebar-y:'+location.pathname,String(window.scrollY));}catch(x){}var s=e.submitter;if(s&&s.hasAttribute('data-save'))s.textContent='Saving…';},true);
function back(){try{var k='savebar-y:'+location.pathname,y=sessionStorage.getItem(k);if(y!==null){sessionStorage.removeItem(k);window.scrollTo(0,+y);}}catch(x){}say();}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',back);else back();})();</script>{% endmacro %}
"""

# The markup. `g` is the table (from `table`, or a page's own dict with the same keys); the id prefixes every element so
# a part can be replaced by its id.
MACROS = SAVE_BAR + """{% macro grid_head(g) %}<thead><tr><th>{{ g.row_head }}</th><th></th>{% for p in g.periods %}{% if p.total %}<th class="n tot"{% if g.year_says %} title="{{ g.year_says }}"{% endif %}>{{ p.label }}{% if g.year_says %}<div class="small muted">{{ g.year_says }}</div>{% endif %}</th>{% elif p.quarter %}<th class="n qtr" title="{{ p.title }}">{{ p.label }}<div class="small muted">{{ 'quarter' if not p.part else p.periods|length ~ ' periods' }}</div></th>{% else %}<th class="n {{ 'actual' if p.actual }}"{% if p.actual %} title="{{ g.actual_title }}"{% endif %}>{{ p.label }}{% if p.actual %}<div class="small muted">actual</div>{% endif %}</th>{% endif %}{% endfor %}</tr></thead>{% endmacro %}
{% macro grid_row(g, r) %}<tbody id="{{ g.id }}-r-{{ r.code }}">{% for m in r.lines %}<tr class="{{ 'first' if loop.first }} {{ 'total' if r.current and loop.first }}">
{% if loop.first %}<td rowspan="{{ r.lines|length }}" class="node d{{ r.depth }}{% if r.lvl %} lv-{{ r.lvl }}{% endif %}"><div class="nm">{% if r.href %}<a href="{{ r.href }}" tabindex="-1" title="open {{ r.label }}: what is beneath it becomes the rows">{{ r.label }}&nbsp;<span class="opens" aria-hidden="true">▸</span></a>{% else %}<span>{{ r.label }}</span>{% endif %}<div class="small muted">{{ r.level }}{% if r.built %} · {{ r.built }}{% endif %}</div>{% if r.toggle %}<a class="more small" href="{{ r.toggle.href }}" tabindex="-1">{{ r.toggle.label }}</a>{% endif %}</div></td>{% endif %}
<td class="small muted">{% if m.group %}<div class="grp">{{ m.group }}</div>{% endif %}{{ m.label }}</td>
{% for x in r.cells[m.key] %}<td class="n {{ x.cls }}"{% if x.title %} title="{{ x.title }}"{% endif %}>{% set mark %}{% if x.undo %}<button class="one" form="{{ g.id }}-one" formaction="{{ g.undo_action }}" name="figure" value="{{ x.undo }}" tabindex="-1" title="take this figure out — {{ x.title }}" aria-label="take this figure out">↶</button>{% elif x.withdraw %}<a class="one" href="{{ x.withdraw }}" tabindex="-1" title="withdraw this figure — shows what will change first" aria-label="withdraw this figure">↶</a>{% endif %}{% endset %}{% if x.input %}<span class="inp"><input class="cell" name="{{ x.input }}" value="{{ x.value }}" inputmode="decimal" data-live='{{ x.live|tojson }}'>{{ mark }}</span>{% else %}{{ mark }}{{ x.show }}{% endif %}{% if x.moved %}<span class="moved">◆</span>{% endif %}{% if x.src is not none %}<span class="src">{{ x.src }}</span>{% endif %}{% if x.built %}<span class="src">built {{ x.built }}</span>{% endif %}</td>{% endfor %}
</tr>{% endfor %}</tbody>{% endmacro %}
{% macro grid_choice(g) %}<form class="toolbar gridpick" method="get">{{ context_fields() }}{% for k in ('measure', 'open', 'alerted') %}{% if request.args.get(k) %}<input type="hidden" name="{{ k }}" value="{{ request.args.get(k) }}">{% endif %}{% endfor %}
{% if not g.movement %}<span class="seg"><span class="small muted">the rows show</span>{% for m in g.measures %}{% if m.on %}<b>{{ m.label }}</b>{% else %}<a href="{{ m.href }}">{{ m.label }}</a>{% endif %}{% endfor %}</span>{% endif %}
{% for f in g.filters %}<label class="small">{{ f.label }} <select name="f_{{ f.key }}" onchange="this.form.submit()"><option value="">all</option>{% for v, lab in f.options %}<option value="{{ v }}" {{ 'selected' if v == f.value }}>{{ lab }}</option>{% endfor %}</select></label>{% endfor %}
<label class="small">find <input name="find" value="{{ g.find }}" size="12" placeholder="part of a name"></label><button class="act">Filter</button>{% if g.n_shown != g.n_all %} <span class="small muted">{{ g.n_shown }} of {{ g.n_all }} rows</span> <a class="small" href="{{ request.path }}?{% for k in ('version', 'location', 'material', 'customer') %}{% if request.args.get(k) %}{{ k }}={{ request.args.get(k)|urlencode }}&amp;{% endif %}{% endfor %}">clear</a>{% endif %}</form>{% endmacro %}
{% macro grid_table(g) %}<div class="finwrap"><table class="fin">{{ grid_head(g) }}
{% for r in g.rows %}{{ grid_row(g, r) }}{% else %}<tbody><tr><td colspan="{{ g.periods|length + 2 }}" class="muted">{{ g.empty }}</td></tr></tbody>{% endfor %}
</table></div>{% endmacro %}
{% macro grid_style() %}<style>.finwrap{overflow-x:auto;margin-bottom:.6rem}table.fin td.small.muted{white-space:nowrap}table.fin td.n{vertical-align:top;white-space:nowrap}table.fin td.node{vertical-align:top;min-width:11rem}
table.fin tr.first td{border-top:1px solid var(--rule)}table.fin td.node .nm{font-weight:400}table.fin td.node.d0 .nm{font-weight:700}table.fin td.node.lv-product .nm,table.fin td.node.lv-category .nm{font-weight:600}
table.fin td.node.d1 .nm{margin-left:.2rem;padding-left:.7rem;border-left:1px solid var(--rule)}table.fin td.node.d2 .nm{margin-left:1.4rem;padding-left:.7rem;border-left:1px solid var(--rule)}table.fin td.node .opens{color:var(--muted)}table.fin td.node .small{font-weight:400}
table.fin td.node .more{display:inline-block;margin-top:.15rem;color:var(--muted)}table.fin .src{display:block;font-size:.72rem;color:var(--muted)}table.fin td.typed{box-shadow:inset 0 0 0 1px var(--ink)}
table.fin .inp{position:relative;display:inline-block}table.fin .one{padding:0;border:0;background:none;color:var(--muted);font-size:.85rem;line-height:1;text-decoration:none;cursor:pointer;margin-right:.3rem}table.fin .inp .one{position:absolute;left:.35rem;top:50%;transform:translateY(-50%);margin:0}table.fin .one:hover,table.fin .one:focus{color:var(--ink)}
table.fin td.unsaved{background:repeating-linear-gradient(135deg,transparent 0 5px,color-mix(in srgb,var(--muted) 14%,transparent) 5px 6px)}table.fin td.unsaved input.cell{font-style:italic}
table.fin td.actual,table.fin th.actual{color:var(--muted);background:var(--soft)}table.fin td.tot,table.fin th.tot{border-left:1px solid var(--rule);border-right:1px solid var(--rule)}table.fin input.cell{width:5.6rem;text-align:right;font-size:.85rem;padding:.15rem .35rem}
.moved{font-size:.7rem;margin-left:.15rem}table.fin .grp{color:var(--ink);font-weight:600;margin-top:.3rem}table.fin td.down{color:var(--muted)}table.fin td.over{font-weight:700;color:var(--bad,#c0392b)}table.fin td.near{font-weight:600;color:var(--warn,#b7791f)}
.toolbar .seg{display:inline-flex;gap:.6rem;margin-left:auto}.toolbar .seg b{font-weight:600}.gridpick{display:flex;flex-wrap:wrap;gap:.8rem;align-items:center}.gridpick .seg{margin-left:0}</style>{% endmacro %}"""
