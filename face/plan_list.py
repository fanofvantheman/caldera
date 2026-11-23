"""The list of plans (DEC-20261124-05 point 7), under plan administration: each kind of plan that feeds the IBP plan, who
owns it, what it owns and what it reads and from whom — read from the declared list (dims.ref_plan_kind,
dims.ref_plan_figure), never from code. A key figure has one owning plan; the run refuses a list where it has two.

Registered on the plan's blueprint by `register(...)`, called once from `face/__main__.py`."""
from __future__ import annotations

from chassis.warehouse import Busy, q

from . import reads
from .words import said

PAGE = """<h1>Plans and their figures<small>each plan that feeds the IBP plan · who owns it · what it owns and what it reads</small></h1>
<p class="hint">Every key figure has one plan that owns it — it is typed there and sent from there; every other plan reads it, as a copy taken in. The IBP plan owns none: it holds what was sent to it and published in it. A plan is listed once it is built.</p>
{% for k in kinds %}<div class="card"><h3>{{ k.plan_kind_name }} <span class="small muted" style="font-weight:400">— feeds {{ k.stage_name }} · owned by {{ k.owners|join(', ') or 'nobody yet' }} ({{ k.right }}) · {{ 'taken by copy, unasked' if k.taken_by == 'copy' else 'taken by request' }}</span></h3>
<table><thead><tr><th>Key figure</th><th>Grain</th><th></th><th>From</th><th>Carries</th></tr></thead><tbody>
{% for f in k.figures %}<tr><td><b>{{ f.figure_name }}</b></td><td class="small">{{ f.grain }}</td><td>{{ 'owns' if f.relation == 'owns' else 'reads' }}</td><td class="small">{{ f.from_says }}</td><td class="small">{{ f.fields or '' }}</td></tr>{% endfor %}
</tbody></table></div>{% else %}<p class="lede">No plan is listed yet.</p>{% endfor %}"""


def register(bp, page, who_fn, ctx_fn, busy, session, roles) -> None:
    @bp.get("/versions/plan_list")
    def plan_list():
        try:
            stages = {r["stage"]: r["stage_name"] for r in q("select stage, stage_name from dims.ref_stage")}
            kinds = q("select * from dims.ref_plan_kind order by plan_kind")
            names = {k["plan_kind"]: k["plan_kind_name"] for k in kinds}
            out = []
            for k in kinds:
                figs = q("select * from dims.ref_plan_figure where plan_kind = ? order by ord", k["plan_kind"])
                for f in figs:
                    rf = f.get("read_from")
                    f["from_says"] = ("" if f["relation"] == "owns" else
                                      names.get(rf) or {"record": "the record — the actuals at the plan's close",
                                                        "assumption": "the IBP plan's assumption"}.get(rf)
                                      or f"the IBP plan — {stages.get(rf, rf)}, a stage with no plan of its own listed yet")
                out.append({**k, "stage_name": stages.get(k["stage"], k["stage"]), "owners": reads.holders(k["owner_verb"]),
                            "right": said(k["owner_verb"]), "figures": figs})
            return page(PAGE, title="Plans and their figures", active="plan_list", kinds=out)
        except Busy as e:
            return busy("Plans and their figures", e)
