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


# ---- the head of demand's dashboard and the accuracy page ----
def _acc(rows: list[dict]) -> None:
    """Accuracy and bias from summed errors, in place: 1 − Σ|e|/Σactual and Σe/Σactual; None where nothing shipped."""
    for r in rows:
        a = r.get("actual") or 0.0
        r["accuracy"] = 1 - r["abs_error"] / a if a else None
        r["bias"] = r["err"] / a if a else None


def accuracy_periods(lag: int) -> list[str]:
    return [r["period"] for r in q("select distinct period from plan.forecast_accuracy where lag = ? order by 1", lag)]


def accuracy(lag: int, periods: list[str], by: str = "") -> list[dict]:
    """Forecast accuracy over `periods` at `lag`, grouped by the columns in `by` (a comma list, or '' for one row)."""
    if not periods:
        return []
    sel = f"{by}, " if by else ""
    grp = f"group by {by} order by {by}" if by else ""
    rows = q(f"""select {sel}sum(actual_cases) actual, sum(forecast_cases) forecast, sum(abs_error) abs_error, sum(error) as err
                 from plan.forecast_accuracy where lag = ? and period in ({','.join('?' * len(periods))}) {grp}""", lag, *periods)
    _acc(rows)
    return rows


def accuracy_tree(lag: int, periods: list[str]) -> list[dict]:
    """Category → product → standard material, each with accuracy, bias and actual over the window."""
    mats = accuracy(lag, periods, "category_code, category_name, product_code, product_name, standard_material, material_name")
    prods = accuracy(lag, periods, "category_code, category_name, product_code, product_name")
    cats = accuracy(lag, periods, "category_code, category_name")
    for p in prods:
        p["children"] = [m for m in mats if m["product_code"] == p["product_code"]]
    for c in cats:
        c["children"] = [p for p in prods if p["category_code"] == c["category_code"]]
    return cats


def demand_tree(version_id: str, fy: int) -> dict:
    """The plan fiscal year by category → product → standard material: this view's total (closed periods as actuals, the
    rest plan), the prior fiscal year's shipments, and the reference version's total where it has the year."""
    v = version(version_id) or {}
    ref_id = v.get("reference_version")
    cur = q("""select m.category_code, m.category_name, m.product_code, m.product_name, d.standard_material, m.material_name, sum(d.cases) cases
               from plan.demand_review d join dims.dim_material m on m.material_code = d.standard_material
               where d.version_id = ? and d.fiscal_year = ? group by all""", version_id, fy)
    py = {r["standard_material"]: r["cases"] for r in q("select standard_material, sum(cases) cases from history.shipments_period where fiscal_year = ? group by 1", fy - 1)}
    ref = {r["standard_material"]: r["cases"] for r in q("select standard_material, sum(cases) cases from plan.unconstrained_demand_period where version_id = ? and fiscal_year = ? group by 1", ref_id, fy)} if ref_id else {}
    for r in cur:
        r["py"] = py.get(r["standard_material"], 0.0); r["ref"] = ref.get(r["standard_material"])
    def roll(rows: list[dict], key: str, label: str) -> list[dict]:
        out: dict[str, dict] = {}
        for r in rows:
            o = out.setdefault(r[key], {"code": r[key], "label": r[label], "cases": 0.0, "py": 0.0, "ref": 0.0 if ref else None, "children": []})
            o["cases"] += r["cases"]; o["py"] += r["py"]
            if ref: o["ref"] += r["ref"] or 0.0
            o["children"].append(r)
        return sorted(out.values(), key=lambda o: -o["cases"])
    for r in cur:
        r["code"], r["label"] = r["standard_material"], r["material_name"]; r["children"] = []
    prods = roll(cur, "product_code", "product_name")
    for p in prods:
        p["category_code"] = p["children"][0]["category_code"]; p["category_name"] = p["children"][0]["category_name"]
        p["children"].sort(key=lambda m: -m["cases"])
    cats = roll(prods, "category_code", "category_name")
    total = {"cases": sum(c["cases"] for c in cats), "py": sum(c["py"] for c in cats), "ref": (sum(c["ref"] for c in cats) if ref else None)}
    return {"categories": cats, "total": total, "ref_id": ref_id, "fy": fy}


def demand_series(version_id: str, fy: int) -> dict:
    """The plan fiscal year by period: this view (actual where closed, plan after), the reference version, the prior year's
    shipments — cases, one axis."""
    v = version(version_id) or {}
    cur = q("select period, source, sum(cases) cases from plan.demand_review where version_id = ? and fiscal_year = ? group by all order by 1", version_id, fy)
    ref = q("select period, sum(cases) cases from plan.unconstrained_demand_period where version_id = ? and fiscal_year = ? group by 1 order by 1", v.get("reference_version"), fy) if v.get("reference_version") else []
    py = q("select period, fiscal_year, sum(cases) cases from history.shipments_period where fiscal_year = ? group by all order by 1", fy - 1)
    periods = [r["period"] for r in q("select period from dims.dim_period where fiscal_year = ? order by 1", fy)]
    return {"periods": periods, "view": {r["period"]: (r["cases"], r["source"]) for r in cur},
            "ref": {r["period"]: r["cases"] for r in ref}, "py": {f"{fy}P{r['period'][5:]}": r["cases"] for r in py}, "ref_id": v.get("reference_version")}


def revenue_fy(version_id: str, fy: int) -> dict | None:
    """Net sales this fiscal year against the reference, on the periods both versions value — the open view values only
    the periods ahead of it, so a whole-year figure would not be a like-for-like reading."""
    v = version(version_id) or {}
    r = one("""select min(g.period) p_from, max(g.period) p_to, sum(g.plan_net_sales) net_sales, sum(g.reference_net_sales) ref_net_sales
               from plan.gap_to_reference g join dims.dim_period p on p.period = g.period where g.version_id = ? and p.fiscal_year = ?""", version_id, fy)
    return {"net_sales": r["net_sales"] if r else None, "ref_net_sales": r["ref_net_sales"] if r else None, "ref_id": v.get("reference_version"),
            "p_from": r["p_from"] if r else None, "p_to": r["p_to"] if r else None}


def unit_status(version_id: str, fy: int) -> list[dict]:
    """One row per planning unit: its demand this fiscal year against the prior year, and the unit's submission state."""
    return q("""select u.code, u.unit_name, s.state, s.open_below, s.acted_by, s.acted_on,
                       (select sum(d.cases) from plan.demand_review d join dims.dim_account a on a.account_code = d.account_code
                         where d.version_id = ? and d.fiscal_year = ? and a.planning_unit = u.code) cases,
                       (select sum(h.cases) from history.shipments_period h join dims.dim_account a on a.account_code = h.account_code
                         where h.fiscal_year = ? and a.planning_unit = u.code) py
                from (select distinct h.ancestor_code as code, a.planning_unit_name as unit_name from dims.dim_customer_hierarchy h
                      join dims.dim_account a on a.planning_unit = h.ancestor_code where h.ancestor_level = 'planning_unit') u
                left join plan.submission_state s on s.version_id = ? and s.subject = 'unit' and s.node = u.code
                order by cases desc nulls last""", version_id, fy, fy - 1, version_id)


def ladder(version_id: str) -> list[dict]:
    """The submission ladder as the run sees it: how many of each rung's subjects are in. Rungs: the account-facing layers at
    their accounts, the planners' layers at their units, the units, the plan."""
    rows = q("""select case when l.submits_at = 'account' then 'inputs' when l.submits_at = 'unit' then 'build' when s.subject = 'unit' then 'units' else 'plan' end rung,
                       sum(case when s.state in ('submitted', 'rolled_up') then 1 else 0 end) done,
                       sum(case when s.state in ('submitted', 'rolled_up', 'ready', 'open') then 1 else 0 end) total
                from plan.submission_state s left join plan.ref_layer l on 'layer:' || l.layer_no = s.subject
                where s.version_id = ? and s.state not in ('n/a', 'nothing')
                  and ((l.submits_at = 'account' and s.node in (select descendant_code from dims.dim_customer_hierarchy where descendant_level = 'account'))
                    or (l.submits_at = 'unit' and s.node in (select descendant_code from dims.dim_customer_hierarchy where descendant_level = 'planning_unit'))
                    or (s.subject = 'unit') or (s.subject = 'plan' and s.node = 'ALL'))
                group by 1""", version_id)
    by = {r["rung"]: r for r in rows}
    return [{"key": k, "label": lab, "says": say, "done": by.get(k, {}).get("done", 0), "total": by.get(k, {}).get("total", 0)}
            for k, lab, say in (("inputs", "Inputs in", "account layers at their accounts"), ("build", "Plans built", "planners' layers at their units"),
                                ("units", "Units submitted", "each unit's planner"), ("plan", "Plan submitted", "to the business"))]


def account_of_ship_to(ship_to: str) -> str | None:
    r = one("select account_code from dims.dim_ship_to where ship_to_code = ?", ship_to)
    return r["account_code"] if r else None


def unit_of_account(account: str) -> str | None:
    r = one("select planning_unit from dims.dim_account where account_code = ?", account)
    return r["planning_unit"] if r else None
