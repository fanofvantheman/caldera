"""Ingestion: every file in the landing, loaded by dlt into the `bronze` dataset of the local
DuckDB warehouse.

One resource per file. Every resource is `write_disposition="replace"`: bronze is the ephemeral
landing, truncated whole on every load and holding only what is on file, stamped with where it
came from (source file, file row). History is owned downstream by the models.

Run:  uv run python -m ingest.pipeline [--root data/generated] [--db data/caldera.duckdb]
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Iterator

import dlt

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
    "ctl_role_definition": (),
    "ctl_role_action": (),
    "ctl_role_assignment": (),
}
HISTORY = {
    "shipments": ("cases", "tonnes"),
    "price_list": ("price_per_case",),
}
INTEGER = {"fiscal_year", "fiscal_week", "fiscal_period", "quarter", "calendar_year", "calendar_month", "weeks",
           "size_g", "units_per_case", "stores_served", "transit_days", "shifts", "working_days", "payment_terms_days"}


def _rows(path: Path, numeric: tuple[str, ...]) -> Iterator[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            out = {k: (v if v != "" else None) for k, v in row.items()}
            for col in numeric:
                if out.get(col) is not None:
                    out[col] = int(float(out[col])) if col in INTEGER else float(out[col])
            out["source_file"] = path.name
            out["file_row_number"] = i
            yield out


def _columns(path: Path, numeric: tuple[str, ...]) -> dict:
    """Declare every header column: the contract is the header, not whichever columns happened to carry data."""
    with path.open(newline="", encoding="utf-8") as f:
        header = next(csv.reader(f))
    cols = {h: {"data_type": ("bigint" if h in INTEGER else "double") if h in numeric else "text", "nullable": True} for h in header}
    cols["source_file"] = {"data_type": "text"}
    cols["file_row_number"] = {"data_type": "bigint"}
    return cols


def _resource(path: Path, name: str, numeric: tuple[str, ...]):
    return dlt.resource(_rows(path, numeric), name=name, write_disposition="replace", columns=_columns(path, numeric))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data/generated")
    ap.add_argument("--db", default="data/caldera.duckdb")
    args = ap.parse_args()
    root = Path(args.root)
    pipeline = dlt.pipeline(pipeline_name="caldera_bronze", destination=dlt.destinations.duckdb(args.db),
                            dataset_name="bronze", pipelines_dir="data/.dlt")
    resources = []
    for name, numeric in REFERENCE.items():
        p = root / "reference" / f"{name}.csv"
        if p.exists() and p.stat().st_size > 0:
            resources.append(_resource(p, name, numeric))
    for name, numeric in HISTORY.items():
        p = root / "history" / f"{name}.csv"
        if p.exists() and p.stat().st_size > 0:
            resources.append(_resource(p, name, numeric))
    info = pipeline.run(resources)
    print(info)


if __name__ == "__main__":
    main()
