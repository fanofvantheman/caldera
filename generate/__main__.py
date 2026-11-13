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
                         PROMO_GROUPS, ACCOUNTS, PROMOTIONS_MASTER, BASELINE_SOURCE, PROMO_WEEK_START, SHIP_TOS, UNIT_OF, NODES, PLANT_AREAS, LINES, LANES, COST_CENTRES)
from .history import forecast_snapshots, generate_demand, generate_prices, value_shipments
from .registers import versions, period_control, roles, capacity_register, assumptions, assumption_amendments, version_acts, strategic_plan, strategic_growth
from .plan import business_plan_entries, latest_view_entries, promo_events, promo_neighbours, terms_register, reason_codes, submissions, finance_edits, finance_sources
from .emit import emit_all, dataclass_rows
from . import sender
from . import forecaster
from . import loads
from . import costs

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
                         "promotions_master": PROMOTIONS_MASTER.get(a[0], "PLAN"), "baseline_source": BASELINE_SOURCE.get(a[0], "PLAN"), "promo_week_start": PROMO_WEEK_START.get(a[0], ""),
                         "planning_unit": UNIT_OF[a[0]][0], "planning_unit_name": UNIT_OF[a[0]][1]} for a in ACCOUNTS],
        "dim_ship_to": [{"ship_to_code": s[0], "account_code": s[1], "ship_to_name": s[2], "state": s[3], "serving_node": s[4], "stores_served": s[5]} for s in SHIP_TOS],
        "dim_node": [{"node_code": n[0], "node_name": n[1], "node_kind": n[2], "roles": n[3], "ownership": n[4], "state": n[5], "status": n[6]} for n in NODES],
        "dim_plant_area": [{"plant_code": a[0], "area_code": a[1], "area_name": a[2]} for a in PLANT_AREAS],
        "dim_line": [{"line_code": l[0], "plant_code": l[1], "area_code": l[2], "line_name": l[3], "rate_uom": l[4]} for l in LINES],
        "ref_lane": [{"from_node": l[0], "to_code": l[1], "to_kind": l[2], "mode": l[3], "transit_days": l[4], "cost_per_pallet": l[5]} for l in LANES],
        "ref_route": build_routes(materials),
        # the labour model is declared per cost centre: by role where the entitlement accrues to the role, by name where not
        "dim_cost_centre": [{"cost_centre_code": c[0], "cost_centre_name": c[1], "parent_code": c[2], "kind": c[3],
                             "labour_model": {"factory": "role", "overhead": "name"}.get(c[3], "")} for c in COST_CENTRES],
        "reg_capacity_machine": capacity_register(weeks),
        "reg_assumption": assumptions(),
        "ref_reason_code": reason_codes(),
        **sender.reference(),
    }
    defs, acts, asg = roles()
    tables["ctl_role_definition"], tables["ctl_role_action"], tables["ctl_role_assignment"] = defs, acts, asg

    shipments = generate_demand(materials, history_weeks, rng, FIRST_FY)
    period_order = [p["period"] for p in cal.periods(weeks)]
    prices, terms = generate_prices(materials, rng), terms_register()
    history = {"shipments": shipments, "price_list": prices,
               "forecast_snapshot": forecast_snapshots(shipments, materials, period_order, LATEST_CLOSED, rng)}
    value_shipments(shipments, prices, terms, weeks, rng)         # history is revenue and units; price is the derived figure
    entries = business_plan_entries(materials, shipments, PLAN_FY) + latest_view_entries(PLAN_FY, LATEST_CLOSED)
    events = promo_events(weeks, PLAN_FY, LATEST_CLOSED, materials)       # one calendar, re-issued through its two doors
    doors = sender.through_the_doors(events, {a[0]: PROMOTIONS_MASTER.get(a[0], "PLAN") for a in ACCOUNTS})
    plan = {
        "layer_entry": [{"entry_id": f"LE-{i:05d}", **e} for i, e in enumerate(entries, start=1)],
        **doors,
        "reg_promo_neighbour": promo_neighbours(events),
        "reg_terms": terms,
        "reg_submission": submissions(LATEST_CLOSED),
        "reg_finance_overlay": finance_edits(shipments, materials, PLAN_FY, LATEST_CLOSED),     # Finance's figures; draws nothing
        "reg_finance_source": finance_sources(),
        "reg_assumption_amend": assumption_amendments(LATEST_CLOSED),       # Finance's acts on the assumptions; draws nothing
        "reg_version_act": version_acts(PLAN_FY),                            # closing and reopening versions; draws nothing
        "reg_strategic_plan": strategic_plan(PLAN_FY, LATEST_CLOSED),         # the five-year plan and the growth beyond the latest view; draw nothing
        "reg_strategic_growth": strategic_growth(PLAN_FY),
    }
    fcst, fcst_waiting = forecaster.run(shipments, materials, weeks, LATEST_CLOSED, {a[0]: BASELINE_SOURCE.get(a[0], "PLAN") for a in ACCOUNTS},
                                        f"LV-{LATEST_CLOSED}")       # after the last draw on rng above: it draws nothing
    plan.update({**fcst, "reg_door_act": plan["reg_door_act"] + fcst["reg_door_act"]})     # one act register for every door
    waiting = sender.next_export(events, {p["period"]: p["period_start"] for p in cal.periods(weeks)}, PLAN_FY)
    periods = cal.periods(weeks)
    tables.update(costs.reference(periods))           # the entities, their ledgers' cost centres, the mapping, the chart
    tables.update(costs.labour_registers(periods))    # the agreements, positions by role, people by name, on-costs
    history["cost_actual"] = costs.cost_actuals(shipments, tables["ref_route"], periods, LATEST_CLOSED, args.seed)   # a stream of its own
    plan["reg_schedule_edit"] = costs.schedule_edits(f"LV-{LATEST_CLOSED}", history["cost_actual"],
                                                     [p["period"] for p in periods if p["period"] <= LATEST_CLOSED][-12:])   # the opex schedule's acts; draws nothing
    tables.update(loads.structure_loads(tables))        # the load before, and one member the client has not finished; draws nothing
    manifest = emit_all(Path(args.out), tables, history, plan, args.seed, outbox={**waiting, **fcst_waiting})
    c = manifest["counts"]
    print(f"generated: {c['dim_material']} materials, {c['dim_ship_to']} ship-tos, {c['dim_week']} weeks, "
          f"{c['shipments']} shipment rows, {c['forecast_snapshot']} forecast snapshot rows, {c['price_list']} price rows, {c['ref_bom']} bom lines, {c['reg_capacity_machine']} capacity rows, "
          f"{c['layer_entry']} layer entries, {c['tpm_event']} promo events from the sender and {c['reg_promo_event']} typed, "
          f"{c['reg_door_act']} door acts, {c['reg_terms']} terms; waiting from the sender: {sender.NEXT_FILE}; "
          f"{c['fcst_series']} forecast rows in run {forecaster.FIRST_RUN}, waiting from the forecasting system: {forecaster.NEXT_RUN}")


if __name__ == "__main__":
    main()
