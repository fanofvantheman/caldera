"""Entitlements under Labour (DEC-20261114-03): the closed list of kinds the labour model can price, and the
entitlements beneath them — each a row under a kind with the clause it came from, quoted — by layer: the statutory floor
for the jurisdiction, then the entity's agreement; the one in force for a classification is the upper layer where it
speaks and the floor where it does not, and the page says which.

What it is for: pricing a roster for a plan. It is not an interpretation of an agreement for payroll, and the page says
so. The register is kept by the holder of `register.agreement.maintain`. Registered on the plan's blueprint by
`register(...)`, called from `face/__main__.py`."""
from __future__ import annotations

from collections import defaultdict

from chassis.warehouse import Busy, q

PAGE = """<h1>Entitlements<small>what the labour model prices: a closed list of kinds, and each agreement's entitlements beneath them, every one with the clause it came from</small></h1>
<p class="hint">For pricing a roster for a plan — not an interpretation of any agreement for payroll. The plan reads the rows below, never the document; a clause that fits none of the kinds is an item to resolve, not forced into one.</p>
<h2>Kinds<span class="count">what the labour model has a calculation for</span></h2>
<table><thead><tr><th>Kind</th><th>What it is</th><th>How the labour model prices it</th><th>Today</th><th class="n">Rows</th></tr></thead><tbody>
{% for k in kinds %}<tr class="{{ '' if k.priced else 'off' }}"><td><b>{{ k.kind_label }}</b></td><td class="small">{{ k.what }}</td><td class="small">{{ k.calculates }}</td>
<td class="small">{% if k.priced %}priced{% else %}<span class="state">not yet priced</span>{% endif %}</td><td class="n">{{ k.n or '' }}</td></tr>{% endfor %}</tbody></table>
{% for inst in instruments %}<h2>{{ inst.instrument_name }}<span class="count">{{ inst.layer_said }} · {{ inst.where }}{% if inst.specimen %} · <b>specimen — awaiting sources</b>{% endif %}</span></h2>
{% if inst.specimen %}<p class="flash no">{{ inst.specimen_says }}</p>{% endif %}
<table><thead><tr><th>Kind</th><th>Classification</th><th>Applies to</th><th class="n">Value</th><th>From</th><th>Clause</th></tr></thead><tbody>
{% for e in inst.rows %}<tr class="{{ 'off' if not e.priced }}"><td class="small">{{ e.kind_label }}</td><td class="small">{{ e.classification_name or 'every classification' }}</td><td class="small">{{ e.applies_to or '' }}</td>
<td class="n">{{ e.shown }}</td><td class="small">{{ e.valid_from_period }}</td><td class="small"><b>{{ e.clause_ref }}</b> “{{ e.clause }}”</td></tr>{% endfor %}</tbody></table>{% endfor %}
{% if layers %}<h2>In force, by layer<span class="count">the upper layer where it speaks, the floor where it does not</span></h2>
<table><thead><tr><th>Entity</th><th>Kind</th><th>Classification</th><th>Applies to</th><th class="n">In force</th><th>From</th><th class="n">The floor</th></tr></thead><tbody>
{% for r in layers %}<tr><td class="small">{{ r.entity_code }}</td><td class="small">{{ r.kind_label }}</td><td class="small">{{ r.classification_name or 'every classification' }}</td><td class="small">{{ r.applies_to or '' }}</td>
<td class="n">{{ r.shown }}</td><td class="small">{{ r.layer_said }}{% if r.specimen %} <span class="state">specimen</span>{% endif %}</td><td class="n small muted">{{ r.floor_shown }}</td></tr>{% endfor %}</tbody></table>{% endif %}
<p class="hint">Entitlements are kept by {{ holders|join(', ') or 'nobody yet' }}.</p>"""

LAYER_SAID = {"statute": "the statutory floor", "award": "the award", "agreement": "the entity's agreement"}


def shown(e: dict) -> str:
    v = e.get("value")
    if v is None:
        return ""
    if e["kind"] in ("base_rate", "allowance", "one_off"):
        return f"${v:,.2f}" + (" an hour" if e["kind"] == "base_rate" else "")
    return f"{v:.2%}".replace(".00%", "%")


def view(layers: list[dict] | None = None) -> dict:
    kinds = q("""select k.*, count(e.entitlement_id) n from dims.ref_entitlement_kind k left join dims.reg_entitlement e using (kind)
                 group by all order by k.ord""")
    label = {k["kind"]: k["kind_label"] for k in kinds}
    order = {k["kind"]: k["ord"] for k in kinds}
    by = defaultdict(list)
    for e in q("select * from dims.reg_entitlement order by instrument, valid_from_period, classification"):
        by[(e["layer"], e["instrument"])].append({**e, "kind_label": label.get(e["kind"], e["kind"]), "shown": shown(e)})
    inst = []
    for (layer, code), rows in sorted(by.items(), key=lambda x: (["statute", "award", "agreement"].index(x[0][0]) if x[0][0] in LAYER_SAID else 9, x[0][1])):
        rows.sort(key=lambda e: (order.get(e["kind"], 99), e["classification"] or "", e["valid_from_period"]))
        sp = any(e["specimen"] for e in rows)
        inst.append({"instrument": code, "instrument_name": rows[0]["instrument_name"], "layer_said": LAYER_SAID.get(layer, layer), "rows": rows,
                     "where": rows[0]["entity_code"] or rows[0]["jurisdiction"] or "", "specimen": sp,
                     "specimen_says": "These rows are a specimen: no source document for this jurisdiction's statute has been given, so nothing here is "
                                      "drafted from one. They show the shape a maintained set takes; each is replaced when the set is drafted from its "
                                      "sources, dated and accepted." if sp else ""})
    return {"kinds": kinds, "instruments": inst, "layers": layers or []}


def register(bp, page, who_fn, busy, roles) -> None:
    from . import reads

    @bp.get("/labour/entitlements")
    def entitlements():
        try:
            return page(PAGE, title="Entitlements", active="hc_entitlements", **view(), holders=reads.holders("register.agreement.maintain"))
        except Busy as e:
            return busy("Entitlements", e)
