"""Reports a person makes (DEC-20261114-02): a saved question over the measure register, drawn in the face as whoever
opens it.

A report declares its measures (from `plan.ref_grid_measure` — every model's outputs, each with where it is read and the
axes it can be cut by), what is on the rows (an axis and a level of its structure), what is across (periods or years), the
versions, whether the first is read less the second, and filters. It asks only for what the plan defines: each measure
adds up by its own registered rule — a price is a ratio of its parts at every node, never a sum — so every figure on a
report is one the plan already stands behind. It is one row in a register (`plan/reg_report`), read here from the
landing at once: a report is a question, not a figure, and needs no run to be kept.

It reads as whoever opens it: no figure without the right to read the plan, and a cell that a withheld line reaches
(labour paid by name, without the right to read individual pay) is shown withheld, never left out of a total that would
then misstate. A planner's own scope is not applied in this step. Pick builds a declaration on a page; an assistant that
writes the same declaration from a sentence is not built — Caldera has no assistant. Registered on the plan's blueprint
by `register(...)`, called from `face/__main__.py`."""
from __future__ import annotations

import csv
import datetime as dt
from collections import defaultdict

from chassis import receipts
from chassis.landing import LogLanding
from chassis.warehouse import Busy, q
from flask import redirect, request, url_for

from .words import said

COLUMNS = ["report_id", "owner", "report_name", "measures", "rows_axis", "rows_level", "columns_axis", "versions", "compare",
           "filter_material", "filter_customer", "saved_on"]
LANDING = LogLanding("plan", "reg_report", COLUMNS)
READ = "read.plan"
# the axes a reader knows: the column each is read from, and for a structure the hierarchy and the leaf level
AXES = {"material": ("material_code", "dims.dim_material_hierarchy", "material", ["all", "category", "product", "material"]),
        "customer": ("account_code", "dims.dim_customer_hierarchy", "account", ["all", "planning_unit", "account"]),
        "period": ("period", None, None, []), "fiscal_year": ("fiscal_year", None, None, []), "entity": ("entity_code", None, None, []),
        "cost_centre": ("cost_centre_code", None, None, []), "account": ("account_code", None, None, []),
        "category": ("category_code", None, None, []), "channel": ("channel", None, None, [])}
AXIS_SAID = {"material": "material", "customer": "customer", "period": "period", "fiscal_year": "fiscal year", "entity": "entity",
             "cost_centre": "cost centre", "account": "account", "category": "category", "channel": "channel"}

PICK = """<h1>Reports<small>a saved question over the plan's own measures — drawn as whoever opens it; every figure is one the plan already stands behind</small></h1>
<h2>Yours<span class="count">{{ mine|length }}</span></h2>
<table><thead><tr><th>Report</th><th>Measures</th><th>Rows</th><th>Across</th><th>Versions</th><th>Saved</th></tr></thead><tbody>
{% for r in mine %}<tr><td><a href="{{ url_for('plan.report', report_id=r.report_id) }}"><b>{{ r.report_name }}</b></a>{% if r.waiting %} <span class="small muted">saved</span>{% endif %}</td><td class="small">{{ r.measures_said }}</td><td class="small">{{ r.rows_said }}</td>
<td class="small">{{ r.columns_said }}</td><td class="small">{{ (r.versions or '').replace(';', ', ') }}{% if r.compare %} · the first less the second{% endif %}</td><td class="small">{{ (r.saved_on or '')[:10] }}</td></tr>
{% else %}<tr><td colspan="6" class="muted">None yet — pick one below.</td></tr>{% endfor %}</tbody></table>
{% if may %}<h2>Make one<span class="count">choose from what the plan defines</span></h2>
<form method="post" action="{{ url_for('plan.report_save') }}">
<div class="form-row"><label class="small grow">name <input name="report_name" required placeholder="what the report answers"></label></div>
{% for g in grids %}<fieldset><legend>{{ g.label }}</legend>{% for m in g.measures %}<label class="small pick"><input type="checkbox" name="measure" value="{{ m.key }}"> {{ m.label }} <span class="muted">· {{ m.rollup_says }} · by {{ m.axes_said }}</span></label>{% endfor %}</fieldset>{% endfor %}
<div class="form-row"><label class="small">rows <select name="rows">{% for o in row_options %}<option value="{{ o.value }}">{{ o.label }}</option>{% endfor %}</select></label>
<label class="small">across <select name="columns_axis"><option value="fiscal_year">fiscal years</option><option value="period">periods</option></select></label>
<label class="small">versions <select name="versions" multiple size="3">{% for v in versions %}<option value="{{ v.version_id }}" {{ 'selected' if loop.first }}>{{ v.version_id }}</option>{% endfor %}</select></label>
<label class="small"><span><input type="checkbox" name="compare" value="Y"> the first less the second</span></label>
<label class="small">material <input name="filter_material" size="12" placeholder="all"></label><label class="small">customer <input name="filter_customer" size="10" placeholder="all"></label></div>
<p><button class="primary">Save the report</button> <span class="hint">a question, not a copy of figures: it is drawn fresh each time it is opened, as whoever opens it</span></p></form>{% endif %}
{% if last and last.act == 'report.save' %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else '✕' }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}
<p class="hint">Asked in a sentence is not offered: the plan has no assistant yet. A report shared by its link reads as whoever opens it.</p>
<style>fieldset{border:1px solid var(--rule);margin:.6rem 0;padding:.4rem .8rem}legend{font-weight:600}.pick{display:block}.form-row{display:flex;flex-wrap:wrap;gap:.8rem;align-items:end;margin:.6rem 0}.form-row .grow{flex:1;display:flex;flex-direction:column}.form-row label{display:flex;flex-direction:column;gap:.2rem}</style>"""

DRAW = """<h1>{{ r.report_name }}<small>{{ r.rows_said }} × {{ r.columns_said }}{% if r.versions %} · {{ r.versions.replace(';', ', ') }}{% endif %}{% if filters %} · {{ filters }}{% endif %} · made by {{ r.owner }}, drawn as {{ reader }}</small></h1>
{% if refused %}<p class="lede">{{ refused }}</p>{% else %}
{% for t in tables %}<h2>{{ t.title }}<span class="count">{{ t.says }}</span></h2>
{% if t.note %}<p class="hint">{{ t.note }}</p>{% endif %}
<div class="finwrap"><table><thead><tr><th>{{ r.rows_said }}</th>{% for c in t.cols %}<th class="n">{{ c }}</th>{% endfor %}</tr></thead><tbody>
{% for row in t.rows %}<tr class="{{ 'total' if row.total }}"><td>{% if row.total %}<b>{{ row.label }}</b>{% else %}{{ row.label }}{% endif %}</td>{% for x in row.cells %}<td class="n">{{ x }}</td>{% endfor %}</tr>{% else %}<tr><td colspan="{{ t.cols|length + 1 }}" class="muted">Nothing.</td></tr>{% endfor %}</tbody></table></div>{% endfor %}{% endif %}
{% if held_from %}<p class="hint">Each version is read as its own models hold it: {% for v in held_from %}{{ v.version_id }} plans from {{ v.after }}{% if v.actual %} — its actual months before that are not part of it{% endif %}{{ '; ' if not loop.last }}{% endfor %}. A difference is read only where both versions have the figure.</p>{% endif %}
<p class="hint">Each figure adds up by its measure's own rule — <a href="{{ url_for('plan.rules') }}">how each figure is calculated</a>. Drawn now from the plan as the last run left it; nothing is stored with the report but the question. <a href="{{ url_for('plan.reports') }}">Reports</a></p>
<style>.finwrap{overflow-x:auto}</style>"""


def measures() -> dict[str, dict]:
    """Every measure a report may ask for: the register's rows that say where they are read — with a column, or as a
    ratio of two that have one."""
    rows = q("select * from plan.ref_grid_measure where relation is not null order by grid, ord")
    by = {(r["grid"], r["measure"]): r for r in rows}
    out = {}
    for r in rows:
        if r["value_column"] or (r["rollup"] == "ratio" and all((by.get((r["grid"], x)) or {}).get("value_column") for x in (r["rollup_num"], r["rollup_den"]))):
            out[f"{r['grid']}.{r['measure']}"] = {**r, "key": f"{r['grid']}.{r['measure']}", "axes_list": (r["axes"] or "").split(","),
                                                   "num": by.get((r["grid"], r["rollup_num"])), "den": by.get((r["grid"], r["rollup_den"]))}
    return out


def declarations() -> list[dict]:
    """Every report: the register as the last run left it, and every save since, from the landing — the latest per report."""
    out = {r["report_id"]: {**r, "waiting": False} for r in q("select * from plan.report")}
    for path in LANDING.pending():
        with open(path, newline="") as fh:
            for r in csv.DictReader(fh):
                out[r["report_id"]] = {**r, "compare": r.get("compare") == "Y", "rows_level": r.get("rows_level") or None,
                                       "versions": r.get("versions") or None, "filter_material": r.get("filter_material") or None,
                                       "filter_customer": r.get("filter_customer") or None, "waiting": True}
    return list(out.values())


def _said(r: dict, ms: dict) -> dict:
    keys = [k for k in (r["measures"] or "").split(";") if k]
    return {**r, "keys": keys, "measures_said": ", ".join(f"{ms[k]['grid_label']} · {ms[k]['label']}" if k in ms else f"{k} (no longer in the register)" for k in keys),
            "rows_said": AXIS_SAID.get(r["rows_axis"], r["rows_axis"]) + (f" by {r['rows_level'].replace('_', ' ')}" if r.get("rows_level") else ""),
            "columns_said": "fiscal years" if r["columns_axis"] == "fiscal_year" else AXIS_SAID.get(r["columns_axis"], r["columns_axis"])}


def checks_for(d: dict, ms: dict, who: str, roles, known_versions: set) -> list[dict]:
    keys = [k for k in d["measures"].split(";") if k]
    unknown = [k for k in keys if k not in ms]
    rows_ok = all(d["rows_axis"] in ms[k]["axes_list"] for k in keys if k in ms)
    cols_ok = all(d["columns_axis"] in ms[k]["axes_list"] for k in keys if k in ms)
    level_ok = d["rows_axis"] not in ("material", "customer") or d.get("rows_level") in AXES[d["rows_axis"]][3]
    versions = [v for v in (d.get("versions") or "").split(";") if v]
    versioned = any(ms[k]["version_column"] for k in keys if k in ms)
    filters = [(a, d.get(f"filter_{a}")) for a in ("material", "customer") if d.get(f"filter_{a}")]
    f_ok = all(all(a in ms[k]["axes_list"] for k in keys if k in ms) and q(f"select 1 from {AXES[a][1]} where ancestor_code = ? limit 1", n) for a, n in filters)
    return [
        {"check": "who may", "ok": roles.may(who, READ), "says": f"{who} holds {said(READ)}" if roles.may(who, READ) else f"{who} does not hold {said(READ)}"},
        {"check": "a name", "ok": bool(d["report_name"]), "says": d["report_name"] or "a report is named"},
        {"check": "measures the plan defines", "ok": bool(keys) and not unknown, "says": f"{len(keys)} measure{'s' if len(keys) != 1 else ''}" if keys and not unknown else (f"{', '.join(unknown)} — not in the register" if unknown else "a report asks for one measure or more")},
        {"check": "rows every measure can be read by", "ok": rows_ok and level_ok, "says": f"{AXIS_SAID.get(d['rows_axis'], d['rows_axis'])}" + (f" by {d.get('rows_level')}" if d.get("rows_level") else "") if rows_ok and level_ok else f"not every measure can be read by {AXIS_SAID.get(d['rows_axis'], d['rows_axis'])}" + ("" if level_ok else " at that level")},
        {"check": "across, the same", "ok": cols_ok, "says": AXIS_SAID.get(d["columns_axis"], d["columns_axis"]) if cols_ok else f"not every measure has {AXIS_SAID.get(d['columns_axis'], d['columns_axis'])}"},
        {"check": "versions", "ok": (not versioned or bool(versions)) and set(versions) <= known_versions and (not d.get("compare") or len(versions) == 2),
         "says": ", ".join(versions) + (" — the first less the second" if d.get("compare") else "") if versions else ("none needed" if not versioned else "a measure with versions needs one")},
        {"check": "filters", "ok": f_ok, "says": ", ".join(f"{a} {n}" for a, n in filters) or "none"},
    ]


def _cell(x, shown_as: str) -> str:
    if x is None:
        return ""
    return f"{x:,.0f}" if shown_as in ("count", "money") else f"{x:,.2f}"


def draw(d: dict, ms: dict, who: str, roles, node_label=None) -> list[dict]:
    """The report's figures, drawn now: per measure and version, rows by the declared axis and level, across by the
    declared axis; each value rolled up by the measure's registered rule; a cell a withheld line reaches shown withheld."""
    tables = []
    keys = [k for k in d["measures"].split(";") if k in ms]
    versions = [v for v in (d.get("versions") or "").split(";") if v]
    for k in keys:
        m = ms[k]
        num, den = (m["num"], m["den"]) if m["rollup"] == "ratio" else (m, None)
        rel, rows_axis, cols_axis = m["relation"], d["rows_axis"], d["columns_axis"]
        rcol, hier, leaf, _ = AXES[rows_axis]
        ccol = AXES[cols_axis][0]
        join, node = "", f"x.{rcol}"
        if hier:
            join = f" join {hier} h on h.descendant_code = x.{rcol} and h.descendant_level = '{leaf}' and h.ancestor_level = ?"
            node = "h.ancestor_code"
        hidden = m["withheld_when"] if m["withheld_verb"] and not roles.may(who, m["withheld_verb"]) else None
        value = f"sum({num['value_column']})" if not den else f"sum({num['value_column']}) / nullif(sum({den['value_column']}), 0)"
        held = f"bool_or({hidden})" if hidden else "false"
        where, params = [], ([d["rows_level"]] if hier else [])
        for a in ("material", "customer"):
            if d.get(f"filter_{a}"):
                where.append(f"x.{AXES[a][0]} in (select descendant_code from {AXES[a][1]} where ancestor_code = ?)"); params.append(d[f"filter_{a}"])
        runs = versions if m["version_column"] else [None]
        grid: dict = {}
        for v in runs:
            w = where + ([f"x.{m['version_column']} = ?"] if v else [])
            pv = params + ([v] if v else [])
            sql_w = (" where " + " and ".join(w)) if w else ""
            body = q(f"select {node} r, x.{ccol}::text c, {value} val, {held} held from {rel} x{join}{sql_w} group by all", *pv)
            tot = q(f"select x.{ccol}::text c, {value} val, {held} held from {rel} x{sql_w} group by all", *(pv[1:] if hier else pv))
            grid[v] = (body, tot)
        cols = sorted({b["c"] for body, tot in grid.values() for b in body if b["c"] is not None})
        label = {b["r"]: (node_label(rows_axis, b["r"]) if hier and node_label else b["r"]) for body, _ in grid.values() for b in body}
        def table(v, body, tot, title):
            rows = defaultdict(dict)
            for b in body:
                rows[b["r"]][b["c"]] = "withheld" if b["held"] else _cell(b["val"], m["shown_as"])
            out = [{"label": label.get(r, r), "cells": [rows[r].get(c, "") for c in cols]} for r in sorted(rows, key=lambda x: str(x))]
            t = {b["c"]: ("withheld" if b["held"] else _cell(b["val"], m["shown_as"])) for b in tot}
            out.append({"label": "Total", "total": True, "cells": [t.get(c, "") for c in cols]})
            return {"title": title, "cols": cols, "rows": out, "says": m["rollup_says"],
                    "note": ("Withheld: lines of individual pay reach these cells, read only by the holders of " + said(m["withheld_verb"]) + "." if hidden and any(b["held"] for b in body) else "")
                            + ("" if m["version_column"] else " The strategic plan has no version: versions do not apply to it.")}
        for v in runs:
            tables.append(table(v, *grid[v], f"{m['grid_label']} · {m['label']}" + (f" · {v}" if v else "")))
        if d.get("compare") and len(runs) == 2 and runs[0]:
            a, b = ({(x["r"], x["c"]): x for x in grid[v][0]} for v in runs)
            ta, tb = ({x["c"]: x for x in grid[v][1]} for v in runs)
            # read against each other only where both versions have the figure — never a figure less nothing
            def less(x, y):
                return x["val"] - y["val"] if x and y and x["val"] is not None and y["val"] is not None else None
            diff = [{"r": r, "c": c, "val": less(a.get((r, c)), b.get((r, c))), "held": bool((a.get((r, c)) or {}).get("held") or (b.get((r, c)) or {}).get("held"))}
                    for r, c in set(a) | set(b)]
            dt_ = [{"c": c, "val": less(ta.get(c), tb.get(c)), "held": bool((ta.get(c) or {}).get("held") or (tb.get(c) or {}).get("held"))} for c in set(ta) | set(tb)]
            tables.append(table(None, diff, dt_, f"{m['grid_label']} · {m['label']} · {runs[0]} less {runs[1]}"))
    return tables


def register(bp, page, who_fn, busy, session, roles) -> None:
    from . import reads

    @bp.get("/reports")
    def reports():
        try:
            who = who_fn(); ms = measures()
            mine = [_said(r, ms) for r in declarations() if r["owner"] == who]
            grids: dict[str, dict] = {}
            for m in ms.values():
                grids.setdefault(m["grid"], {"label": m["grid_label"], "measures": []})["measures"].append(
                    {**m, "axes_said": ", ".join(AXIS_SAID[a] for a in m["axes_list"] if a in AXIS_SAID)})
            row_options = [{"value": f"{a}:{lv}", "label": f"{AXIS_SAID[a]} by {lv.replace('_', ' ')}"} for a in ("material", "customer") for lv in AXES[a][3][1:]] + \
                          [{"value": a, "label": AXIS_SAID[a]} for a in AXES if not AXES[a][1]]
            return page(PICK, title="Reports", active="reports", mine=mine, grids=list(grids.values()), row_options=row_options,
                        versions=[v for v in reads.versions() if v.get("version_kind") != "actual"], may=roles.may(who, READ), last=session.last)
        except Busy as e:
            return busy("Reports", e)

    @bp.post("/reports")
    def report_save():
        f = request.form; who = who_fn(); ms = measures()
        axis, _, level = (f.get("rows") or "").partition(":")
        d = {"report_id": f"RP-{dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')}", "owner": who, "report_name": (f.get("report_name") or "").strip(),
             "measures": ";".join(f.getlist("measure")), "rows_axis": axis if axis in AXES else "", "rows_level": level, "columns_axis": f.get("columns_axis") or "",
             "versions": ";".join(f.getlist("versions")), "compare": "Y" if f.get("compare") == "Y" else "",
             "filter_material": (f.get("filter_material") or "").strip(), "filter_customer": (f.get("filter_customer") or "").strip(),
             "saved_on": dt.datetime.now().isoformat(timespec="seconds")}
        checks = checks_for({**d, "compare": d["compare"] == "Y"}, ms, who, roles, {v["version_id"] for v in reads.versions()})
        placed = receipts.judge(checks)
        if placed:
            LANDING.place([d], who)
        session.last = receipts.write("report.save", who, d["report_id"], checks, placed)
        session.say(f"{d['report_name']} saved" if placed else "report not saved: " + "; ".join(c["says"] for c in checks if not c["ok"]), placed)
        return redirect(url_for("plan.report", report_id=d["report_id"]) if placed else url_for("plan.reports"))

    @bp.get("/reports/<report_id>")
    def report(report_id: str):
        try:
            who = who_fn(); ms = measures()
            d = next((r for r in declarations() if r["report_id"] == report_id), None)
            if d is None:
                return page("<h1>Reports</h1><p class='lede'>No report {{ rid }}.</p>", title="Reports", active="reports", rid=report_id)
            r = _said(d, ms)
            refused = None if roles.may(who, READ) else f"{who} does not hold {said(READ)} — a report reads the plan, so it is drawn for nobody without it."
            filters = ", ".join(f"{a} {d[f'filter_{a}']}" for a in ("material", "customer") if d.get(f"filter_{a}"))
            held_from = []
            for vid in [v for v in (d.get("versions") or "").split(";") if v]:
                vp = reads.version_periods(vid)
                if vp["plan"]:
                    held_from.append({"version_id": vid, "after": vp["plan"][0], "actual": bool(vp["actual"])})
            return page(DRAW, title=d["report_name"], active="reports", r=r, reader=who, refused=refused, filters=filters, held_from=held_from,
                        tables=[] if refused else draw(d, ms, who, roles, reads.node_label))
        except Busy as e:
            return busy("Reports", e)
