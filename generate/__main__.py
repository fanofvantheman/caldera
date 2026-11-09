"""Generate the synthetic client.  python -m generate [--seed N] [--out DIR]

Deterministic: the same seed produces byte-identical files, so every runner regenerates the same
input and the repository carries the recipe, never the data.
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

from . import calendar as cal
from .structures import (build_materials, build_bom, build_routes, INPUT_MATERIALS, CATEGORIES, PRODUCTS, FORMATS,
                         PROMO_GROUPS, ACCOUNTS, SHIP_TOS, UNIT_OF, NODES, PLANT_AREAS, LINES, LANES, COST_CENTRES)
from .history import generate_demand, generate_prices
from .registers import versions, period_control, roles, capacity_register, assumptions
from .plan import business_plan_entries, latest_view_entries, promo_events, terms_register, reason_codes, submissions
from .emit import emit_all, dataclass_rows

FIRST_FY, LAST_FY, PLAN_FY = 2024, 2030, 2027   # the latest view rolls 36 periods from the cycle
LATEST_CLOSED = "2027P04"          # the last closed period: October 2026


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261107)
    ap.add_argument("--out", default="data/generated")
    args = ap.parse_args()
    rng = random.Random(args.seed)

    weeks = cal.build(FIRST_FY, LAST_FY)
    history_weeks = [w for w in weeks if w.period <= LATEST_CLOSED]
    materials = build_materials()

    tables = {
        "dim_week": [{**{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in w.__dict__.items()}} for w in weeks],
        "ctl_period": period_control(weeks, LATEST_CLOSED),
        "ctl_version": versions(weeks, PLAN_FY, LATEST_CLOSED),
        "dim_category": [{"category_code": c, "category_name": n, "trend": t} for c, (n, t) in CATEGORIES.items()],
        "dim_product": [{"product_code": p[0], "product_name": p[1], "category_code": p[2], "segment": p[3], "brand": p[4],
                         "sub_brand": p[5], "price_tier": p[6], "branded": p[7], "seasonal_flag": p[8], "campaign_input": p[9]} for p in PRODUCTS],
        "dim_format": [{"format_code": k, "format_name": v[0], "container": v[1], "size_g": v[2], "units_per_case": v[3], "case_net_kg": v[4]} for k, v in FORMATS.items()],
        "dim_material": dataclass_rows(materials),
        "dim_input_material": [{"material_code": r[0], "material_name": r[1], "material_type": r[2], "base_uom": r[3],
                                "campaign_window": r[4], "commodity_link": r[5], "origin": r[6]} for r in INPUT_MATERIALS],
        "ref_promo_group": [{"promo_group_code": k, "promo_group_name": v[0], "material_code": m} for k, v in PROMO_GROUPS.items() for m in v[1]],
        "ref_bom": build_bom(materials),
        "dim_account": [{"account_code": a[0], "account_name": a[1], "channel": a[2], "sub_channel": a[3], "account_tier": a[4],
                         "route_to_market": a[5], "state": a[6], "price_list": a[7], "payment_terms_days": a[8],
                         "settlement_discount_pct": a[9], "collaborative_flag": a[10], "scan_flag": a[11], "status": "active",
                         "planning_unit": UNIT_OF[a[0]][0], "planning_unit_name": UNIT_OF[a[0]][1]} for a in ACCOUNTS],
        "dim_ship_to": [{"ship_to_code": s[0], "account_code": s[1], "ship_to_name": s[2], "state": s[3], "serving_node": s[4], "stores_served": s[5]} for s in SHIP_TOS],
        "dim_node": [{"node_code": n[0], "node_name": n[1], "node_kind": n[2], "roles": n[3], "ownership": n[4], "state": n[5], "status": n[6]} for n in NODES],
        "dim_plant_area": [{"plant_code": a[0], "area_code": a[1], "area_name": a[2]} for a in PLANT_AREAS],
        "dim_line": [{"line_code": l[0], "plant_code": "SHP", "area_code": l[1], "line_name": l[2], "rate_uom": l[3]} for l in LINES],
        "ref_lane": [{"from_node": l[0], "to_code": l[1], "to_kind": l[2], "mode": l[3], "transit_days": l[4], "cost_per_pallet": l[5]} for l in LANES],
        "ref_route": build_routes(materials),
        "dim_cost_centre": [{"cost_centre_code": c[0], "cost_centre_name": c[1], "parent_code": c[2], "kind": c[3]} for c in COST_CENTRES],
        "reg_capacity_machine": capacity_register(weeks),
        "reg_assumption": assumptions(),
        "ref_reason_code": reason_codes(),
    }
    defs, acts, asg = roles()
    tables["ctl_role_definition"], tables["ctl_role_action"], tables["ctl_role_assignment"] = defs, acts, asg

    shipments = generate_demand(materials, history_weeks, rng, FIRST_FY)
    history = {"shipments": shipments, "price_list": generate_prices(materials, rng)}
    entries = business_plan_entries(materials, shipments, PLAN_FY) + latest_view_entries(PLAN_FY, LATEST_CLOSED)
    plan = {
        "layer_entry": [{"entry_id": f"LE-{i:05d}", **e} for i, e in enumerate(entries, start=1)],
        "reg_promo_event": promo_events(weeks, PLAN_FY, LATEST_CLOSED, materials),
        "reg_terms": terms_register(),
        "reg_submission": submissions(LATEST_CLOSED),
    }
    manifest = emit_all(Path(args.out), tables, history, plan, args.seed)
    c = manifest["counts"]
    print(f"generated: {c['dim_material']} materials, {c['dim_ship_to']} ship-tos, {c['dim_week']} weeks, "
          f"{c['shipments']} shipment rows, {c['price_list']} price rows, {c['ref_bom']} bom lines, {c['reg_capacity_machine']} capacity rows, "
          f"{c['layer_entry']} layer entries, {c['reg_promo_event']} promo events, {c['reg_terms']} terms")


if __name__ == "__main__":
    main()
