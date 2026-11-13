"""Finance's plan at its grain — account × material × period: volume, price and revenue, with the demand plan beneath;
cost of goods and margin where a standard cost per case is known (none yet in Caldera).

Fed cells start as the demand plan valued; built cells exist only where Finance has typed at the grain and have no
source. Every figure in force is then replayed in the order it was typed: the cells it wrote when it was typed are put
back as they were — the mix fixed as at typing — and a figure saved before spreads were recorded is spread now. The
arithmetic is `calc.finance`, the same function the face calls as a person types, so the grid before a save and this
model after it agree to the cent; both hand it the rules of `plan.ref_grid_measure`. Ordered, iterative arithmetic,
which is why it is Python (charter, scope default 2).
"""
from __future__ import annotations

import typing as t
from collections import defaultdict
from datetime import datetime

import pandas as pd
from sqlmesh import ExecutionContext, model

from calc.finance import COLUMNS, Grid, rules_from

TYPES = {"version_id": "TEXT", "account_code": "TEXT", "material_code": "TEXT", "period": "TEXT", "fiscal_year": "INT",
         "source": "TEXT", "source_cases": "DOUBLE", "source_net_sales": "DOUBLE", "source_price": "DOUBLE",
         "cases": "DOUBLE", "price": "DOUBLE", "net_sales": "DOUBLE", "std_cost": "DOUBLE", "cogs": "DOUBLE", "margin": "DOUBLE",
         "volume_edit_id": "TEXT", "price_edit_id": "TEXT"}


@model(
    "plan.finance_plan",
    kind="FULL",
    grain=["version_id", "account_code", "material_code", "period"],
    depends_on=["plan.demand_financialised", "plan.finance_edit", "plan.finance_edit_cell", "plan.finance_source", "plan.ref_grid_measure",
                "dims.dim_customer_hierarchy", "dims.dim_material_hierarchy", "dims.dim_period"],
    columns={c: TYPES[c] for c in COLUMNS},
    description="Finance's plan: volume × price = revenue at account × material × period, fed by the demand plan or built by Finance.",
)
def execute(context: ExecutionContext, start: datetime, end: datetime, execution_time: datetime, **kwargs: t.Any) -> pd.DataFrame:
    T = context.resolve_table
    # rounded below a millionth: a parallel sum adds in no fixed order, and a run-out's cancelling lines otherwise leave
    # ±1e-14 cases that flip a price between none and -0 from one run to the next
    demand = context.fetchdf(f"""select version_id, account_code, material_code, period, round(sum(cases), 6) cases, round(sum(net_sales), 6) net_sales
                                 from {T('plan.demand_financialised')} group by all""")
    edits = context.fetchdf(f"""select edit_id, version_id, scope_customer, scope_material, period, measure, value
                                from {T('plan.finance_edit')} where state = 'in_force' order by entered_on, edit_id""")
    written = context.fetchdf(f"select typed, account_code, material_code, value from {T('plan.finance_edit_cell')} order by edit_id")
    decl = context.fetchdf(f"select account_code, material_code, source from {T('plan.finance_source')} where valid")
    cust = context.fetchdf(f"select ancestor_code, descendant_code from {T('dims.dim_customer_hierarchy')} where descendant_level = 'account'")
    mats = context.fetchdf(f"select ancestor_code, descendant_code from {T('dims.dim_material_hierarchy')} where descendant_level = 'material'")
    fy_of = {p: int(fy) for p, fy in context.fetchdf(f"select period, fiscal_year from {T('dims.dim_period')}").itertuples(index=False, name=None)}
    reg = context.fetchdf(f"select * from {T('plan.ref_grid_measure')}").astype(object)
    rules = rules_from(reg.where(reg.notna(), None).to_dict("records"))

    declared = {(a, m): s for a, m, s in decl.itertuples(index=False, name=None)}
    def source_of(acct: str, mat: str) -> str:
        return declared.get((acct, mat)) or declared.get((acct, "ALL")) or "fed"
    accounts_under: dict[str, set] = defaultdict(set)
    for a, d in cust.itertuples(index=False, name=None):
        accounts_under[a].add(d)
    materials_under: dict[str, set] = defaultdict(set)
    for a, d in mats.itertuples(index=False, name=None):
        materials_under[a].add(d)
    on_record: dict[str, list] = defaultdict(list)
    for typed, a, m, x in written.itertuples(index=False, name=None):
        on_record[typed].append((a, m, float(x)))

    grid = Grid(dict(accounts_under), dict(materials_under), source_of, fy_of, rules).from_source(demand.itertuples(index=False, name=None))
    grid.replay(edits.to_dict("records"), on_record)
    return pd.DataFrame(list(grid.cells.values()), columns=COLUMNS)
