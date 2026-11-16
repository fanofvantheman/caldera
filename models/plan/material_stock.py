"""The material purchase plan and its stock (DEC-20261116-04): each key raw material at each plant on each plan, period by
period — requirement, purchase (quantity and price, from its declared source), opening, the weighted-average cost,
consumption at it, closing. Made by `calc.purchases`, the function the face's page also calls. Python because each
period's average is made from the one before (charter, scope default 2). The costing reads the average and nothing else
(point 5)."""
from __future__ import annotations

import typing as t
from datetime import datetime

import pandas as pd
from sqlmesh import ExecutionContext, model

from calc.purchases import COLUMNS, TYPES, compute_all


def _records(df: pd.DataFrame) -> list[dict]:
    df = df.astype(object)
    return df.where(df.notna(), None).to_dict("records")


@model(
    "plan.material_stock",
    kind="FULL",
    grain=["version_id", "input_code", "plant_code", "period"],
    depends_on=["plan.material_requirement", "plan.input_price_in_force", "plan.purchase_act", "dims.ref_key_material", "dims.dim_input_material",
                "dims.dim_period", "dims.ctl_version", "plan.assumption_in_force"],
    columns={c: TYPES[c] for c in COLUMNS},
    description="Key raw materials: purchases, stock and the weighted-average cost, by version, plant and period.",
)
def execute(context: ExecutionContext, start: datetime, end: datetime, execution_time: datetime, **kwargs: t.Any) -> pd.DataFrame:
    T = context.resolve_table
    fetch = lambda sql: _records(context.fetchdf(sql))
    return pd.DataFrame(compute_all(fetch, T), columns=COLUMNS)
