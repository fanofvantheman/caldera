"""What the plan's pages read from the warehouse — every question a page asks, as a function. Read only: what the face
shows is what the last run said."""
from __future__ import annotations

from chassis.warehouse import one, q


def versions() -> list[dict]:
    return q("select * from dims.ctl_version order by case status when 'open' then 0 when 'frozen' then 1 else 2 end, version_id")


def open_versions() -> list[dict]:
    return q("select * from dims.ctl_version where status = 'open' order by named_on desc")


def version(version_id: str) -> dict | None:
    return one("select * from dims.ctl_version where version_id = ?", version_id)


def default_version() -> str | None:
    r = one("select version_id from dims.ctl_version where status = 'open' order by named_on desc limit 1")
    return r["version_id"] if r else None


def horizon(version_id: str) -> list[str]:
    v = version(version_id)
    if not v:
        return []
    return [r["period"] for r in q("select period from dims.dim_period where period between ? and ? order by period", v["horizon_start"], v["horizon_end"])]


def layers() -> list[dict]:
    return q("select * from plan.ref_layer order by layer_no")


def accounts() -> list[dict]:
    return q("select distinct account_code from plan.unconstrained_demand_period order by 1")


def demand(version_id: str, account: str | None) -> dict:
    """Standard materials down, periods across, cases in the cell; the layers under the total by period."""
    where = "where version_id = ?" + (" and account_code = ?" if account else "")
    params = [version_id] + ([account] if account else [])
    cells = q(f"select standard_material, period, sum(cases) cases from plan.unconstrained_demand_period {where} group by all order by 1, 2", *params)
    by_layer = q(f"""select period, sum(l1_baseline) l1, sum(l2_adjustment) l2, sum(l4_distribution) l4, sum(l6_promotions) l6,
                            sum(l7_innovation) l7, sum(l8_exit) l8, sum(cases) cases
                     from plan.unconstrained_demand_period {where} group by period order by period""", *params)
    periods = sorted({c["period"] for c in cells})
    grid: dict[str, dict[str, float]] = {}
    for c in cells:
        grid.setdefault(c["standard_material"], {})[c["period"]] = c["cases"]
    rows = [{"material": m, "cells": [g.get(p) for p in periods], "total": sum(g.values())} for m, g in grid.items()]
    totals = [sum(r["cells"][i] or 0 for r in rows) for i in range(len(periods))]
    return {"periods": periods, "rows": rows, "by_layer": by_layer, "totals": totals, "grand": sum(totals)}


def entries(version_id: str, layer_no: int | None, show_withdrawn: bool) -> list[dict]:
    sql = """select e.*, r.description reason_description from plan.layer_entry e left join plan.ref_reason_code r on r.reason_code = e.reason_code
             where e.version_id = ?""" + (" and e.layer_no = ?" if layer_no else "") + ("" if show_withdrawn else " and not (e.withdrawn and e.withdrawn_by_owner)")
    params = [version_id] + ([layer_no] if layer_no else [])
    return q(sql + " order by e.layer_no, e.entered_on desc, e.entry_id desc", *params)


def entry(entry_id: str) -> dict | None:
    return one("select * from plan.layer_entry where entry_id = ?", entry_id)


def reasons() -> list[dict]:
    return q("select * from plan.ref_reason_code order by reason_code")


def material_scopes() -> list[dict]:
    return q("""select distinct ancestor_code code, ancestor_level as lvl from dims.dim_material_hierarchy where descendant_is_leaf
                union all select promo_group_code, 'promo_group' as lvl from dims.ref_promo_group order by 2, 1""")


def customer_scopes() -> list[dict]:
    return q("select distinct ancestor_code code, ancestor_level as lvl from dims.dim_customer_hierarchy where descendant_is_leaf order by 2, 1")


def material_scope_resolves(code: str) -> bool:
    return one("""select 1 ok where exists (select 1 from dims.dim_material_hierarchy where ancestor_code = ? and descendant_is_leaf)
                                 or exists (select 1 from dims.ref_promo_group where promo_group_code = ?)""", code, code) is not None


def customer_scope_resolves(code: str) -> bool:
    return one("select 1 ok from dims.dim_customer_hierarchy where ancestor_code = ? and descendant_is_leaf limit 1", code) is not None


def bridge(version_id: str) -> dict:
    rows = q("""select layer_no, layer_name, sum(cases) cases, sum(gross_at_list) gross_at_list, sum(on_invoice_deductions) on_invoice,
                       sum(gross_invoice) gross_invoice, sum(off_invoice_deductions) off_invoice, sum(net_sales) net_sales
                from plan.revenue_bridge where version_id = ? group by all order by layer_no""", version_id)
    by_period = q("""select period, sum(gross_at_list) gross_at_list, sum(on_invoice_deductions) on_invoice, sum(gross_invoice) gross_invoice,
                            sum(off_invoice_deductions) off_invoice, sum(net_sales) net_sales
                     from plan.revenue_bridge where version_id = ? group by period order by period""", version_id)
    gap = one("""select reference_version, sum(plan_cases) plan_cases, sum(reference_cases) reference_cases, sum(cases_gap) cases_gap,
                        sum(plan_net_sales) plan_net_sales, sum(reference_net_sales) reference_net_sales, sum(net_sales_gap) net_sales_gap
                 from plan.gap_to_reference where version_id = ? group by reference_version""", version_id)
    return {"by_layer": rows, "by_period": by_period, "gap": gap}


def events() -> list[dict]:
    return q("select * from plan.promo_event order by window_start, account_code")


def terms() -> list[dict]:
    return q("select * from plan.terms order by account_code, instrument_code")
