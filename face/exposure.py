"""The exposure matrix (DEC-20261120-05), beside Material purchases under Supply: a row a key raw material in a SKU at
the plant that makes it, the Plan's periods across, one measure at a time — the material's dollars in one case at
standard, revised on the Plan, and the difference, each per case or as a share of the whole cost of the case in the
period. Money only; read only: nothing here moves a quantity, the bill or the amount consumed.

Nothing is calculated here: the costing already holds each input of a case (plan.planned_material_input — the bill ×
usage at the key material's consumption cost) and the standard holds the year's (plan.standard_input, over
plan.standard_cost). Registered on the plan's blueprint by `register(...)`."""
from __future__ import annotations

from chassis.warehouse import Busy, q

from . import figures
from .figures import Filter, Measure

# per case: never added across SKUs (total=False) nor over periods (year=None) — a share as a percentage, two places
MEASURES = [Measure("std", "at standard, $ a case", shown="price", year=None, total=False),
            Measure("rev", "revised, $ a case", shown="price", year=None, total=False),
            Measure("diff", "difference, $ a case", shown="price", year=None, total=False),
            Measure("std_pct", "at standard, % of the case", shown="price", year=None, total=False),
            Measure("rev_pct", "revised, % of the case", shown="price", year=None, total=False),
            Measure("diff_pct", "difference, % of the case", shown="price", year=None, total=False)]

PAGE = """<h1>Exposure<small>{{ version|plan }} · what each key raw material is worth in a case, period by period — at standard, revised on the Plan, and the difference</small></h1>
<p class="hint">A row is a key raw material in a product at the plant that makes it: the bill's quantity in one case × the material's cost. <b>At standard</b> is the year's bill at the standard price, set on the year's business plan and held through the year; <b>revised</b> is the same quantity at what the material's consumption is valued at on {{ version|plan }} in the period, from the <a href="{{ url_for('plan.material_purchases') }}">material balance</a>; the <b>difference</b> is what the balance has moved in the cost of that case. Each is read per case or as a percentage of the whole cost of the case in the period — material, labour and overhead: at standard over the standard cost, revised and the difference over the planned cost. Filter to a product for its key materials through the year, or to a material for every case that carries it. Only money is shown: what a case consumes is the bill's and the production plan's, and nothing here changes it.</p>
{{ grid_choice(g) }}
{{ grid_table(g) }}
<p class="hint">Figures per case are not added across products or over periods, so there is no total row and no year. A period of a year with no business plan has no standard.</p>
{{ grid_style() }}"""


def register(bp, page, who_fn, ctx_fn, busy, session, roles) -> None:
    from . import reads

    @bp.get("/supply/purchases/exposure")
    def material_exposure():
        try:
            c = ctx_fn()
            version = c.get("version") or reads.default_version()
            loc = c.get("location") or "ALL"
            rows = q("""select i.material_code, i.plant_code, i.input_code, i.period, p.fiscal_year, i.per_case rev, u.unit_cost,
                               s.std_quantity * s.std_price std, sc.std_cost
                        from plan.planned_material_input i
                        join dims.ref_key_material k on k.input_code = i.input_code and k.plant_code = i.plant_code
                        join dims.dim_period p on p.period = i.period
                        left join plan.planned_unit_cost u on u.version_id = i.version_id and u.material_code = i.material_code and u.period = i.period
                        left join plan.standard_input s on s.material_code = i.material_code and s.plant_code = i.plant_code and s.input_code = i.input_code and s.fiscal_year = p.fiscal_year
                        left join plan.standard_cost sc on sc.material_code = i.material_code and sc.plant_code = i.plant_code and sc.fiscal_year = p.fiscal_year
                        where i.version_id = ? order by i.material_code, i.input_code, i.period""", version)
            skus = {r["material_code"]: r["material_name"] for r in q("select material_code, material_name from dims.dim_material")}
            inputs = {r["material_code"]: r["material_name"] for r in q("select material_code, material_name from dims.dim_input_material")}
            plants = {r["node_code"]: r["node_name"] for r in q("select node_code, node_name from dims.dim_node")}
            out: dict = {}
            for r in rows:
                if loc != "ALL" and r["plant_code"] != loc:
                    continue
                row = out.setdefault((r["material_code"], r["input_code"]), {
                    "code": f"{r['material_code']}~{r['input_code']}", "label": skus.get(r["material_code"], r["material_code"]),
                    "level": f"{inputs.get(r['input_code'], r['input_code'])} · {plants.get(r['plant_code'], r['plant_code'])}",
                    "attrs": {"input": r["input_code"], "sku": r["material_code"], "plant": r["plant_code"]}, "by": {}})
                std, rev = r["std"], r["rev"]
                pct = lambda x, d: None if x is None or not d else 100.0 * x / d
                row["by"][r["period"]] = {"std": std, "rev": rev, "diff": None if std is None or rev is None else rev - std,
                                          "std_pct": pct(std, r["std_cost"]), "rev_pct": pct(rev, r["unit_cost"]),
                                          "diff_pct": None if std is None or rev is None else pct(rev - std, r["unit_cost"])}
            rs = list(out.values())
            filters = [Filter("input", "material", tuple(sorted({(x["attrs"]["input"], inputs.get(x["attrs"]["input"], x["attrs"]["input"])) for x in rs}, key=lambda t: t[1]))),
                       Filter("sku", "product", tuple(sorted({(x["attrs"]["sku"], x["label"]) for x in rs}, key=lambda t: t[1]))),
                       Filter("plant", "plant", tuple((p, plants.get(p, p)) for p in sorted({x["attrs"]["plant"] for x in rs})))]
            vp = reads.version_periods(version)
            g = figures.table("exp", rs, MEASURES, "rev", figures.columns(vp, actuals=False, quarters=False), row_head="Key raw material in a case",
                              filters=filters, empty="No key raw material in a case on this plan.")
            return page(figures.MACROS + PAGE, title="Exposure", active="exposure", width="none", version=version, g=g)
        except Busy as e:
            return busy("Exposure", e)
