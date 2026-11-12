"""The structures as loaded from the client's systems, and the load before: what the plan was given and what changed.

The plan does not manage master data; it reads the structures it is given and says what state they are in. So that the
structures page has something true to show, this writes the load before the latest — the same structures with a
handful of differences a real master shows between two loads — and adds to the latest load one material the client has
created and not yet finished (no price, no route, no bill of materials), so the page can show a member not yet fit to
plan. Nothing here draws on the generator's random stream; history is untouched.

  reference/ctl_structure_load.csv     each structure's two loads: the system, the load and when
  reference/prior_dim_material.csv     the materials as at the load before
  reference/prior_dim_ship_to.csv      the ship-tos as at the load before
  reference/prior_dim_node.csv         the locations as at the load before
  reference/prior_ref_lane.csv         the lanes as at the load before
"""

from __future__ import annotations

import copy

LOADS = [
    # structure, what it is, the system, the load before, the latest
    ("materials", "Materials", "ERP material master", "2026-10-26T02:00:00", "2026-11-02T02:00:00"),
    ("customers", "Customers and ship-tos", "ERP customer master", "2026-10-26T02:10:00", "2026-11-02T02:10:00"),
    ("locations", "Locations", "ERP plant and warehouse register", "2026-10-26T02:20:00", "2026-11-02T02:20:00"),
    ("lanes", "Lanes and routes", "ERP transport and routing", "2026-10-26T02:30:00", "2026-11-02T02:30:00"),
]


def structure_loads(tables: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Adds the unfinished material to the latest load (in place) and returns the load register and the prior snapshots."""
    mats = tables["dim_material"]
    # the client has created a four-pack of the first snack cup and not finished it: no price, no route, no bill of materials
    tpl = next(m for m in mats if m["category_code"] == "SNACK_CUPS")
    new = {**tpl, "material_code": f"{tpl['material_code']}-4PK6", "material_name": f"{tpl['material_name']}, six four-packs",
           "lifecycle_status": "launching", "parent_material": "", "base_cases_per_week": 0.0}
    mats.append(new)

    prior_mats = [copy.copy(m) for m in mats if m["material_code"] != new["material_code"]]
    # two materials renamed or re-cased since the load before, and one the client has since removed
    canned = [m for m in prior_mats if m["category_code"] == "CANNED_FRUIT"]
    canned[2]["material_name"] = canned[2]["material_name"].replace(" in juice", " in natural juice")
    canned[5]["units_per_case"] = int(canned[5]["units_per_case"]) * 2
    gone = {**canned[0], "material_code": f"{canned[0]['product_code']}-CAN_3000", "material_name": canned[0]["material_name"].split(",")[0] + ", 3 kg catering can",
            "lifecycle_status": "delisting", "parent_material": ""}
    prior_mats.append(gone)

    ship_tos = tables["dim_ship_to"]
    prior_ship = [copy.copy(s) for s in ship_tos[:-1]]                        # the last ship-to is new in the latest load
    moved = next(s for s in prior_ship if s["account_code"] == "CAR")
    moved["serving_node"] = "SYD" if moved["serving_node"] != "SYD" else "MEL"  # since re-served from another warehouse

    prior_nodes = [copy.copy(n) for n in tables["dim_node"]]

    lanes = tables["ref_lane"]
    prior_lanes = [copy.copy(l) for l in lanes[:-1]]                          # the last lane is new in the latest load
    prior_lanes[1]["transit_days"] = int(prior_lanes[1]["transit_days"]) + 1

    register = []
    for key, name, system, before, latest in LOADS:
        register.append({"structure": key, "structure_name": name, "source_system": system, "load_id": f"{key.upper()}-{before[:10]}", "loaded_at": before, "is_latest": "N"})
        register.append({"structure": key, "structure_name": name, "source_system": system, "load_id": f"{key.upper()}-{latest[:10]}", "loaded_at": latest, "is_latest": "Y"})
    return {"ctl_structure_load": register, "prior_dim_material": prior_mats, "prior_dim_ship_to": prior_ship,
            "prior_dim_node": prior_nodes, "prior_ref_lane": prior_lanes}
