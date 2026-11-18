"""When each supersession link switches (DEC-20261118-01 point 3): on its declared week, or — the default for Replace —
when the predecessor's stock runs out: what it holds across the network at the plan's first week (each stocking point's
order-up-to target, as the inventory plan opens it) sold down at its own baseline demand with nothing more made. Read from
the baseline before any link (layer 1), so a link never decides its own switch. Python for the walk (charter, scope
default 2)."""
from __future__ import annotations

import typing as t
from collections import defaultdict
from datetime import datetime

import pandas as pd
from sqlmesh import ExecutionContext, model

from calc.inventory import safety_stock

COLUMNS = {"version_id": "TEXT", "link_id": "TEXT", "switch": "TEXT", "switch_week": "TEXT", "end_week": "TEXT", "stock_at_start": "DOUBLE", "run_out_week": "TEXT", "says": "TEXT"}


def _records(df: pd.DataFrame) -> list[dict]:
    df = df.astype(object)
    return df.where(df.notna(), None).to_dict("records")


@model(
    "plan.supersession_switch",
    kind="FULL",
    grain=["version_id", "link_id"],
    depends_on=["plan.supersession_link", "plan.layer1_lines", "dims.ref_serving_node", "plan.demand_variability", "dims.ref_service_level",
                "dims.ref_replenishment", "dims.ref_lane", "dims.dim_week", "dims.ctl_version"],
    columns=COLUMNS,
    description="The week each supersession link switches: declared, or at the predecessor's run-out.",
)
def execute(context: ExecutionContext, start: datetime, end: datetime, execution_time: datetime, **kwargs: t.Any) -> t.Iterator[pd.DataFrame]:
    T = context.resolve_table
    fetch = lambda sql: _records(context.fetchdf(sql))
    links = fetch(f"select version_id, link_id, any_value(switch) switch, any_value(switch_week) switch_week, any_value(end_week) end_week, list(distinct from_material) froms from {T('plan.supersession_link')} group by all")
    out = []
    review = (fetch(f"select max(review_weeks) r from {T('dims.ref_replenishment')}") or [{"r": 1}])[0]["r"] or 1
    fill_b = {r["service_class"]: r["fill_rate"] for r in fetch(f"select * from {T('dims.ref_service_level')}")}
    sigma = {(r["node_code"], r["material_code"]): r["sigma"] for r in fetch(f"select node_code, material_code, sigma from {T('plan.demand_variability')}")}
    for ln in links:
        v = ln["version_id"]
        if ln["switch"] != "run_out":
            out.append({**{k: ln[k] for k in ("version_id", "link_id", "switch", "switch_week", "end_week")}, "stock_at_start": None, "run_out_week": None,
                        "says": f"on the week declared, {ln['switch_week']}"})
            continue
        ver = fetch(f"select from_period, plan_through from {T('dims.ctl_version')} where version_id = '{v}'")[0]
        weeks = [r["week_id"] for r in fetch(f"select week_id from {T('dims.dim_week')} where period > '{ver['from_period']}' and period <= '{ver['plan_through']}' order by week_id")]
        froms = "', '".join(ln["froms"])
        dem = defaultdict(lambda: defaultdict(float))
        for r in fetch(f"""select n.node_code, l.week_id, sum(l.cases) cases from {T('plan.layer1_lines')} l join {T('dims.ref_serving_node')} n using (ship_to_code)
                           where l.version_id = '{v}' and l.material_code in ('{froms}') group by all"""):
            dem[r["node_code"]][r["week_id"]] += float(r["cases"] or 0)
        total = [sum(dem[n][w] for n in dem) for w in weeks]
        stock = 0.0
        for n, by in dem.items():                      # each point's opening: the first week's demand and its buffer
            mean = sum(by.values()) / len(weeks) if weeks else 0.0
            ss = sum(safety_stock(sigma.get((n, m)) or 0.0, mean, 0, review, fill_b.get("B")) for m in ln["froms"])
            stock += (by.get(weeks[0], 0.0) if weeks else 0.0) + ss
        left, run_out = stock, None
        for w, d in zip(weeks, total):
            left -= d
            if left <= 0:
                run_out = w
                break
        out.append({**{k: ln[k] for k in ("version_id", "link_id", "switch", "end_week")}, "switch_week": run_out or (weeks[-1] if weeks else None),
                    "stock_at_start": stock, "run_out_week": run_out,
                    "says": f"at run-out: {stock:,.0f} cases on hand sold down at the baseline — out in {run_out}" if run_out else "at run-out: not out within the plan"})
    if out:                                              # no link on any Plan: an empty table, which a model yields as nothing
        yield pd.DataFrame(out, columns=list(COLUMNS))
    else:
        yield from ()
