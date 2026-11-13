"""Finance's plan at its grain — account × material × period: volume, price and revenue, with the demand plan beneath.

Fed cells start as the demand plan valued (cases, and net sales per case as the price); built cells exist only where
Finance has typed at the grain and have no source. Finance's figures are then applied in the order they were typed —
every volume first, then every price, so a volume never moves a price typed at a node:

- a volume typed at a node is spread over the node's cells by the shape beneath it — the source's volumes where fed,
  Finance's own where built; where that shape is all zero, evenly;
- a price typed at a node moves every price beneath it by one proportion, so the node's calculated price (revenue ÷
  volume) is what was typed; a cell with no price takes the typed price.

A later figure overwrites an earlier one where their scopes meet. Revenue is always volume × price; above the grain the
price is never stored. This is ordered, iterative arithmetic, which is why it is Python (charter, scope default 2).
"""
from __future__ import annotations

import typing as t
from collections import defaultdict
from datetime import datetime

import pandas as pd
from sqlmesh import ExecutionContext, model

COLUMNS = {
    "version_id": "TEXT", "account_code": "TEXT", "material_code": "TEXT", "period": "TEXT", "fiscal_year": "INT",
    "source": "TEXT", "source_cases": "DOUBLE", "source_net_sales": "DOUBLE", "source_price": "DOUBLE",
    "cases": "DOUBLE", "price": "DOUBLE", "net_sales": "DOUBLE", "volume_edit_id": "TEXT", "price_edit_id": "TEXT",
}


@model(
    "plan.finance_plan",
    kind="FULL",
    grain=["version_id", "account_code", "material_code", "period"],
    depends_on=["plan.demand_financialised", "plan.finance_edit", "plan.finance_source", "dims.dim_customer_hierarchy",
                "dims.dim_material_hierarchy", "dims.dim_period"],
    columns=COLUMNS,
    description="Finance's plan: volume × price = revenue at account × material × period, fed by the demand plan or built by Finance.",
)
def execute(context: ExecutionContext, start: datetime, end: datetime, execution_time: datetime, **kwargs: t.Any) -> pd.DataFrame:
    T = context.resolve_table
    demand = context.fetchdf(f"""select version_id, account_code, material_code, period, any_value(fiscal_year) fiscal_year,
                                        sum(cases) cases, sum(net_sales) net_sales
                                 from {T('plan.demand_financialised')} group by all""")
    edits = context.fetchdf(f"""select edit_id, version_id, scope_customer, scope_material, period, measure, value, at_grain
                                from {T('plan.finance_edit')} where state = 'in_force' order by entered_on, edit_id""")
    decl = context.fetchdf(f"select account_code, material_code, source from {T('plan.finance_source')} where valid")
    cust = context.fetchdf(f"select ancestor_code, descendant_code from {T('dims.dim_customer_hierarchy')} where descendant_level = 'account'")
    mats = context.fetchdf(f"select ancestor_code, descendant_code from {T('dims.dim_material_hierarchy')} where descendant_level = 'material'")
    fy_of = dict(context.fetchdf(f"select period, fiscal_year from {T('dims.dim_period')}").itertuples(index=False, name=None))

    declared = {(a, m): s for a, m, s in decl.itertuples(index=False, name=None)}
    def source_of(acct: str, mat: str) -> str:
        return declared.get((acct, mat)) or declared.get((acct, "ALL")) or "fed"
    accounts_under: dict[str, set] = defaultdict(set)
    for a, d in cust.itertuples(index=False, name=None):
        accounts_under[a].add(d)
    materials_under: dict[str, set] = defaultdict(set)
    for a, d in mats.itertuples(index=False, name=None):
        materials_under[a].add(d)

    cells: dict[tuple, dict] = {}                        # (version, account, material, period) → the cell
    by_period: dict[tuple, list] = defaultdict(list)     # (version, period) → its cells, for scope matching

    def new_cell(key: tuple, fy, src: str, sc, sn) -> dict:
        price = (sn / sc) if (sc not in (None, 0)) else None
        c = {"version_id": key[0], "account_code": key[1], "material_code": key[2], "period": key[3], "fiscal_year": fy,
             "source": src, "source_cases": sc, "source_net_sales": sn, "source_price": price,
             "cases": sc if sc is not None else 0.0, "price": price, "volume_edit_id": None, "price_edit_id": None}
        cells[key] = c; by_period[(key[0], key[3])].append(c)
        return c

    for v, a, m, p, fy, sc, sn in demand.itertuples(index=False, name=None):
        if source_of(a, m) == "fed":
            new_cell((v, a, m, p), int(fy), "fed", float(sc or 0), float(sn or 0))
    # a figure typed at the grain starts the cell where nothing feeds it: a built material, or a fed one the demand plan lacks
    for e in edits.itertuples(index=False):
        key = (e.version_id, e.scope_customer, e.scope_material, e.period)
        if e.at_grain and key not in cells:
            src = source_of(e.scope_customer, e.scope_material)
            new_cell(key, fy_of.get(e.period), src, 0.0 if src == "fed" else None, 0.0 if src == "fed" else None)

    def scope(e) -> list[dict]:
        A, M = accounts_under.get(e.scope_customer, set()), materials_under.get(e.scope_material, set())
        return [c for c in by_period.get((e.version_id, e.period), []) if c["account_code"] in A and c["material_code"] in M]

    for e in edits[edits.measure == "volume"].itertuples(index=False):
        S = scope(e)
        if not S:
            continue
        w = [max(c["source_cases"], 0.0) if c["source"] == "fed" else max(c["cases"] or 0.0, 0.0) for c in S]
        W = sum(w)
        for c, wi in zip(S, w):
            c["cases"] = e.value * (wi / W if W > 0 else 1 / len(S))
            c["volume_edit_id"] = e.edit_id

    for e in edits[edits.measure == "price"].itertuples(index=False):
        S = scope(e)
        if not S:
            continue
        priced = [c for c in S if c["price"] is not None]
        vp = sum(c["cases"] for c in priced)
        rp = sum(c["cases"] * c["price"] for c in priced)
        k = e.value * vp / rp if vp > 0 and rp > 0 else None
        for c in S:
            c["price"] = c["price"] * k if (k is not None and c["price"] is not None) else e.value
            c["price_edit_id"] = e.edit_id

    for c in cells.values():
        untouched = c["volume_edit_id"] is None and c["price_edit_id"] is None
        if untouched and c["source"] == "fed":
            c["net_sales"] = c["source_net_sales"]           # exactly the demand plan valued, even where it has no cases
        else:
            c["net_sales"] = c["cases"] * c["price"] if c["price"] is not None else None
    return pd.DataFrame(list(cells.values()), columns=list(COLUMNS))
