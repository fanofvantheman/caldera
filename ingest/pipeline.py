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
    "ctl_version": ("horizon_periods", "horizon_quarters"),
    "ref_version_kind": ("horizon_periods", "horizon_quarters", "ord"),
    "ref_verb": ("ord",),
    "ref_step_horizon": ("horizon_periods", "ord"),
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
    # the cost side: the legal entities, each one's ledger cost centres, the mapping to the plan's, the chart, the drivers
    "dim_entity": (),
    "dim_ledger_cost_centre": (),
    "reg_cost_centre_map": (),
    "dim_gl_account": (),
    "ref_cost_driver": ("ord",),
    # labour: each entity's agreement, the on-costs, the positions (by role) and the people (by name)
    "ref_entitlement_kind": ("ord",),
    "ref_on_cost": ("rate",),
    "reg_position": ("fte", "hours_per_week"),
    "reg_person": ("annual_salary", "incentive_pct"),
    "reg_capacity_machine": ("shifts", "working_days", "available_hours", "planned_downtime_hours", "efficiency_assumption"),
    "reg_assumption": ("value",),
    "ref_reason_code": (),
    "ref_mechanic": ("default_uplift_pct", "default_dip_pct"),
    "ref_funding_type": (),
    "ref_promo_status": (),
    "ctl_role_definition": (),
    "ctl_role_action": (),
    "ctl_role_assignment": (),
    # the structures' loads, and each structure as at the load before — what changed is read against them
    "ctl_structure_load": (),
    "prior_dim_material": ("units_per_case", "case_net_kg", "base_cases_per_week"),
    "prior_dim_ship_to": ("stores_served",),
    "prior_dim_node": (),
    "prior_ref_lane": ("transit_days", "cost_per_pallet"),
}
HISTORY = {
    "shipments": ("cases", "tonnes", "gross_sales", "net_sales"),
    "price_list": ("price_per_case",),
    "forecast_snapshot": ("lag", "cases"),
    "cost_actual": ("amount",),
}
PLAN = {
    "layer_entry": ("layer_no", "value"),
    "reg_promo_event": ("uplift_pct", "dip_pct", "tpr_per_case", "scan_funding_per_case", "fixed_fee", "media_fee", "envelope_drawdown"),
    "reg_promo_neighbour": ("rate",),
    "tpm_event": ("uplift_pct", "dip_pct"),
    "tpm_funding": ("line_no", "rate"),
    "reg_terms": ("rate",),
    "reg_submission": (),
    "fcst_run": ("horizon_weeks",),
    "fcst_series": ("cases",),
    "reg_door_act": (),
    "reg_finance_overlay": ("value", "source_at_entry"),
    "reg_finance_source": (),
    "reg_schedule_edit": ("value", "calc_at_entry"),
    "reg_assumption_amend": ("value",),
    "reg_version_act": (),
    "reg_strategic_plan": ("first_year", "last_year"),
    "reg_strategic_growth": ("fiscal_year", "growth_pct"),
    "reg_role": (),
    "reg_entitlement": ("value",),
}
INTEGER = frozenset({"layer_no", "line_no", "lag", "fiscal_year", "fiscal_week", "fiscal_period", "quarter", "calendar_year", "calendar_month", "weeks",
           "size_g", "units_per_case", "stores_served", "transit_days", "shifts", "working_days", "payment_terms_days", "horizon_weeks", "horizon_periods", "horizon_quarters", "ord"})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data/generated")
    ap.add_argument("--db", default="data/caldera.duckdb")
    ap.add_argument("--landing", default="data/landing", help="what the face has written since the load: appended to the same tables")
    ap.add_argument("--only", nargs="+", default=None, help="load just these tables — a run scoped to what one act can reach")
    args = ap.parse_args()
    root = Path(args.root)
    landing = Path(args.landing)
    pipeline = dlt.pipeline(pipeline_name="caldera_bronze", destination=dlt.destinations.duckdb(args.db),
                            dataset_name="bronze", pipelines_dir="data/.dlt")
    resources = []
    only = set(args.only) if args.only else None
    for name, numeric in ({} if only else REFERENCE).items():
        p = root / "reference" / f"{name}.csv"
        if p.exists() and p.stat().st_size > 0:
            resources.append(log_resource(p, [], name, numeric, INTEGER))
    for sub, group in (("history", HISTORY), ("plan", PLAN)):
        for name, numeric in group.items():
            if only and name not in only:
                continue
            p = root / sub / f"{name}.csv"
            placed = sorted((landing / sub / name).glob("*.csv")) if (landing / sub / name).is_dir() else []   # file order is time order
            if p.exists() and p.stat().st_size > 0:
                resources.append(log_resource(p, placed, name, numeric, INTEGER))
    info = pipeline.run(resources)
    print(info)


if __name__ == "__main__":
    main()
