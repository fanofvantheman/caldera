"""Ingestion: every file in the landing, loaded by dlt into the `bronze` dataset of the local
DuckDB warehouse.

One resource per file. Every resource is `write_disposition="replace"`: bronze is the ephemeral
landing, truncated whole on every load and holding only what is on file, stamped with where it
came from (source file, file row). History is owned downstream by the models.

Two sources feed a plan table: the generated file (what was loaded from the client's systems) and
every file the face has since placed under data/landing/<sub>/<table>/ — appended in file order,
which is time order. The face is the landing's only writer.

Run:  uv run python -m ingest.pipeline [--root data/generated] [--db data/caldera.duckdb]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import dlt
from chassis.ingest import log_resource

# file stem → numeric columns (the file is text; the door casts)
REFERENCE = {
    "dim_week": ("fiscal_year", "fiscal_week", "fiscal_period", "quarter", "calendar_year", "calendar_month"),
    "ctl_period": ("fiscal_year", "fiscal_period", "quarter", "weeks"),
    "ctl_version": (),
    "dim_category": (),
    "dim_product": (),
    "dim_format": ("size_g", "units_per_case", "case_net_kg"),
    "dim_material": ("units_per_case", "case_net_kg", "base_cases_per_week"),
    "dim_input_material": (),
    "ref_promo_group": (),
    "ref_bom": ("quantity_per_case",),
    "dim_account": ("payment_terms_days", "settlement_discount_pct"),
    "dim_ship_to": ("stores_served",),
    "dim_node": (),
    "dim_plant_area": (),
    "dim_line": (),
    "ref_lane": ("transit_days", "cost_per_pallet"),
    "ref_route": ("rate_cases_per_hour", "changeover_hours"),
    "dim_cost_centre": (),
    "reg_capacity_machine": ("shifts", "working_days", "available_hours", "planned_downtime_hours", "efficiency_assumption"),
    "reg_assumption": ("value",),
    "ref_reason_code": (),
    "ctl_role_definition": (),
    "ctl_role_action": (),
    "ctl_role_assignment": (),
}
HISTORY = {
    "shipments": ("cases", "tonnes"),
    "price_list": ("price_per_case",),
    "forecast_snapshot": ("lag", "cases"),
}
PLAN = {
    "layer_entry": ("layer_no", "value"),
    "reg_promo_event": ("uplift_pct", "dip_pct", "tpr_per_case", "scan_funding_per_case", "fixed_fee"),
    "reg_terms": ("rate",),
    "reg_submission": (),
}
INTEGER = frozenset({"layer_no", "lag", "fiscal_year", "fiscal_week", "fiscal_period", "quarter", "calendar_year", "calendar_month", "weeks",
           "size_g", "units_per_case", "stores_served", "transit_days", "shifts", "working_days", "payment_terms_days"})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data/generated")
    ap.add_argument("--db", default="data/caldera.duckdb")
    ap.add_argument("--landing", default="data/landing", help="what the face has written since the load: appended to the same tables")
    args = ap.parse_args()
    root = Path(args.root)
    landing = Path(args.landing)
    pipeline = dlt.pipeline(pipeline_name="caldera_bronze", destination=dlt.destinations.duckdb(args.db),
                            dataset_name="bronze", pipelines_dir="data/.dlt")
    resources = []
    for name, numeric in REFERENCE.items():
        p = root / "reference" / f"{name}.csv"
        if p.exists() and p.stat().st_size > 0:
            resources.append(log_resource(p, [], name, numeric, INTEGER))
    for sub, group in (("history", HISTORY), ("plan", PLAN)):
        for name, numeric in group.items():
            p = root / sub / f"{name}.csv"
            placed = sorted((landing / sub / name).glob("*.csv")) if (landing / sub / name).is_dir() else []   # file order is time order
            if p.exists() and p.stat().st_size > 0:
                resources.append(log_resource(p, placed, name, numeric, INTEGER))
    info = pipeline.run(resources)
    print(info)


if __name__ == "__main__":
    main()
