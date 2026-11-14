"""The opex schedule: entity × the plan's cost centre × account × period on each open version — every line a driver and a
rate, every month driver × rate until someone types it, a typed month held with the calculated amount beside it.

The inputs are read by `calc.schedule.read_inputs` and the figures made by `calc.schedule.compute`, the same function the
face's working copy calls as a person types, so the schedule before a save and this model after it agree to the cent.
Acts apply in the order typed, which is why it is Python (charter, scope default 2).
"""
from __future__ import annotations

import typing as t
from datetime import datetime

import pandas as pd
from sqlmesh import ExecutionContext, model

from calc.schedule import COLUMNS, compute, in_force, read_inputs, rules_from

TYPES = {"version_id": "TEXT", "entity_code": "TEXT", "cost_centre_code": "TEXT", "account_code": "TEXT", "period": "TEXT", "fiscal_year": "INT",
         "driver": "TEXT", "driver_qty": "DOUBLE", "rate_calc": "DOUBLE", "rate": "DOUBLE", "rate_typed": "BOOLEAN", "amount_calc": "DOUBLE",
         "amount": "DOUBLE", "state": "TEXT", "typed_calc": "DOUBLE", "moved": "BOOLEAN", "rate_edit_id": "TEXT", "month_edit_id": "TEXT"}


def _records(df: pd.DataFrame) -> list[dict]:
    df = df.astype(object)
    return df.where(df.notna(), None).to_dict("records")


@model(
    "plan.opex_schedule",
    kind="FULL",
    grain=["version_id", "entity_code", "cost_centre_code", "account_code", "period"],
    depends_on=["plan.cost_actual", "plan.schedule_edit", "plan.labour_cost", "plan.ref_grid_measure", "plan.demand_financialised", "history.shipments",
                "dims.dim_period", "dims.ctl_version", "dims.ref_step_horizon", "dims.ref_route", "dims.reg_assumption", "plan.assumption_in_force"],
    columns={c: TYPES[c] for c in COLUMNS},
    description="The opex schedule: each line a driver and a rate; each month calculated until typed.",
)
def execute(context: ExecutionContext, start: datetime, end: datetime, execution_time: datetime, **kwargs: t.Any) -> pd.DataFrame:
    T = context.resolve_table
    fetch = lambda sql: _records(context.fetchdf(sql))
    rules = rules_from(fetch(f"select * from {T('plan.ref_grid_measure')}"))
    versions = [r["version_id"] for r in fetch(f"select version_id from {T('dims.ctl_version')} where status = 'open'")]
    acts = in_force(fetch(f"select * from {T('plan.schedule_edit')} order by entered_on, edit_id"))      # withdrawn acts out
    rows: list[dict] = []
    for v in versions:
        inp = read_inputs(fetch, T, v, labour=True)
        rows += compute(inp, [a for a in acts if a["version_id"] == v], rules).values()
    return pd.DataFrame(rows, columns=COLUMNS)
