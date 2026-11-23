"""The material balance as the stages after supply read it (DEC-20261123-01 point 13): the same calculation as
plan.material_stock, over purchasing's receipts as last published in place of the receipts as sent — for the Plans that
hold a published copy (plan.purchase_published_version) and no others. The costing reads this where it exists and the
balance as it stands elsewhere."""
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
    "plan.material_stock_published",
    kind="FULL",
    grain=["version_id", "input_code", "plant_code", "period"],
    depends_on=["plan.material_requirement", "plan.input_price_in_force", "plan.purchase_published", "plan.purchase_published_version",
                "dims.ref_key_material", "dims.dim_input_material", "dims.dim_period", "dims.ctl_version", "plan.assumption_in_force"],
    columns={c: TYPES[c] for c in COLUMNS},
    description="Key raw materials: the material balance over purchasing's receipts as last published, for the plans that hold a published copy.",
)
def execute(context: ExecutionContext, start: datetime, end: datetime, execution_time: datetime, **kwargs: t.Any) -> t.Iterator[pd.DataFrame]:
    T = context.resolve_table
    fetch = lambda sql: _records(context.fetchdf(sql))
    acts = fetch(f"select * from {T('plan.purchase_published')}")
    out: list[dict] = []
    for v in fetch(f"select version_id from {T('plan.purchase_published_version')} order by 1"):
        out += compute_all(fetch, T, v["version_id"], acts=[a for a in acts if a["version_id"] == v["version_id"]])
    if not out:                                         # no plan holds a published copy: an empty model, not an empty frame
        yield from ()
        return
    yield pd.DataFrame(out, columns=COLUMNS)
