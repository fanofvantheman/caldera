"""The material balance (DEC-20261116-04, DEC-20261120-02 point 7): each key raw material at each plant on each plan, period
by period — opening, consumption, contracted receipts, additional receipts, closing, in volume, value and cost basis.
Made by `calc.purchases`, the function the face's pages also call. Python because each period opens on the one before's
closing (charter, scope default 2). Consumption is valued at the opening cost basis, and the costing reads that and
nothing else (DEC-20261116-04 point 5). The additional receipts are the typed ones and nothing else (DEC-20261124-02); only a typed one is
carried (plan.purchase_act, DEC-20261120-02 point 6)."""
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
    description="Key raw materials: the material balance — opening, consumption, contracted and additional receipts, closing — by version, plant and period.",
)
def execute(context: ExecutionContext, start: datetime, end: datetime, execution_time: datetime, **kwargs: t.Any) -> pd.DataFrame:
    T = context.resolve_table
    fetch = lambda sql: _records(context.fetchdf(sql))
    return pd.DataFrame(compute_all(fetch, T), columns=COLUMNS)
