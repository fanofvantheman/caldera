"""The capital plan walked: every item of every plan version — the assets as loaded, the projects, the sustaining rates,
the leases — × the version's plan periods: cash out, additions, depreciation, the lease charge and the net book value.

The walk is `calc.capex.compute`, the same function the generator used to make the ledgers' depreciation actuals, so the
first plan period carries on from the last closed one. Python because an asset's book value is carried period to period.
"""
from __future__ import annotations

import typing as t
from datetime import datetime

import pandas as pd
from sqlmesh import ExecutionContext, model

from calc.capex import COLUMNS, compute, in_force, read_inputs

TYPES = {"version_id": "TEXT", "item_id": "TEXT", "kind": "TEXT", "item_name": "TEXT", "asset_class": "TEXT", "entity_code": "TEXT",
         "cost_centre_code": "TEXT", "plant_code": "TEXT", "period": "TEXT", "fiscal_year": "INT", "spend": "DOUBLE", "additions": "DOUBLE",
         "depreciation": "DOUBLE", "lease_charge": "DOUBLE", "opening_nbv": "DOUBLE", "closing_nbv": "DOUBLE", "units": "DOUBLE"}


def _records(df: pd.DataFrame) -> list[dict]:
    df = df.astype(object)
    return df.where(df.notna(), None).to_dict("records")


@model(
    "plan.capex_line",
    kind="FULL",
    grain=["version_id", "item_id", "period"],
    depends_on=["plan.capex_item", "dims.reg_asset", "dims.ref_asset_class", "dims.ctl_version", "dims.dim_period", "dims.ref_route",
                "history.shipments", "plan.demand_financialised"],
    columns={c: TYPES[c] for c in COLUMNS},
    description="The capital plan walked: cash out, additions, depreciation, lease charges and book value by item × period.",
)
def execute(context: ExecutionContext, start: datetime, end: datetime, execution_time: datetime, **kwargs: t.Any) -> pd.DataFrame:
    T = context.resolve_table
    fetch = lambda sql: _records(context.fetchdf(sql))
    versions = [r["version_id"] for r in fetch(f"select version_id from {T('dims.ctl_version')} where version_kind <> 'actual' and from_period is not null")]
    acts = fetch(f"select * from {T('plan.capex_item')} order by entered_on, act_id")
    rows: list[dict] = []
    for v in versions:
        mine = in_force([a for a in acts if a["version_id"] == v])
        rows += compute(read_inputs(fetch, T, v), mine)
    return pd.DataFrame(rows, columns=COLUMNS)
