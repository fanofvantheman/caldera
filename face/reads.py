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
    """One row per standard material; every period across — closed periods as actuals (marked), open ones as plan — then,
    at the end, each fiscal year's total beside its comparatives: the prior year's actual and the reference version."""
    acct = " and account_code = ?" if account else ""
    ap = [account] if account else []
    rows = q(f"select standard_material, fiscal_year, period, source, sum(cases) cases from plan.demand_review where version_id = ?{acct} group by all order by 3", version_id, *ap)
    v = version(version_id) or {}
    fys = sorted({r["fiscal_year"] for r in rows})
    periods = sorted({r["period"] for r in rows})
    source_of = {r["period"]: r["source"] for r in rows}
    # prior year, same periods: the view's own figure where the prior year is in the view, else shipments
    first_fy = fys[0] if fys else None
    hist = q(f"select standard_material, fiscal_year, period, sum(cases) cases from history.shipments_period where fiscal_year = ?{acct} group by all",
             first_fy - 1, *ap) if first_fy else []
    prior = {(h["standard_material"], h["fiscal_year"], int(h["period"][5:])): h["cases"] for h in hist}
    for r in rows:
        prior[(r["standard_material"], r["fiscal_year"], int(r["period"][5:]))] = prior.get((r["standard_material"], r["fiscal_year"], int(r["period"][5:])), 0.0) + r["cases"]
    fps = {fy: sorted({int(r["period"][5:]) for r in rows if r["fiscal_year"] == fy}) for fy in fys}
    py_tot = {}
    for (m, fy, fp), c in prior.items():
        if fy + 1 in fps and fp in fps[fy + 1]:
            py_tot[(m, fy + 1)] = py_tot.get((m, fy + 1), 0.0) + c
    py_years = {fy for (_, fy) in py_tot}
    ref_id = v.get("reference_version")
    ref = q(f"select standard_material, fiscal_year, sum(cases) cases from plan.unconstrained_demand_period where version_id = ?{acct} group by all", ref_id, *ap) if ref_id else []
    ref_years = {r["fiscal_year"] for r in ref}
    mats = sorted({r["standard_material"] for r in rows})
    cell = {(r["standard_material"], r["period"]): r["cases"] for r in rows}
    fy_tot = {}
    for r in rows:
        fy_tot[(r["standard_material"], r["fiscal_year"])] = fy_tot.get((r["standard_material"], r["fiscal_year"]), 0.0) + r["cases"]
    ref_tot = {(r["standard_material"], r["fiscal_year"]): r["cases"] for r in ref}
    comps = [{"fy": fy, "py": fy in py_years, "ref": fy in ref_years} for fy in fys]
    def line(m: str | None) -> dict:
        pick = (lambda d, k: d.get((m, k))) if m else (lambda d, k: (sum(v for (mm, kk), v in d.items() if kk == k) or None) if any(kk == k for (_, kk) in d) else None)
        blocks = [{"fy": c["fy"], "total": pick(fy_tot, c["fy"]) or 0.0, "py": pick(py_tot, c["fy"]) if c["py"] else None, "ref": pick(ref_tot, c["fy"]) if c["ref"] else None} for c in comps]
        return {"material": m or "Total", "cells": [pick(cell, p) for p in periods], "blocks": blocks, "total": sum(b["total"] for b in blocks)}
    return {"periods": periods, "source_of": source_of, "comps": comps, "ref_id": ref_id, "rows": [line(m) for m in mats], "totals": line(None),
            "n_actual": sum(1 for p in periods if source_of[p] == "actual")}


def by_layer(version_id: str, account: str | None) -> list[dict]:
    where = "where version_id = ?" + (" and account_code = ?" if account else "")
    params = [version_id] + ([account] if account else [])
    return q(f"""select fiscal_year, sum(l1_baseline) l1, sum(l2_adjustment) l2, sum(l4_distribution) l4, sum(l6_promotions) l6,
                        sum(l7_innovation) l7, sum(l8_exit) l8, sum(cases) cases
                 from plan.unconstrained_demand_period {where} group by fiscal_year order by fiscal_year""", *params)


def gap(version_id: str) -> dict:
    by_material = q("""select standard_material, account_code, sum(plan_cases) plan_cases, sum(reference_cases) reference_cases, sum(cases_gap) cases_gap,
                              sum(plan_net_sales) plan_net_sales, sum(reference_net_sales) reference_net_sales, sum(net_sales_gap) net_sales_gap
                       from plan.gap_to_reference where version_id = ? group by all order by net_sales_gap""", version_id)
    by_period = q("""select period, sum(plan_cases) plan_cases, sum(reference_cases) reference_cases, sum(cases_gap) cases_gap,
                            sum(plan_net_sales) plan_net_sales, sum(reference_net_sales) reference_net_sales, sum(net_sales_gap) net_sales_gap
                     from plan.gap_to_reference where version_id = ? group by period order by period""", version_id)
    ref = one("select reference_version from plan.gap_to_reference where version_id = ? limit 1", version_id)
    return {"by_material": by_material, "by_period": by_period, "reference": ref["reference_version"] if ref else None}


def entries(version_id: str, layers: list[int] | None, show_withdrawn: bool) -> list[dict]:
    sql = """select e.*, r.description reason_description from plan.layer_entry e left join plan.ref_reason_code r on r.reason_code = e.reason_code
             where e.version_id = ?""" + (f" and e.layer_no in ({','.join('?' * len(layers))})" if layers else "") + ("" if show_withdrawn else " and not (e.withdrawn and e.withdrawn_by_owner)")
    params = [version_id] + (list(layers) if layers else [])
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


# ---- submissions ----
def units() -> list[dict]:
    return q("""select distinct h.ancestor_code as code, a.planning_unit_name as unit_name from dims.dim_customer_hierarchy h
                join dims.dim_account a on a.planning_unit = h.ancestor_code where h.ancestor_level = 'planning_unit' order by 2""")


def accounts_of(unit: str) -> list[dict]:
    return q("""select descendant_code code from dims.dim_customer_hierarchy where ancestor_code = ? and descendant_level = 'account' order by 1""", unit)


def submission_matrix(version_id: str) -> list[dict]:
    return q("""select s.*, l.layer_name from plan.submission_state s left join plan.ref_layer l on 'layer:' || l.layer_no = s.subject
                where s.version_id = ? order by case when s.subject = 'plan' then 2 when s.subject = 'unit' then 1 else 0 end, s.subject, s.node""", version_id)


def submission_acts(version_id: str) -> list[dict]:
    return q("select * from plan.submission where version_id = ? order by acted_on desc, source_file desc, file_row_number desc", version_id)


def layer_closed_at(version_id: str, layer_no: int, scope_customer: str) -> dict | None:
    """The submission, if any, that covers this scope for this layer — the node and who closed it."""
    return one("""select s.scope_node, s.acted_by, s.acted_on from plan.submission s
                  join dims.dim_customer_hierarchy h on h.ancestor_code = s.scope_node and h.descendant_code = ?
                  where s.version_id = ? and s.subject = ? and s.state = 'submitted' and s.acted_by_holder order by h.depth limit 1""",
               scope_customer, version_id, f"layer:{layer_no}")
