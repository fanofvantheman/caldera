"""The inventory plan (DEC-20261117-02): each stocking point's demand, target, receipts and projected stock by version ×
node × material × period — the DCs replenishing to an order-up-to target from the plant that supplies them, and each
plant's receipts its production requirement. Made by `calc.inventory`, the function the supply pages and the storage
stress test also call. Python because each week's stock is made from the one before (charter, scope default 2)."""
from __future__ import annotations

import typing as t
from datetime import datetime

import pandas as pd
from sqlmesh import ExecutionContext, model

from calc.inventory import COLUMNS, TYPES, compute, read_inputs


def _records(df: pd.DataFrame) -> list[dict]:
    df = df.astype(object)
    return df.where(df.notna(), None).to_dict("records")


@model(
    "plan.inventory_flow",
    kind="FULL",
    grain=["version_id", "node_code", "material_code", "period"],
    depends_on=["plan.unconstrained_demand", "dims.ref_serving_node", "plan.sourcing_rule", "dims.ref_lane", "plan.demand_variability",
                "plan.service_class", "dims.ref_replenishment", "plan.production_act", "dims.dim_node", "dims.dim_week", "dims.ctl_version"],
    columns={c: TYPES[c] for c in COLUMNS},
    description="The inventory plan: demand, target, receipts and projected stock by node, material and period; a plant's receipts are its production.",
)
def execute(context: ExecutionContext, start: datetime, end: datetime, execution_time: datetime, **kwargs: t.Any) -> pd.DataFrame:
    T = context.resolve_table
    fetch = lambda sql: _records(context.fetchdf(sql))
    rows: list[dict] = []
    for v in fetch(f"select version_id from {T('dims.ctl_version')} where version_kind <> 'actual' and from_period is not null order by 1"):
        rows += compute(read_inputs(fetch, T, v["version_id"]), v["version_id"])[1]
    return pd.DataFrame(rows, columns=COLUMNS)
