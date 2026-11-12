"""The plan's doors on the chassis's one resolution model: the promotions system (TPM) and the forecasting system (FCS).

Every decision at either door is one row in one act register (`plan/reg_door_act`); what a person may decide about each
kind of disagreement is reference data (`plan.ref_door_resolution`); each door's queue is a worklist in the chassis's
queue contract. What stays per door is the comparison — which codes, series or members disagree and what each would
bring — in the door's own worklist query."""
from __future__ import annotations

import csv

from chassis import door
from chassis.landing import LogLanding
from chassis.warehouse import q

from . import ROOT, roles
from . import reads

ACTS = LogLanding("plan", "reg_door_act", door.ACT_COLUMNS)
GENERATED = ROOT / "data" / "generated" / "plan" / "reg_door_act.csv"


def _master() -> list[dict]:
    """The acts loaded with the build — the onboarding mappings and resolutions."""
    if not GENERATED.exists() or GENERATED.stat().st_size == 0:
        return []
    with GENERATED.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _kinds() -> dict[str, dict[str, door.Kind]]:
    return door.kinds_from(q("select * from plan.ref_door_resolution"))


TPM = door.Door("TPM", "the promotions system", ACTS, lambda: _kinds().get("TPM", {}), _master)
FCS = door.Door("FCS", "the forecasting system", ACTS, lambda: _kinds().get("FCS", {}), _master)
DOORS = {"TPM": TPM, "FCS": FCS}
QUEUES = {"TPM": "plan.worklist_promo_mapping_review", "FCS": "plan.worklist_forecast_queue"}
PAGES = {"TPM": "plan.mapping", "FCS": "plan.forecast"}
# what of ours a resolution names → the list it must be one of
TPM_SUBJECT = {"account": "customer", "promo group": "material", "mechanic": "mechanic", "funding type": "funding_type", "status": "status"}


def may(who: str, verb: str, reaches: list[str]) -> bool:
    """Whether this person may decide: the verb anywhere when the item reaches no particular node; otherwise the verb at
    one of the nodes it reaches, in the customer structure (the root reaches every node)."""
    if not reaches:
        return roles.may(who, verb)
    return any(roles.may(who, verb, n, dimension="customer") for n in reaches)


def ours_list(names: str) -> list[dict]:
    """Our members a resolution may name, as {code, label}."""
    if names in TPM_SUBJECT:
        return [{"code": t["code"], "label": t["description"]} for t in reads.mapping_targets(TPM_SUBJECT[names])]
    if names == "material":
        return [{"code": m["material_code"], "label": m["material_name"]} for m in reads.materials()]
    if names == "product":
        return [{"code": p["product_code"], "label": f"{p['category_name']} › {p['product_name']}"} for p in reads.products()]
    return []


def ours(names: str) -> set[str]:
    return {o["code"] for o in ours_list(names)}


def ours_lists(kinds: dict[str, door.Kind]) -> dict[str, list[dict]]:
    return {n: ours_list(n) for k in kinds.values() for n in k.names}


def queue(key: str) -> list[dict]:
    return q(f"select * from {QUEUES[key]}")


def waiting(key: str, kind: str, item: str, scope: str) -> dict | None:
    return next((i for i in queue(key) if i["kind"] == kind and i["item_code"] == item and str(i["scope_code"]) == scope), None)


def decided(key: str) -> list[dict]:
    """The latest decision per item at a door, newest first, with the name of what it names where it names one of ours."""
    return q("""select a.*, coalesce(m.material_name, p.product_name, pm.target_name) as target_name
                from plan.door_act a
                left join dims.dim_material m on a.door = 'FCS' and a.resolution = 'same_as' and m.material_code = a.target_code
                left join (select distinct product_code, product_name from dims.dim_material) p on a.door = 'FCS' and a.resolution = 'place_under' and p.product_code = a.target_code
                left join plan.promo_mapping pm on a.door = 'TPM' and pm.subject = a.kind and pm.local_code = a.item_code
                where a.door = ? and a.in_force order by a.acted_at desc, a.kind, a.item_code""", key)


def page_context(key: str, who: str, items: list[dict] | None = None, next_url: str = "") -> dict:
    """What `door.QUEUE` and `door.DECIDED` read: the door's items with what this person may decide, its kinds, the lists
    of ours its resolutions name, where the decision posts and where it returns."""
    from flask import url_for
    d = DOORS[key]
    kinds = d.kinds
    return {"door_items": d.offer(queue(key) if items is None else items, who, may), "door_kinds": kinds, "door_ours": ours_lists(kinds),
            "door_action": url_for("plan.door_decide", key=key), "door_next": next_url or url_for(PAGES[key])}
