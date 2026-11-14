"""What the plan's pages read from the warehouse — every question a page asks, as a function. Read only: what the face
shows is what the last run said."""
from __future__ import annotations

from chassis.warehouse import one, q


# a version as the face reads it: its status is its state — open or closed — read from the acts (plan.version_state);
# what it was named (open, frozen, closed) is kept beside it
_VERSIONS = """select v.* replace (coalesce(s.state, case v.status when 'open' then 'open' else 'closed' end) as status), v.status as named_status,
                      s.last_act, s.last_act_by, s.last_act_on, s.last_act_reason, s.reference_of, coalesce(s.is_reference, false) is_reference
               from dims.ctl_version v left join plan.version_state s using (version_id)"""


def versions() -> list[dict]:
    return q(f"{_VERSIONS} order by case v.version_kind when 'actual' then 2 else 0 end, case s.state when 'open' then 0 else 1 end, v.version_id")


def open_versions() -> list[dict]:
    return q(f"{_VERSIONS} where s.state = 'open' order by v.named_on desc")


def version(version_id: str) -> dict | None:
    return one(f"{_VERSIONS} where v.version_id = ?", version_id)


def default_version() -> str | None:
    r = one(f"{_VERSIONS} where s.state = 'open' order by v.named_on desc limit 1")
    return r["version_id"] if r else None


def horizon(version_id: str) -> list[str]:
    v = version(version_id)
    if not v:
        return []
    return [r["period"] for r in q("select period from dims.dim_period where period between ? and ? order by period", v["horizon_start"], v["horizon_end"])]


def version_periods(version_id: str | None) -> dict:
    """The periods a grid shows on a version, asked of the version and not the calendar: the actual periods of the year it
    is named for (up to its from point), then the plan periods for its horizon — past the year end where it reaches. Each
    period: period, fiscal_year, fiscal_period, actual."""
    v = version(version_id) if version_id else None
    out = {"fy": None, "from": None, "through": None, "periods": [], "actual": [], "plan": [], "horizon": 0, "quarters": 0}
    if not v or not v.get("from_period"):
        return out
    fy = int(v["fiscal_year"]) if v.get("fiscal_year") else None
    rows = q("""select period, fiscal_year, fiscal_period from dims.dim_period
                where (fiscal_year = ? and period <= ?) or (period > ? and period <= ?) order by period""",
             fy or -1, v["from_period"], v["from_period"], v.get("plan_through") or v["from_period"])
    ps = [{**r, "actual": r["period"] <= v["from_period"]} for r in rows]
    return {"fy": fy, "from": v["from_period"], "through": v.get("plan_through"), "periods": ps,
            "actual": [p["period"] for p in ps if p["actual"]], "plan": [p["period"] for p in ps if not p["actual"]],
            "horizon": int(v.get("horizon_periods") or 0), "quarters": int(v.get("horizon_quarters") or 0)}


def version_kinds() -> list[dict]:
    return q("select * from dims.ref_version_kind order by ord")


def step_horizons() -> list[dict]:
    return q("select * from dims.ref_step_horizon order by ord")


def layers() -> list[dict]:
    return q("select * from plan.ref_layer order by layer_no")


def accounts() -> list[dict]:
    return q("select distinct account_code from plan.unconstrained_demand_period order by 1")


def demand(version_id: str, customer: str | None = None, material: str | None = None) -> dict:
    """One row per standard material; the version's periods across — its actual periods of the year it is named for
    (marked), then the plan for its horizon, past the year end — then, at the end, each fiscal year's total beside its
    comparatives: the prior year's actual and the reference version, over the same periods (a year the horizon cuts is
    totalled to where it stops). At a node of either structure (an account, a unit, all; a category, a product, a material)."""
    acct, ap = _scope_sql(customer, material, "account_code", "standard_material")
    rows = q(f"select standard_material, fiscal_year, period, source, sum(cases) cases from plan.demand_review where version_id = ?{acct} group by all order by 3", version_id, *ap)
    vp = version_periods(version_id)
    if vp["periods"]:                       # the version's periods, not every period its models calculate
        shown = {p["period"] for p in vp["periods"]}
        rows = [r for r in rows if r["period"] in shown]
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
    shown_p = sorted({r["period"] for r in rows})
    ref = q(f"""select standard_material, fiscal_year, sum(cases) cases from plan.unconstrained_demand_period where version_id = ?{acct}
                and period in ({','.join('?' * len(shown_p)) or "''"}) group by all""", ref_id, *ap, *shown_p) if ref_id and shown_p else []
    ref_years = {r["fiscal_year"] for r in ref}
    mats = sorted({r["standard_material"] for r in rows})
    cell = {(r["standard_material"], r["period"]): r["cases"] for r in rows}
    fy_tot = {}
    for r in rows:
        fy_tot[(r["standard_material"], r["fiscal_year"])] = fy_tot.get((r["standard_material"], r["fiscal_year"]), 0.0) + r["cases"]
    ref_tot = {(r["standard_material"], r["fiscal_year"]): r["cases"] for r in ref}
    comps = [{"fy": fy, "py": fy in py_years, "ref": fy in ref_years, "to": f"P{fps[fy][-1]:02d}" if fps[fy] and fps[fy][-1] < 12 and fps[fy][0] == 1 else None} for fy in fys]
    indexed: dict[int, dict] = {}
    def idx(d: dict) -> dict:
        """d keyed (material, k) -> k -> material -> value, built once per dict."""
        if id(d) not in indexed:
            out: dict = {}
            for (m, k), v in d.items():
                out.setdefault(k, {})[m] = v
            indexed[id(d)] = out
        return indexed[id(d)]
    def line(ms: list[str] | None, name: str) -> dict:
        """One row: a single material, a group of them (summed), or — with none — the whole grid."""
        def pick(d, k):
            by_m = idx(d).get(k, {})
            vals = list(by_m.values()) if ms is None else [by_m[m] for m in ms if m in by_m]
            return sum(vals) if vals else None
        blocks = [{"fy": c["fy"], "total": pick(fy_tot, c["fy"]) or 0.0, "py": pick(py_tot, c["fy"]) if c["py"] else None, "ref": pick(ref_tot, c["fy"]) if c["ref"] else None} for c in comps]
        return {"material": name, "cells": [pick(cell, p) for p in periods], "blocks": blocks, "total": sum(b["total"] for b in blocks)}
    # the material structure over the materials in view: category -> product -> standard material, largest first
    info = {r["material_code"]: r for r in q("select material_code, material_name, product_code, product_name, category_code, category_name from dims.dim_material")}
    tree: dict[str, dict] = {}
    for m in mats:
        i = info.get(m) or {"material_name": m, "product_code": "?", "product_name": "Other", "category_code": "?", "category_name": "Other"}
        c = tree.setdefault(i["category_code"], {"code": i["category_code"], "label": i["category_name"], "products": {}})
        p = c["products"].setdefault(i["product_code"], {"code": i["product_code"], "label": i["product_name"], "mats": []})
        p["mats"].append(m)
    groups = []
    for c in tree.values():
        prods = []
        for p in c["products"].values():
            row = line(p["mats"], p["label"]); row.update(code=p["code"], children=sorted((dict(line([m], m), label=(info.get(m) or {}).get("material_name", m)) for m in p["mats"]), key=lambda r: -r["total"]))
            prods.append(row)
        prods.sort(key=lambda r: -r["total"])
        row = line([m for p in c["products"].values() for m in p["mats"]], c["label"]); row.update(code=c["code"], children=prods)
        groups.append(row)
    groups.sort(key=lambda r: -r["total"])
    return {"periods": periods, "source_of": source_of, "comps": comps, "ref_id": ref_id, "groups": groups, "rows": [line([m], m) for m in mats], "totals": line(None, "Total"),
            "n_actual": sum(1 for p in periods if source_of[p] == "actual"), "n_plan": sum(1 for p in periods if source_of[p] != "actual")}


def by_layer(version_id: str, customer: str | None = None, material: str | None = None) -> list[dict]:
    w, wp = _scope_sql(customer, material, "account_code", "standard_material")
    where = "where version_id = ?" + w
    params = [version_id] + wp
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
    """The one calendar: both doors, each event with its source and, for the sender's, its own codes beside ours."""
    return q("""select e.*, x.uplift_cases, x.dip_cases, x.neighbour_cases, x.net_incremental_cases, x.uplift_net_sales, x.neighbour_net_sales,
                       x.net_incremental_net_sales, x.given_on_other_cases, x.net_return, x.neighbours
                from plan.promo_event e left join plan.promo_event_effect x on x.event_id = e.event_id
                order by e.window_start, e.account_code""")


def neighbours() -> list[dict]:
    """Every neighbour line in force, one row per line (not per material), with how many of our materials it reaches."""
    return q("""select version_id, event_id, scope_material, any_value(effect_type) effect_type, any_value(rate) rate, any_value(entered_by) entered_by,
                       any_value(entered_at) entered_at, any_value(note) note, count(material_code) materials, bool_and(event_in_calendar) event_in_calendar
                from plan.promo_neighbour group by all order by event_id, scope_material""")


def event(event_id: str) -> dict | None:
    return one("select * from plan.promo_event where event_id = ?", event_id)


def event_split(event_id: str) -> list[dict]:
    """What a dated window does to our grid: for each trading week it touches, the days of the window in it, the period it
    falls in, and the cases each effect puts there — the uplift, the dip after, any neighbour line."""
    return q("""select l.week_id, w.week_start, w.week_end, w.period, round(coalesce(max(case when l.effect_type = 'primary' then l.in_window end), 0) * 7) as window_days,
                       round(coalesce(max(case when l.effect_type = 'timing_shift' then l.in_dip end), 0) * 7) as dip_days,
                       sum(case when l.effect_type = 'primary' then l.cases else 0 end) as uplift_cases,
                       sum(case when l.effect_type = 'timing_shift' then l.cases else 0 end) as dip_cases,
                       sum(case when l.effect_type in ('cannibalisation', 'halo') then l.cases else 0 end) as neighbour_cases
                from plan.promo_line l join dims.dim_week w on w.week_id = l.week_id where l.event_id = ? group by all order by w.week_start""", event_id)


def weeks_between(start, end) -> list[dict]:
    return q("select week_id, week_start, week_end, period from dims.dim_week where week_end >= ? and week_start <= ? order by week_start", start, end)


def envelopes(version_id: str) -> list[dict]:
    return q("select * from plan.terms_envelope where version_id = ? order by account_code", version_id)


def holders(action: str) -> list[str]:
    return [r["principal"] for r in q("select distinct principal from dims.effective_entitlements where action = ? order by 1", action)]


def open_period_start():
    """The first day of the first period not yet closed — nothing is placed before it."""
    r = one("select min(period_start) d from dims.dim_period where period_state <> 'CLOSED'")
    return r["d"] if r else None


def mapping_structure() -> dict[str, list[dict]]:
    """The promotions system's structure laid against ours, per subject: every code the register names (in force,
    proposed, or seen and not yet mapped), what it lands on, and what that is in our structure."""
    rows = q("""select subject, local_code, local_description, target_code, target_name, review_state, origin, in_force, null as events from plan.promo_mapping
                union all
                select subject, local_code, local_description, proposed_target, proposed_target_name, 'missing', null, false, events
                from plan.worklist_promo_mapping_review where review_state = 'missing'
                order by subject, target_code nulls last, local_code""")
    ours = {
        "customer": {r["code"]: r for r in q("""select account_code as code, account_name as name, planning_unit_name, promotions_master, promo_week_start, channel
                                                from dims.dim_account""")},
        "material": {r["code"]: r for r in q("""select g.promo_group_code as code, any_value(g.promo_group_name) as name, count(*) materials,
                                                       string_agg(m.material_name, '; ' order by m.material_name) material_names
                                                from dims.ref_promo_group g left join dims.dim_material m on m.material_code = g.material_code group by 1""")},
        "mechanic": {r["code"]: r for r in q("select mechanic as code, mechanic_name as name, family, default_uplift_pct, default_dip_pct from dims.ref_mechanic")},
        "funding_type": {r["code"]: r for r in q("select funding_type as code, funding_type_name as name, driver_basis, priced, event_column from dims.ref_funding_type")},
        "status": {r["code"]: r for r in q("select status as code, status_name as name, enters_calendar from dims.ref_promo_status")},
    }
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["subject"], []).append({**r, "ours": ours.get(r["subject"], {}).get(r["target_code"])})
    return out


def events_held() -> list[dict]:
    return q("select * from plan.worklist_promo_held order by window_start")


def events_refused() -> list[dict]:
    return q("select * from plan.worklist_promo_refused order by event_id")


def events_cancelled() -> list[dict]:
    return q("select event_id, local_account, local_product_group, window_start, window_end, sender_file from plan.promo_sender_event where state = 'cancelled' order by event_id")


def accounts_master() -> list[dict]:
    return q("select account_code, account_name, promotions_master, supplies_scan_data, promo_week_start from dims.dim_account order by promotions_master, account_code")


def account(code: str) -> dict | None:
    return one("select * from dims.dim_account where account_code = ?", code)


def promo_groups() -> list[dict]:
    return q("select promo_group_code, any_value(promo_group_name) promo_group_name, count(*) materials from dims.ref_promo_group group by 1 order by 1")


def mechanics() -> list[dict]:
    return q("select * from dims.ref_mechanic order by family, mechanic")


def statuses() -> list[dict]:
    return q("select * from dims.ref_promo_status order by status")


def mapping_targets(subject: str) -> list[dict]:
    """Our list a sender's code maps onto, per subject: code and description."""
    sql = {"mechanic": "select mechanic code, mechanic_name description from dims.ref_mechanic order by 1",
           "funding_type": "select funding_type code, funding_type_name description from dims.ref_funding_type order by 1",
           "status": "select status code, status_name description from dims.ref_promo_status order by 1",
           "customer": "select account_code code, account_name description from dims.dim_account order by 1",
           "material": "select promo_group_code code, any_value(promo_group_name) description from dims.ref_promo_group group by 1 order by 1"}[subject]
    return q(sql)


def mapping_review() -> list[dict]:
    """The codes waiting for a person, lowest confidence first; codes with no proposal at all lead."""
    return q("select * from plan.worklist_promo_mapping_review order by confidence_rank, subject, local_code")


def mapping_in_force() -> list[dict]:
    return q("select * from plan.promo_mapping order by subject, local_code")


def terms() -> list[dict]:
    return q("select * from plan.terms order by account_code, instrument_code")


def price_lists() -> list[dict]:
    """Every price list with its currency, the accounts on it, and each material's rows in validity order, so an
    increase reads as a dated event with the price before and after."""
    rows = q("""select p.*, coalesce(m.material_name, p.material_code) as material_name from history.price_list p
                left join dims.dim_material m on m.material_code = p.material_code order by p.price_list, p.material_code, p.valid_from""")
    accts = q("select price_list, account_code, account_name from dims.dim_account order by account_name")
    out: dict[str, dict] = {}
    for r in rows:
        pl = out.setdefault(r["price_list"], {"price_list": r["price_list"], "currency": r["currency"], "materials": {}, "accounts": [], "events": {}})
        pl["materials"].setdefault(r["material_code"], []).append(r)
    for a in accts:
        if a["price_list"] in out:
            out[a["price_list"]]["accounts"].append(a)
    for pl in out.values():
        mats = []
        for code, rs in pl["materials"].items():
            cur = rs[-1]
            prev = rs[-2] if len(rs) > 1 else None
            chg = None if prev is None or not prev["price_per_case"] else cur["price_per_case"] / prev["price_per_case"] - 1
            mats.append({"material_code": code, "material_name": cur["material_name"], "rows": rs, "current": cur, "prior": prev, "change": chg})
            for i, r in enumerate(rs):
                if r["price_event"]:
                    e = pl["events"].setdefault((r["price_event"], r["valid_from"]), {"event": r["price_event"], "effective": r["valid_from"], "n": 0, "chg": []})
                    e["n"] += 1
                    if i and rs[i - 1]["price_per_case"]:
                        e["chg"].append(r["price_per_case"] / rs[i - 1]["price_per_case"] - 1)
        pl["materials"] = mats
        pl["events"] = sorted(pl["events"].values(), key=lambda e: e["effective"])
        for e in pl["events"]:
            e["avg"] = sum(e["chg"]) / len(e["chg"]) if e["chg"] else None
    return list(out.values())


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


def is_material(node: str) -> bool:
    """A node of the material structure at which cases mean one thing: a standard material or one of its variants."""
    return one("select 1 as x from dims.dim_material where material_code = ? or standard_material = ? limit 1", node, node) is not None


def demand_tree(version_id: str, fy: int) -> dict:
    """The plan fiscal year by category → product → standard material in net sales — this view's total (closed periods as
    actuals, the rest plan), the prior fiscal year invoiced, the reference version where it has the year — with cases
    beside the money on the material rows only: a case means one thing at a material and nothing above it."""
    v = version(version_id) or {}
    ref_id = v.get("reference_version")
    cur = q("""select m.category_code, m.category_name, m.product_code, m.product_name, d.standard_material, m.material_name,
                      sum(d.net_sales) net_value, sum(d.cases) cases
               from plan.demand_review d join dims.dim_material m on m.material_code = d.standard_material
               where d.version_id = ? and d.fiscal_year = ? group by all""", version_id, fy)
    py = {r["standard_material"]: r for r in q("select standard_material, sum(net_sales) net_value, sum(cases) cases from history.shipments_period where fiscal_year = ? group by 1", fy - 1)}
    ref = {r["standard_material"]: r["net_value"] for r in q("select standard_material, sum(net_sales) net_value from plan.demand_financialised where version_id = ? and fiscal_year = ? group by 1", ref_id, fy)} if ref_id else {}
    for r in cur:
        r["value"] = r.pop("net_value")
        r["py"] = (py.get(r["standard_material"]) or {}).get("net_value") or 0.0; r["py_cases"] = (py.get(r["standard_material"]) or {}).get("cases") or 0.0
        r["ref"] = ref.get(r["standard_material"])
    def roll(rows: list[dict], key: str, label: str) -> list[dict]:
        out: dict[str, dict] = {}
        for r in rows:
            o = out.setdefault(r[key], {"code": r[key], "label": r[label], "value": 0.0, "py": 0.0, "ref": 0.0 if ref else None, "children": []})
            o["value"] += r["value"] or 0.0; o["py"] += r["py"]
            if ref: o["ref"] += r["ref"] or 0.0
            o["children"].append(r)
        return sorted(out.values(), key=lambda o: -o["value"])
    for r in cur:
        r["code"], r["label"] = r["standard_material"], r["material_name"]; r["children"] = []
    prods = roll(cur, "product_code", "product_name")
    for p in prods:
        p["category_code"] = p["children"][0]["category_code"]; p["category_name"] = p["children"][0]["category_name"]
        p["children"].sort(key=lambda m: -(m["value"] or 0.0))
    cats = roll(prods, "category_code", "category_name")
    total = {"value": sum(c["value"] for c in cats), "py": sum(c["py"] for c in cats), "ref": (sum(c["ref"] for c in cats) if ref else None)}
    return {"categories": cats, "total": total, "ref_id": ref_id, "fy": fy}


def _scope_sql(customer: str | None, material: str | None, acct_col: str, mat_col: str) -> tuple[str, list]:
    """A where-clause fragment restricting to a customer node and/or a material node through the hierarchy bridges."""
    sql, params = "", []
    if customer and customer != "ALL":
        sql += f" and {acct_col} in (select descendant_code from dims.dim_customer_hierarchy where ancestor_code = ? and descendant_level = 'account')"; params.append(customer)
    if material and material != "ALL":
        sql += f" and {mat_col} in (select descendant_code from dims.dim_material_hierarchy where ancestor_code = ? and descendant_is_leaf)"; params.append(material)
    return sql, params


def demand_series(version_id: str, fy: int, customer: str | None = None, material: str | None = None,
                  grain: str = "period", measure: str = "net_sales") -> dict:
    """The plan fiscal year at a node of either structure — this view (actual where closed, plan after), the reference
    version, the prior year's shipments — read as a rate per week. On a 4-4-5 calendar a five-week period is a quarter
    larger than a four-week one before anything in the business has moved, so a period total drawn as a series shows the
    calendar, not the trend. grain 'period': each period's total divided by its weeks (the prior year by its own weeks,
    so a 53-week year compares); grain 'week': the weeks themselves. measure 'net_sales' (history: what was invoiced; plan:
    the gross-to-net at the list and terms in force) or 'cases', which is meaningful only at a material — the caller
    decides where to offer it."""
    v = version(version_id) or {}
    ref_id = v.get("reference_version")
    val, tbl = ("cases", "plan.unconstrained_demand") if measure == "cases" else ("net_sales", "plan.demand_financialised")
    src = {r["period"]: r["source"] for r in q("select distinct period, source from plan.demand_review where version_id = ? and fiscal_year = ?", version_id, fy)}
    actual_p = sorted(p for p, s in src.items() if s == "actual"); plan_p = sorted(p for p, s in src.items() if s == "plan")
    def inlist(ps): return "(" + ",".join("?" * len(ps)) + ")" if ps else "(null)"
    w, wp = _scope_sql(customer, material, "account_code", "standard_material")
    if grain == "week":
        keys = [{"k": r["week_id"], "label": f"P{r['fiscal_period']}" if r["first"] else "", "period": r["period"], "weeks": 1, "boundary": bool(r["first"]),
                 "n": r["fiscal_week"], "say": f"{r['week_id']} · P{r['fiscal_period']} · w/c {r['week_start']:%d %b}"}
                for r in q("""select week_id, fiscal_week, period, fiscal_period, week_start, fiscal_week = min(fiscal_week) over (partition by period) as first
                              from dims.dim_week where fiscal_year = ? order by week_sequence""", fy)]
        col, pyk = "week_id", "fiscal_week"
        ws, wsp = _scope_sql(customer, material, "s.account_code", "m.standard_material")
        actual = q(f"select s.week_id k, sum(s.{val}) v from history.shipments s join dims.dim_material m on m.material_code = s.material_code where s.period in {inlist(actual_p)}{ws} group by 1",
                   *actual_p, *wsp) if actual_p else []
        py = q(f"select s.fiscal_week k, sum(s.{val}) v from history.shipments s join dims.dim_material m on m.material_code = s.material_code where s.fiscal_year = ?{ws} group by 1",
               fy - 1, *wsp)
        py_weeks: dict = {}
    else:
        keys = [{"k": r["period"], "label": f"P{r['fiscal_period']} · {r['weeks_in_period']}w", "period": r["period"], "weeks": r["weeks_in_period"], "boundary": False,
                 "n": r["fiscal_period"], "say": f"P{r['fiscal_period']} FY{fy} · {r['weeks_in_period']} weeks"}
                for r in q("select period, fiscal_period, weeks_in_period from dims.dim_period where fiscal_year = ? order by 1", fy)]
        col, pyk = "period", "fiscal_period"
        actual = q(f"select period k, sum({val}) v from history.shipments_period where period in {inlist(actual_p)}{w} group by 1", *actual_p, *wp) if actual_p else []
        py = q(f"select cast(substr(period, 6) as int) k, sum({val}) v from history.shipments_period where fiscal_year = ?{w} group by 1", fy - 1, *wp)
        py_weeks = {r["fiscal_period"]: r["weeks_in_period"] for r in q("select fiscal_period, weeks_in_period from dims.dim_period where fiscal_year = ?", fy - 1)}
    plan = q(f"select {col} k, sum({val}) v from {tbl} where version_id = ? and period in {inlist(plan_p)}{w} group by 1", version_id, *plan_p, *wp) if plan_p else []
    ref = q(f"select {col} k, sum({val}) v from {tbl} where version_id = ? and fiscal_year = ?{w} group by 1", ref_id, fy, *wp) if ref_id else []
    weeks = {k["k"]: k["weeks"] for k in keys}; by_n = {k["n"]: k["k"] for k in keys}
    def pt(total, wk, source=None): return {"rate": total / wk if wk else None, "total": total, "weeks": wk, "source": source}
    view = {r["k"]: pt(r["v"], weeks[r["k"]], "actual") for r in actual if r["k"] in weeks}
    view.update({r["k"]: pt(r["v"], weeks[r["k"]], "plan") for r in plan if r["k"] in weeks})
    return {"grain": grain, "measure": measure, "keys": keys, "unit": "cases / week" if measure == "cases" else "AUD net sales / week",
            "view": view, "ref": {r["k"]: pt(r["v"], weeks[r["k"]]) for r in ref if r["k"] in weeks},
            "py": {by_n[r["k"]]: pt(r["v"], py_weeks.get(r["k"], 1)) for r in py if r["k"] in by_n},
            "ref_id": ref_id, "total": sum(x["total"] for x in view.values()), "n_actual": len(actual_p)}


def node_label(dimension: str, node: str) -> str:
    if node == "ALL":
        return "All customers" if dimension == "customer" else "All materials"
    if dimension == "customer":
        r = one("select coalesce((select planning_unit_name from dims.dim_account where planning_unit = ? limit 1), (select account_name from dims.dim_account where account_code = ?), ?) as label", node, node, node)
    else:
        r = one("""select coalesce((select category_name from dims.dim_material where category_code = ? limit 1), (select product_name from dims.dim_material where product_code = ? limit 1),
                          (select material_name from dims.dim_material where material_code = ?), ?) as label""", node, node, node, node)
    return r["label"] if r else node


def node_path(dimension: str, node: str) -> list[dict]:
    """Root to node, each with its label — the breadcrumb of a drill."""
    table = "dims.dim_customer_hierarchy" if dimension == "customer" else "dims.dim_material_hierarchy"
    rows = q(f"select ancestor_code code, depth from {table} where descendant_code = ? order by depth desc", node)
    return [{"code": r["code"], "label": node_label(dimension, r["code"])} for r in rows]


def node_children(dimension: str, node: str) -> list[dict]:
    """The next level down in the structure: units under all, accounts under a unit; categories, products, materials."""
    table = "dims.dim_customer_hierarchy" if dimension == "customer" else "dims.dim_material_hierarchy"
    stop = "and descendant_level <> 'ship_to'" if dimension == "customer" else "and descendant_code <> ancestor_code"
    rows = q(f"select descendant_code code, descendant_level lvl from {table} where ancestor_code = ? and depth = 1 {stop} order by 1", node)
    return [{"code": r["code"], "level": r["lvl"], "label": node_label(dimension, r["code"])} for r in rows]


def revenue_fy(version_id: str, fy: int) -> dict | None:
    """Net sales this fiscal year against the reference, on the periods both versions value — the open view values only
    the periods ahead of it, so a whole-year figure would not be a like-for-like reading."""
    v = version(version_id) or {}
    r = one("""select min(g.period) p_from, max(g.period) p_to, sum(g.plan_net_sales) net_sales, sum(g.reference_net_sales) ref_net_sales
               from plan.gap_to_reference g join dims.dim_period p on p.period = g.period where g.version_id = ? and p.fiscal_year = ?""", version_id, fy)
    return {"net_sales": r["net_sales"] if r else None, "ref_net_sales": r["ref_net_sales"] if r else None, "ref_id": v.get("reference_version"),
            "p_from": r["p_from"] if r else None, "p_to": r["p_to"] if r else None}


def unit_status(version_id: str, fy: int) -> list[dict]:
    """One row per planning unit: its net sales this fiscal year against the prior year invoiced, and its submission state."""
    rows = q("""select u.code, u.unit_name, s.state, s.open_below, s.acted_by, s.acted_on,
                       (select sum(d.net_sales) from plan.demand_review d join dims.dim_account a on a.account_code = d.account_code
                         where d.version_id = ? and d.fiscal_year = ? and a.planning_unit = u.code) net_value,
                       (select sum(h.net_sales) from history.shipments_period h join dims.dim_account a on a.account_code = h.account_code
                         where h.fiscal_year = ? and a.planning_unit = u.code) py
                from (select distinct h.ancestor_code as code, a.planning_unit_name as unit_name from dims.dim_customer_hierarchy h
                      join dims.dim_account a on a.planning_unit = h.ancestor_code where h.ancestor_level = 'planning_unit') u
                left join plan.submission_state s on s.version_id = ? and s.subject = 'unit' and s.node = u.code
                order by net_value desc nulls last""", version_id, fy, fy - 1, version_id)
    for r in rows:
        r["value"] = r.pop("net_value")
    return rows


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


def accounts_under(node: str) -> set[str]:
    """The accounts at or beneath a node of the customer structure."""
    return {r["d"] for r in q("select descendant_code d from dims.dim_customer_hierarchy where ancestor_code = ? and descendant_level = 'account'", node)}


def unit_of_account(account: str) -> str | None:
    r = one("select planning_unit from dims.dim_account where account_code = ?", account)
    return r["planning_unit"] if r else None


def fiscal_years(version_id: str) -> list[int]:
    """The fiscal years a version carries, actual or plan."""
    return [r["fiscal_year"] for r in q("select distinct fiscal_year from plan.demand_review where version_id = ? order by 1", version_id)]


def like_for_like(series: dict) -> dict:
    """A series read against its reference on the points both value: the view's planned points that the reference also
    values. Closed points are what was invoiced, not a forecast, so they are left out — the same rule as revenue_fy, at
    any node and either grain. Also the year's invoiced to date, the view's whole year, the reference's whole year, and
    the prior year invoiced only when it covers every point (a year still closing is no year to grow against)."""
    view, ref, py = series["view"], series["ref"], series["py"]
    both = [k["k"] for k in series["keys"] if k["k"] in view and view[k["k"]]["source"] == "plan" and k["k"] in ref]
    lv = sum(view[k]["total"] for k in both); bp = sum(ref[k]["total"] for k in both)
    labels = {k["k"]: k for k in series["keys"]}
    return {"keys": both, "view": lv if both else None, "ref": bp if both else None, "gap": lv - bp if both else None,
            "from": labels[both[0]] if both else None, "to": labels[both[-1]] if both else None,
            "invoiced": sum(x["total"] for x in view.values() if x["source"] == "actual"),
            "year": series["total"], "ref_year": sum(x["total"] for x in ref.values()) if ref else None,
            "py_year": sum(x["total"] for x in py.values()) if py and len(py) == len(series["keys"]) else None,
            "py_part": 0 < len(py) < len(series["keys"])}


# ---- the statistical forecast: the run in force, where each account's baseline comes from, and where the two structures disagree ----

def forecast_runs(version_id: str) -> list[dict]:
    """The run in force for each account that has taken one in — a run can be in force for one account and waiting for another."""
    return q("select * from plan.forecast_run where version_id = ? and in_force order by account_code", version_id)


def reference_cases(version_id: str, account: str, first, last, materials: list[str]) -> float:
    """Our own calculation for one account's materials over a span of weeks — what a waiting run is read against."""
    r = one("""select sum(cases) c from plan.baseline_reference where version_id = ? and account_code = ? and week_start between ? and ?
               and list_contains(?, material_code)""", version_id, account, first, last, materials)
    return (r or {}).get("c") or 0.0


def forecast_sources(version_id: str) -> list[dict]:
    """One row per account: where its baseline is made, and — for the accounts the forecasting system sends — the run's
    cases beside our own calculation for the same series and weeks, and what stands on our calculation meanwhile."""
    return q("""with r as (select * from plan.forecast_run where version_id = ? and in_force),
                 b as (select account_code, sum(case when source = 'forecast_run' then cases end) landed,
                              sum(case when source in ('our_calculation_gap', 'our_calculation_kept') then cases end) gap,
                              sum(case when source = 'our_calculation_beyond_run' then cases end) beyond,
                              sum(case when source = 'calculated' then cases end) calculated
                       from plan.baseline_in_force where version_id = ? group by 1),
                 s as (select account_code, count(distinct material_code) series from plan.forecast_series where version_id = ? and state = 'in' group by 1),
                 o as (select f.account_code, sum(f.cases) ours from plan.baseline_reference f join r on r.account_code = f.account_code and f.week_start between r.first_week and r.last_day
                       join (select distinct material_code, account_code from plan.forecast_series where version_id = ? and state = 'in') x
                         on x.material_code = f.material_code and x.account_code = f.account_code
                       where f.version_id = ? group by 1)
                select a.account_code, a.account_name, a.baseline_source, s.series, b.landed, o.ours, b.landed / nullif(o.ours, 0) - 1 as departure,
                       b.gap, b.beyond, b.calculated, r.run_id, r.taken_in_by, r.taken_in_at
                from dims.dim_account a left join b using (account_code) left join s using (account_code) left join o using (account_code)
                left join r using (account_code)
                order by a.baseline_source, b.landed desc nulls last, b.calculated desc nulls last""", version_id, version_id, version_id, version_id, version_id)


def forecast_states(version_id: str, accounts: list[str]) -> list[dict]:
    return q("""select state, count(distinct sent_code || '|' || account_code) series, sum(cases) cases
                from plan.forecast_series where version_id = ? and list_contains(?, account_code) group by 1 order by 1""", version_id, accounts)


def forecast_queue() -> list[dict]:
    return q("select * from plan.worklist_forecast_queue order by kind desc, cases desc")


def forecast_resolutions(version_id: str) -> list[dict]:
    """Every resolution in force, with the cases it covers in the run in force (theirs) or on our calculation (ours)."""
    return q("""select r.*, case r.kind when 'theirs_not_ours'
                         then (select sum(s.cases) from plan.forecast_series s where s.version_id = ? and s.sent_code = r.item_code)
                         else (select sum(b.cases) from plan.baseline_reference b join plan.forecast_run fr on fr.version_id = b.version_id and fr.account_code = b.account_code and fr.in_force
                               where b.version_id = ? and b.material_code = r.item_code and b.account_code = r.account_code
                                 and b.week_start between fr.first_week and fr.last_day) end as cases,
                       coalesce((select any_value(s.sent_description) from plan.forecast_series s where s.sent_code = r.item_code),
                                (select material_name from dims.dim_material m where m.material_code = r.item_code)) as description
                from plan.forecast_resolution r order by r.acted_at desc""", version_id, version_id)


def forecast_departures(version_id: str, accounts: list[str], limit: int = 12) -> list[dict]:
    """Where the run departs most from our own calculation, by material × account over the run's weeks."""
    return q("""with r as (select * from plan.forecast_run where version_id = ? and in_force),
                 l as (select material_code, account_code, sum(cases) landed from plan.baseline_in_force where version_id = ? and source = 'forecast_run' group by all),
                 o as (select b.material_code, b.account_code, sum(b.cases) ours from plan.baseline_reference b join r on r.account_code = b.account_code and b.week_start between r.first_week and r.last_day
                       where b.version_id = ? group by all)
                select l.material_code, m.material_name, l.account_code, l.landed, o.ours, l.landed - coalesce(o.ours, 0) as diff, l.landed / nullif(o.ours, 0) - 1 as departure
                from l left join o using (material_code, account_code) join dims.dim_material m using (material_code)
                where list_contains(?, l.account_code)
                order by abs(l.landed - coalesce(o.ours, 0)) desc limit ?""", version_id, version_id, version_id, accounts, limit)


def forecast_series(version_id: str, material: str, account: str) -> list[dict]:
    """One series by period over the run's weeks: what the run says, our own calculation, and the same period last year as shipped."""
    return q("""with r as (select * from plan.forecast_run where version_id = ? and in_force and account_code = ?),
                 wk as (select w.week_id, w.period, w.fiscal_year, w.fiscal_period from dims.dim_week w join r on w.week_start between r.first_week and r.last_day),
                 l as (select w.period, sum(b.cases) landed from plan.baseline_in_force b join wk w using (week_id)
                       where b.version_id = ? and b.material_code = ? and b.account_code = ? and b.source = 'forecast_run' group by 1),
                 o as (select w.period, sum(b.cases) ours from plan.baseline_reference b join wk w using (week_id)
                       where b.version_id = ? and b.material_code = ? and b.account_code = ? group by 1),
                 h as (select fiscal_year, cast(substr(period, 6) as int) fiscal_period, sum(cases) shipped from history.shipments
                       where material_code = ? and account_code = ? group by all)
                select p.period, count(*) as "weeks", any_value(l.landed) as landed, any_value(o.ours) ours, any_value(l.landed) / nullif(any_value(o.ours), 0) - 1 as departure,
                       any_value(h.shipped) last_year
                from wk p left join l using (period) left join o using (period)
                left join h on h.fiscal_year = p.fiscal_year - 1 and h.fiscal_period = p.fiscal_period
                group by p.period order by p.period""", version_id, account, version_id, material, account, version_id, material, account, material, account)


def products() -> list[dict]:
    return q("select distinct product_code, product_name, category_name from dims.dim_material order by category_name, product_name")


def materials() -> list[dict]:
    return q("select material_code, material_name from dims.dim_material order by material_code")


# ---- Finance's plan and where each number comes from ----

def finance_reasons() -> list[dict]:
    return q("select * from plan.ref_overlay_reason order by reason_code")


def open_periods(version_id: str) -> list[str]:
    """The version's plan periods — after its last actual one, inside its horizon: where Finance may type. Asked of the
    version, not the calendar."""
    return version_periods(version_id)["plan"]


def finance_actuals(periods: list[str]) -> list[dict]:
    """What happened in the version's actual periods, at Finance's grain — account × material × period: the cases
    shipped and the net sales invoiced."""
    if not periods:
        return []
    return q(f"""select account_code, standard_material material_code, period, sum(cases) cases, sum(net_sales) net_sales
                 from history.shipments_period where period in ({','.join('?' * len(periods))}) group by all""", *periods)


def fy_periods(fy: int) -> list[dict]:
    return q("select period, fiscal_period, period_state from dims.dim_period where fiscal_year = ? order by period", fy)


def material_node(code: str) -> bool:
    return one("select 1 ok from dims.dim_material_hierarchy where ancestor_code = ? limit 1", code) is not None


def is_account(code: str) -> bool:
    return one("select 1 ok from dims.dim_account where account_code = ?", code) is not None


def material_tree_under(node: str) -> dict:
    """The material nodes beneath a node in one read: each child's label, level and whether it has children of its own."""
    rows = q("""with k as (select descendant_code code, descendant_level lvl from dims.dim_material_hierarchy where ancestor_code = ? and depth = 1 and descendant_code <> ancestor_code)
                select k.code, k.lvl, coalesce(c.category_name, p.product_name, m.material_name, k.code) as "label",
                       exists (select 1 from dims.dim_material_hierarchy h where h.ancestor_code = k.code and h.depth = 1 and h.descendant_code <> h.ancestor_code) has_kids
                from k left join (select distinct category_code, category_name from dims.dim_material) c on c.category_code = k.code
                left join (select distinct product_code, product_name from dims.dim_material) p on p.product_code = k.code
                left join dims.dim_material m on m.material_code = k.code order by k.code""", node)
    return {r["code"]: r for r in rows}


def customer_labels() -> dict:
    rows = q("""select planning_unit code, any_value(planning_unit_name) as "label" from dims.dim_account group by 1
                union all select account_code, account_name from dims.dim_account""")
    return {r["code"]: r["label"] for r in rows}


def finance_customer_nodes() -> list[dict]:
    """The customer nodes Finance types at: all, the units, the accounts — never a ship-to."""
    rows = q("""select h.descendant_code code, h.descendant_level lvl, h.depth, p.ancestor_code parent from dims.dim_customer_hierarchy h
                left join dims.dim_customer_hierarchy p on p.descendant_code = h.descendant_code and p.depth = 1
                where h.ancestor_code = 'ALL' and h.descendant_level <> 'ship_to' order by h.depth, h.descendant_code""")
    kids: dict = {}
    for r in rows:
        kids.setdefault(r["parent"], []).append(r)
    out: list[dict] = []
    names = customer_labels()
    def walk(r):                                          # the tree in order: each unit followed by its accounts
        out.append({**r, "label": "All customers" if r["code"] == "ALL" else names.get(r["code"], r["code"])})
        for k in kids.get(r["code"], []):
            walk(k)
    for r in kids.get(None, []):
        walk(r)
    return out


def finance_cells(version_id: str, fy: int, customer: str, nodes: list[str]) -> list[dict]:
    """Finance's plan summed to each node shown × period: the plan, the fed part, the demand plan beneath it, the built part."""
    marks = ",".join("?" * len(nodes))
    return q(f"""with sc as (select descendant_code a from dims.dim_customer_hierarchy where ancestor_code = ? and descendant_level = 'account'),
                     n as (select ancestor_code node, descendant_code mat from dims.dim_material_hierarchy
                           where descendant_level = 'material' and ancestor_code in ({marks}))
                 select n.node, f.period, count(*) n_cells, sum(f.cases) cases, sum(f.net_sales) net_sales,
                        sum(f.cases) filter (where f.source = 'fed') fed_cases, sum(f.net_sales) filter (where f.source = 'fed') fed_net_sales,
                        sum(f.source_cases) source_cases, sum(f.source_net_sales) source_net_sales,
                        count(*) filter (where f.source = 'built') n_built,
                        sum(f.cases) filter (where f.source = 'built') built_cases, sum(f.net_sales) filter (where f.source = 'built') built_net_sales
                 from plan.finance_plan f join sc on sc.a = f.account_code join n on n.mat = f.material_code
                 where f.version_id = ? and f.fiscal_year = ? group by all""", customer, *nodes, version_id, fy)


def finance_edits_at(version_id: str, periods: list[str], customer: str, nodes: list[str]) -> list[dict]:
    """The figures typed at this customer node on the nodes shown, in the periods shown, latest first."""
    if not periods or not nodes:
        return []
    marks, pm = ",".join("?" * len(nodes)), ",".join("?" * len(periods))
    return q(f"""select * from plan.finance_edit_reading where version_id = ? and period in ({pm}) and scope_customer = ?
                 and scope_material in ({marks}) order by entered_on desc, edit_id desc""", version_id, *periods, customer, *nodes)


def finance_saves(version_id: str) -> list[dict]:
    return q("""select save_id, min(entered_on) entered_on, any_value(entered_by) entered_by, any_value(reason_code) reason_code, any_value(reason) reason,
                       any_value(note) note, count(*) figures, count(*) filter (where standing = 'held') held,
                       count(*) filter (where standing = 'overwritten') overwritten, count(*) filter (where source_moved) moved,
                       count(*) filter (where standing like 'unplaced%') unplaced, bool_or(state = 'released') released,
                       string_agg(distinct scope_customer, ', ') customers, min(period) period_from, max(period) period_to
                from plan.finance_edit_reading where version_id = ? group by save_id order by min(entered_on) desc, save_id desc""", version_id)


def finance_save(save_id: str) -> dict | None:
    return one("select save_id, any_value(version_id) version_id, bool_or(state = 'released') released from plan.finance_edit where save_id = ? group by 1", save_id)


def finance_source_at(version_id: str, period: str, customer: str, material: str) -> dict:
    """The demand plan at a node now, fed cells only — what a figure typed there is read against."""
    return one("""select count(f.source_cases) n_fed, sum(f.source_cases) cases, sum(f.source_net_sales) / nullif(sum(f.source_cases), 0) price
                  from plan.finance_plan f
                  join dims.dim_customer_hierarchy c on c.ancestor_code = ? and c.descendant_level = 'account' and c.descendant_code = f.account_code
                  join dims.dim_material_hierarchy m on m.ancestor_code = ? and m.descendant_level = 'material' and m.descendant_code = f.material_code
                  where f.version_id = ? and f.period = ?""", customer, material, version_id, period) or {}


def finance_sources() -> list[dict]:
    return q("select * from plan.finance_source order by account_code, material_code = 'ALL' desc, material_code")


def finance_by_source(version_id: str, fy: int) -> list[dict]:
    return q("""select account_code, source, count(distinct material_code) materials, sum(cases) cases, sum(net_sales) net_sales, sum(source_net_sales) source_net_sales
                from plan.finance_plan where version_id = ? and fiscal_year = ? group by all order by account_code, source""", version_id, fy)


def account_materials(account: str) -> list[dict]:
    """What the account can be sold: the materials on its price list."""
    return q("""select distinct p.material_code code, m.material_name as "label" from history.price_list p join dims.dim_account a on a.price_list = p.price_list
                join dims.dim_material m on m.material_code = p.material_code where a.account_code = ? order by 1""", account)


def slots() -> list[dict]:
    return q("select * from plan.ref_plan_slot order by ord")


def grid_measures() -> list[dict]:
    """The measure register: every grid a person types into, its measures and the rules behind each, in order."""
    return q("select * from plan.ref_grid_measure order by grid, ord")


# ---- the structures as loaded: read here, maintained in the client's systems ----

def structure_loads() -> list[dict]:
    """Per structure: the system, the latest load and the one before, the members now, and how many are new, changed, gone."""
    return q("""with l as (select structure, any_value(structure_name) structure_name, any_value(source_system) source_system,
                              max(loaded_at) filter (where is_latest) latest, max(loaded_at) filter (where not is_latest) previous
                       from dims.structure_load group by 1),
                 c as (select structure, count(*) filter (where change = 'new') n_new, count(*) filter (where change = 'changed') n_changed,
                              count(*) filter (where change = 'gone') n_gone from dims.structure_change group by 1),
                 m as (select 'materials' structure, (select count(*) from dims.dim_material) members, 'materials' says
                       union all select 'customers', (select count(*) from dims.dim_account) + (select count(*) from dims.dim_ship_to),
                                        (select count(*) from dims.dim_account) || ' accounts, ' || (select count(*) from dims.dim_ship_to) || ' ship-tos'
                       union all select 'locations', (select count(*) from dims.dim_node), 'plants, warehouses and depots'
                       union all select 'lanes', (select count(*) from dims.ref_lane) + (select count(*) from dims.ref_route),
                                        (select count(*) from dims.ref_lane) || ' lanes, ' || (select count(*) from dims.ref_route) || ' routes')
                select l.*, m.members, m.says, coalesce(c.n_new, 0) n_new, coalesce(c.n_changed, 0) n_changed, coalesce(c.n_gone, 0) n_gone
                from l join m using (structure) left join c using (structure)
                order by case l.structure when 'materials' then 1 when 'customers' then 2 when 'locations' then 3 else 4 end""")


def structure_changes() -> list[dict]:
    return q("select * from dims.structure_change order by structure, case change when 'new' then 1 when 'changed' then 2 else 3 end, member_code")


def structure_unfit() -> list[dict]:
    return q("select * from plan.structure_unfit order by structure, lacks, member_code")


def provisional() -> list[dict]:
    """Members held in the plan ahead of the client's master: codes the forecasting system sent that a planner placed under one of our products."""
    return q("""select r.item_code, r.target_code, r.target_name, r.acted_by, r.acted_at, r.reason,
                       (select any_value(sent_description) from plan.forecast_series s where s.sent_code = r.item_code) description,
                       (select sum(cases) from plan.forecast_series s where s.sent_code = r.item_code) cases
                from plan.forecast_resolution r where r.resolution = 'place_under' order by r.acted_at desc""")
