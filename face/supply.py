"""The supply plan's first two pages (DEC-20261117-02 point 7), under Integrated business planning → Supply:

- **Inventory** — one table, a material at the stocking point chosen a row (DEC-20261119-05): projected stock at period
  end leading, a row opening to its demand, receipts, target, the period's peak and its safety stock.
- **Supply plan** — one table, a material at its plant a row: cases to make leading, a row opening to the proposal, what
  it ships to each DC and its finished stock; the supply plan's owner types a quantity in its cell over the proposal
  with a reason, the proposal kept beside it (DEC-20261118-04 point 3).

Both read plan.inventory_flow, made by calc.inventory. Registered on the plan's blueprint by `register(...)`."""
from __future__ import annotations

import datetime as dt

from chassis import receipts
from chassis.landing import LogLanding
from chassis.warehouse import Busy, q
from flask import redirect, request, url_for

from . import figures, overrides
from .figures import Filter, Measure
from .words import said

VERB = "delta.supply.enter"
ACT_COLUMNS = ["act_id", "action", "withdraws", "version_id", "material_code", "plant_code", "period", "quantity", "reason", "entered_by", "entered_at"]
ACTS = LogLanding("plan", "reg_production_act", ACT_COLUMNS)

MACRO = """{% macro n0(x) %}{{ '' if x is none else '{:,.0f}'.format(x) }}{% endmacro %}"""

INVENTORY = """<h1>Inventory<small>{{ version|plan }} · {{ node_name }} · replenished to an order-up-to target from the plant that supplies it</small></h1>
<p class="hint">Each stocking point holds the demand over the next review period and lead time, plus a safety stock solved for the fill rate of the material's class ({% for s in levels %}{{ s.service_class }} {{ '{:.0%}'.format(s.fill_rate) }}{{ ', ' if not loop.last }}{% endfor %}); each week it receives what restores the target and ships its demand. A DC's demand is the plan's cases at the ship-tos it serves; a plant's is the DCs' receipts, by the share each takes from it. The variability is what the node shipped a week over the last 52 closed weeks — <b>demand variability, an upper bound</b>: no weekly record of the plan against what shipped is kept yet, so the buffer is larger than a residual would make it. Opening stock is each point's target at the plan's first week — no stock position is loaded. Stock at period end; the week-grain peak is one of a row's figures.</p>
<div class="seg toolbar"><span class="small muted">node</span>{% for n in nodes %}{% if n.code == node %}<b>{{ n.name }}</b>{% else %}<a href="{{ url_for('plan.inventory', location=n.code, material=material) }}">{{ n.name }}</a>{% endif %}{% endfor %}</div>
{{ grid_choice(g) }}
{{ grid_table(g) }}
<p class="hint">A row is a material at {{ node_name }}; its name's line says its class and fill rate and what it shipped a week (σ). Cases of different materials add, so the first row totals the cases. The year is its plan periods: demand and {{ 'production' if is_plant else 'receipts' }} summed, the stock, target and safety stock its last period's; a peak is not added. A typed production quantity is boxed.</p>
{{ grid_style() }}<style>.seg{display:flex;gap:.6rem;flex-wrap:wrap;margin:.4rem 0}</style>"""

SUPPLY = """<h1>Supply plan<small>{{ version|plan }} · the production requirement by plant — what the inventory plan asks each plant to make, not sequenced against the lines</small></h1>
<p class="hint">Each plant's requirement is its replenishment of the DCs it supplies, less its own finished stock, on its own order-up-to target. Whether the lines can make it is the capacity reading's question, not this page's. {% if may and is_open %}You plan supply: type a quantity in a period's cell over the proposal and save it with a reason — the proposal stays beside it, and materials read what stands after the next run.{% else %}Typed over by {{ holders|join(', ') or 'nobody yet' }}.{% endif %}</p>
{{ grid_choice(g) }}
{% if g.editable %}<form method="post" action="{{ url_for('plan.production_type') }}" id="type">{% for k in ('version', 'location', 'material') %}{% if request.args.get(k) %}<input type="hidden" name="{{ k }}" value="{{ request.args.get(k) }}">{% endif %}{% endfor %}{% endif %}
{{ grid_table(g) }}
{% if g.editable %}{% call save_bar(discard='reset', note='each figure changed is one act, by ' ~ who_ ~ ' — in the plan after the next run') %}<label class="small grow">why <input name="reason" placeholder="a campaign run, a line down, a build ahead"></label>{% endcall %}</form>{% endif %}
<p class="hint">A row is a material at the plant that makes it, in cases: the first row totals them. A row opens to the proposal, what it ships to each DC and its finished stock at period end. The year is its plan periods; the stock its last period's. A typed quantity is boxed with the proposal beneath it.</p>
{% if typed %}<h2>Typed<span class="count">{{ typed|length }} standing on {{ version|plan }}</span></h2><table><thead><tr><th>Material</th><th>Plant</th><th>Period</th><th class="n">Typed</th><th class="n">Proposed</th><th>Why</th><th>By</th><th></th></tr></thead><tbody>
{% for t in typed %}<tr><td>{{ t.material_code }}</td><td>{{ t.plant_code }}</td><td>{{ t.period }}</td><td class="n">{{ n0(t.quantity) }}</td><td class="n">{{ n0(t.proposed) }}</td><td class="small">{{ t.reason }}</td><td class="small">{{ t.entered_by }}</td>
<td>{% if may and is_open %}<form class="inline" method="post" action="{{ url_for('plan.production_withdraw') }}"><input type="hidden" name="act_id" value="{{ t.act_id }}"><input name="reason" required placeholder="why" size="10"> <button class="act">Withdraw</button></form>{% endif %}</td></tr>{% endfor %}</tbody></table>{% endif %}
{% if last %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>
{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else ('!' if c.flag else '✕') }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}
{{ grid_style() }}<style>.form-row{display:flex;flex-wrap:wrap;gap:.8rem;align-items:end;margin:.6rem 0}.form-row .grow{flex:1;display:flex;flex-direction:column}</style>"""

INV_MEASURES = [Measure("closing", "projected stock", year="last"), Measure("demand", "demand"),
                Measure("receipt", "receipts", typed="typed"), Measure("target", "target at period end", year="last"),
                Measure("peak", "peak in the period", year=None, total=False), Measure("safety_stock", "safety stock", year="last")]


def _categories(q) -> dict:
    """Each finished material's category — what the category filter reads."""
    return {r["descendant_code"]: r["ancestor_code"] for r in q("select descendant_code, ancestor_code from dims.dim_material_hierarchy where ancestor_level = 'category'")}


def register(bp, page, who_fn, ctx_fn, busy, session, roles) -> None:
    from . import reads

    def version_of() -> str:
        return ctx_fn().get("version") or reads.default_version()

    def leaf(code: str | None) -> str | None:
        return code if code and q("select 1 ok from dims.dim_material where material_code = ?", code) else None

    @bp.get("/supply/inventory")
    def inventory():
        try:
            c = ctx_fn(); version = version_of()
            nodes = [{"code": r["node_code"], "name": r["node_name"], "kind": r["node_kind"]} for r in q("select node_code, node_name, node_kind from dims.dim_node order by node_kind desc, node_code")]
            node = c.get("location") if c.get("location") in {n["code"] for n in nodes} else next((n["code"] for n in nodes if n["kind"] != "plant"), nodes[0]["code"])
            mat = leaf(c.get("material"))
            names = {r["material_code"]: r["material_name"] for r in q("select material_code, material_name from dims.dim_material")}
            cls = {r["material_code"]: r for r in q("select c.material_code, c.service_class, l.fill_rate from plan.service_class c left join dims.ref_service_level l using (service_class) where c.version_id = ?", version)}
            var = {r["material_code"]: r for r in q("select * from plan.demand_variability where node_code = ?", node)}
            cat_of = _categories(q)
            is_plant = next(n["kind"] for n in nodes if n["code"] == node) == "plant"
            rows: dict = {}
            for r in q("select * from plan.inventory_flow where version_id = ? and node_code = ? order by material_code, period", version, node):
                if mat and r["material_code"] != mat:
                    continue
                m = r["material_code"]; k = cls.get(m) or {}; v = var.get(m) or {}
                row = rows.setdefault(m, {"code": m, "label": names.get(m, m),
                                          "level": " · ".join(x for x in [f"class {k['service_class']}" if k.get("service_class") else "no class",
                                                                          f"{k['fill_rate']:.0%}" if k.get("fill_rate") else "",
                                                                          f"σ {v['sigma']:,.0f} a week" if v.get("sigma") is not None else "under 13 weeks shipped, no safety stock"] if x),
                                          "attrs": {"class": k.get("service_class") or "", "category": cat_of.get(m, "")}, "by": {}})
                row["by"][r["period"]] = {**r, "typed_title": "a production quantity typed over the proposal"}
            cats = sorted({r["attrs"]["category"] for r in rows.values() if r["attrs"]["category"]})
            filters = [Filter("class", "class", tuple((x, x) for x in sorted({r["attrs"]["class"] for r in rows.values() if r["attrs"]["class"]}))),
                       Filter("category", "category", tuple((x, reads.node_label("material", x) or x) for x in cats))]
            measures = [m if m.key != "receipt" else Measure("receipt", "production" if is_plant else "receipts", typed="typed") for m in INV_MEASURES]
            vp = reads.version_periods(version)
            node_name = next(n["name"] for n in nodes if n["code"] == node)
            g = figures.table("inv", list(rows.values()), measures, "closing", figures.columns(vp, actuals=False, quarters=False), row_head=f"Materials at {node_name}",
                              filters=filters, total=f"Every material at {node_name}", year_says="plan periods", empty=f"Nothing stocked at {node_name} on {version}.")
            return page(figures.MACROS + INVENTORY, title="Inventory", active="inventory", width="none", version=version, nodes=nodes, node=node,
                        node_name=node_name, is_plant=is_plant, material=mat or "ALL", g=g, levels=q("select * from dims.ref_service_level order by service_class"))
        except Busy as e:
            return busy("Inventory", e)

    @bp.get("/supply/plan")
    def supply_plan():
        try:
            c = ctx_fn(); who = who_fn(); version = version_of(); v = reads.version(version) or {}
            loc = c.get("location") or "ALL"
            mat = leaf(c.get("material"))
            names = {r["node_code"]: r["node_name"] for r in q("select node_code, node_name from dims.dim_node")}
            plant_codes = {r["node_code"] for r in q("select node_code from dims.dim_node where node_kind = 'plant'")}
            mats = {r["material_code"]: r["material_name"] for r in q("select material_code, material_name from dims.dim_material")}
            cat_of = _categories(q)
            src: dict = {}
            for s_ in q("select material_code, plant_code, node_code, period, sum(cases) cases from plan.production_source where version_id = ? group by all", version):
                src.setdefault((s_["material_code"], s_["plant_code"], s_["period"]), {})[f"src_{s_['node_code']}"] = s_["cases"]
            dcs = sorted({k[4:] for d in src.values() for k in d})
            rows: dict = {}
            for r in q("select * from plan.production_requirement where version_id = ? order by material_code, plant_code, period", version):
                if (loc in plant_codes and r["plant_code"] != loc) or (mat and r["material_code"] != mat):
                    continue
                row = rows.setdefault((r["material_code"], r["plant_code"]), {
                    "code": f"{r['material_code']}~{r['plant_code']}", "label": mats.get(r["material_code"], r["material_code"]),
                    "level": names.get(r["plant_code"], r["plant_code"]), "attrs": {"plant": r["plant_code"], "category": cat_of.get(r["material_code"], "")}, "by": {}})
                row["by"][r["period"]] = {**r, **src.get((r["material_code"], r["plant_code"], r["period"]), {}),
                                          "proposed_note": f"proposed {r['proposed']:,.0f}" if r["typed"] and r["proposed"] is not None else None,
                                          "typed_title": "typed over the proposal — listed under Typed"}
            measures = [Measure("quantity", "to make", typed="typed", note="proposed_note", input=True), Measure("proposed", "proposed"),
                        Measure("shipped_to_dcs", "to the DCs")] + [Measure(f"src_{n}", f"for {names.get(n, n)}") for n in dcs] + \
                       [Measure("finished_stock", "finished stock at period end", year="last")]
            cats = sorted({r["attrs"]["category"] for r in rows.values() if r["attrs"]["category"]})
            filters = [Filter("plant", "plant", tuple((p, names.get(p, p)) for p in sorted({r["attrs"]["plant"] for r in rows.values()}))),
                       Filter("category", "category", tuple((x, reads.node_label("material", x) or x) for x in cats))]
            vp = reads.version_periods(version)
            may, is_open = roles.may(who, VERB), v.get("status") == "open"
            g = figures.table("sup", list(rows.values()), measures, "quantity", figures.columns(vp, actuals=False, quarters=False), row_head="Materials at their plant",
                              filters=filters, total="Cases to make", editable=may and is_open, plan_periods=set(vp["plan"]), year_says="plan periods",
                              empty="No production requirement on this plan.")
            typed = q("""select a.*, r.proposed from plan.production_act a left join plan.production_requirement r using (version_id, material_code, plant_code, period)
                         where a.version_id = ? order by a.material_code, a.period""", version)
            return page(figures.MACROS + MACRO + SUPPLY, title="Supply plan", active="supply", width="none", version=version, g=g, typed=typed,
                        may=may, holders=reads.holders(VERB), is_open=is_open, who_=who, last=session.last, receipt_acts=("production",))
        except Busy as e:
            return busy("Supply plan", e)

    @bp.post("/supply/plan/type")
    def production_type():
        f = request.form
        if not f.get("key"):
            return production_cells()
        who = who_fn(); version = version_of(); v = reads.version(version) or {}
        mat, _, plant = (f.get("key") or "").partition("|")
        period, reason = f.get("period") or "", (f.get("reason") or "").strip()
        try:
            qty = float(f.get("quantity") or "")
        except ValueError:
            qty = None
        cell = q("select proposed from plan.production_requirement where version_id = ? and material_code = ? and plant_code = ? and period = ?", version, mat, plant, period)
        stage = reads.stage_open(version, "production") if hasattr(reads, "stage_open") else (True, "")
        checks = [
            {"check": "who may plan supply", "ok": roles.may(who, VERB), "says": f"{who} holds {said(VERB)}" if roles.may(who, VERB) else f"{who} does not hold {said(VERB)} — supply is planned by {', '.join(reads.holders(VERB))}"},
            {"check": "the plan is open", "ok": v.get("status") == "open", "says": f"{version} is {v.get('status', 'unknown')}"},
            {"check": "the stage is open", "ok": stage[0], "says": stage[1] or "production is open on this plan"},
            {"check": "a proposal to type over", "ok": bool(cell), "says": f"{mat} at {plant} in {period}: {cell[0]['proposed']:,.0f} proposed" if cell else f"{mat or 'nothing'} at {plant or '—'} has no requirement in {period or 'no period'}"},
            {"check": "a quantity", "ok": qty is not None and qty >= 0, "says": f"{qty:,.0f} cases" if qty is not None and qty >= 0 else "a number of cases, not below zero"},
            {"check": "a reason", "ok": bool(reason), "says": reason or "a typed quantity says why"},
        ]
        placed = receipts.judge(checks)
        if placed:
            now = dt.datetime.now()
            ACTS.place([{"act_id": f"PRD-{now:%Y%m%d%H%M%S%f}", "action": "set", "withdraws": "", "version_id": version, "material_code": mat, "plant_code": plant,
                         "period": period, "quantity": qty, "reason": reason, "entered_by": who, "entered_at": now.isoformat(timespec="seconds")}], who)
        session.last = receipts.write("production.type", who, f"{mat}:{plant}:{period}", checks, placed)
        if overrides.released(who, "production", session, f"{mat} at {plant} in {period} placed", placed):
            return redirect(url_for("plan.run"))
        if not placed:
            session.say("refused: " + "; ".join(x["says"] for x in checks if not x["ok"]), False)
        return redirect(url_for("plan.supply_plan") + "#type")

    def production_cells():
        """The table posted back: every quantity whose cell differs from the figure it was drawn with is placed — one act a
        material at a plant in a period, all with the one reason, or none."""
        f = request.form; who = who_fn(); version = f.get("version") or version_of(); v = reads.version(version) or {}
        reason = (f.get("reason") or "").strip()
        now = {(r["material_code"], r["plant_code"], r["period"]): r for r in q("select * from plan.production_requirement where version_id = ?", version)}
        plan_periods = set(reads.version_periods(version)["plan"])
        qm = Measure("quantity", "to make", input=True)
        changed, bad = {}, []
        for _, code, period, raw in figures.posted(f, [qm]):
            m, _, plant = code.partition("~")
            r = now.get((m, plant, period))
            if raw == "" or (r is not None and raw == figures.input_value(qm, r["quantity"])):
                continue
            try:
                x = float(raw)
            except ValueError:
                x = None
            if x is None or x < 0 or r is None or period not in plan_periods:
                bad.append(f"{raw!r} for {m} at {plant} in {period}"); continue
            changed[(m, plant, period)] = x
        stage = reads.stage_open(version, "production") if hasattr(reads, "stage_open") else (True, "")
        checks = [
            {"check": "who may plan supply", "ok": roles.may(who, VERB), "says": f"{who} holds {said(VERB)}" if roles.may(who, VERB) else f"{who} does not hold {said(VERB)} — supply is planned by {', '.join(reads.holders(VERB))}"},
            {"check": "the plan is open", "ok": v.get("status") == "open", "says": f"{version} is {v.get('status', 'unknown')}"},
            {"check": "the stage is open", "ok": stage[0], "says": stage[1] or "production is open on this plan"},
            {"check": "quantities typed", "ok": bool(changed) and not bad, "says": ("refused: " + "; ".join(bad)) if bad else ("; ".join(f"{m} at {pl} in {per}: {x:,.0f}" for (m, pl, per), x in sorted(changed.items())) or "no cell differs from the figure it was drawn with")},
            {"check": "a reason", "ok": bool(reason), "says": reason or "a typed quantity says why"},
        ]
        placed = receipts.judge(checks)
        if placed:
            now_ = dt.datetime.now()
            ACTS.place([{"act_id": f"PRD-{now_:%Y%m%d%H%M%S%f}-{i:03d}", "action": "set", "withdraws": "", "version_id": version, "material_code": m, "plant_code": pl,
                         "period": per, "quantity": x, "reason": reason, "entered_by": who, "entered_at": now_.isoformat(timespec="seconds")}
                        for i, ((m, pl, per), x) in enumerate(sorted(changed.items()), start=1)], who)
        session.last = receipts.write("production.type", who, f"{len(changed)} cells", checks, placed)
        if overrides.released(who, "production", session, f"{len(changed)} production quantit{'ies' if len(changed) != 1 else 'y'} placed", placed):
            return redirect(url_for("plan.run"))
        if not placed:
            session.say("refused: " + "; ".join(x["says"] for x in checks if not x["ok"]), False)
        return redirect(figures.back(url_for("plan.supply_plan", version=version, location=f.get("location") or None, material=f.get("material") or None) + "#type"))

    @bp.post("/supply/plan/withdraw")
    def production_withdraw():
        f = request.form; who = who_fn()
        act = q("select * from plan.production_act where act_id = ?", f.get("act_id") or "")
        reason = (f.get("reason") or "").strip()
        v = (reads.version(act[0]["version_id"]) or {}) if act else {}
        checks = [
            {"check": "who may plan supply", "ok": roles.may(who, VERB), "says": f"{who} holds {said(VERB)}" if roles.may(who, VERB) else f"{who} does not hold {said(VERB)}"},
            {"check": "a typed quantity standing", "ok": bool(act), "says": f"{act[0]['act_id']}: {act[0]['material_code']} at {act[0]['plant_code']} in {act[0]['period']}" if act else "no such typed quantity in force"},
            {"check": "the plan is open", "ok": v.get("status") == "open", "says": f"{v.get('version_id', '—')} is {v.get('status', 'unknown')}"},
            {"check": "a reason", "ok": bool(reason), "says": reason or "a withdrawal says why"},
        ]
        placed = receipts.judge(checks)
        if placed:
            now = dt.datetime.now(); a = act[0]
            ACTS.place([{"act_id": f"PRD-{now:%Y%m%d%H%M%S%f}", "action": "withdraw", "withdraws": a["act_id"], "version_id": a["version_id"], "material_code": a["material_code"],
                         "plant_code": a["plant_code"], "period": a["period"], "quantity": "", "reason": reason, "entered_by": who, "entered_at": now.isoformat(timespec="seconds")}], who)
        session.last = receipts.write("production.withdraw", who, f.get("act_id") or "", checks, placed)
        if overrides.released(who, "production", session, "withdrawn — the proposal stands again", placed):
            return redirect(url_for("plan.run"))
        if not placed:
            session.say("refused: " + "; ".join(x["says"] for x in checks if not x["ok"]), False)
        return redirect(url_for("plan.supply_plan"))
