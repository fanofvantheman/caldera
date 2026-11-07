"""The plan as entered: layer entries on a version, the promotions calendar, the terms register.

Nothing here is a plan total. A layer entry is one owner's contribution at the slice they chose —
a scope on each dimension, a time window, a value that is either cases or a rate on the baseline,
and the rule that spreads it to the storage grain. The models spread, sum and value; this file is
what the people typed.

Two versions carry entries. BP-FY2027 is the frozen business plan: its baseline was entered in June
as cases by material × account × period (run-rate × trend × a little optimism) and it does not move.
LV-2027P04 is the open latest view: its baseline is computed by the models from history at the
cycle; the people enter adjustments, listings, launches and exits over the top.
"""

from __future__ import annotations

from collections import defaultdict

from .calendar import Week, periods
from .structures import Material, ACCOUNTS, SHIP_TOS, account_ranges, CATEGORIES, PROMO_GROUPS

TREND = {"declining": -0.045, "growing": 0.09, "flat": 0.005}

REASON_CODES = {
    "MARKET_INTEL": "Market intelligence from the account team",
    "CATEGORY_DECLINE": "Category decline steeper than the fitted trend",
    "RANGE_REVIEW": "Range review outcome",
    "NEW_LISTING": "New listing with a ranging date",
    "DELISTING": "Listing withdrawn",
    "LAUNCH": "Launch volume typed in by marketing",
    "CANNIBALISATION": "Volume the launch takes from a neighbour",
    "EXIT_RUN_OUT": "Discontinuation run-out",
    "BUDGET": "Business plan contribution",
}


def _entry(version: str, layer: int, by: str, on: str, reason: str, effect: str,
           mat: str, cust: str, p_from: str, p_to: str, kind: str, value: float, spread: str, note: str = "") -> dict:
    return {"version_id": version, "layer_no": layer, "entered_by": by, "entered_on": on, "reason_code": reason,
            "effect_type": effect, "scope_material": mat, "scope_customer": cust, "period_from": p_from, "period_to": p_to,
            "value_kind": kind, "value": value, "spread_rule": spread, "note": note}


def business_plan_entries(materials: list[Material], shipments: list[dict], plan_fy: int) -> list[dict]:
    """BP-FY2027 layer 1: FY2026 run-rate by material × account × fiscal period, trended, +3% optimism."""
    by_cell: dict[tuple[str, str, int], float] = defaultdict(float)
    for r in shipments:
        fy, p = int(r["period"][:4]), int(r["period"][-2:])
        if fy == plan_fy - 1:
            by_cell[(r["material_code"], r["account_code"], p)] += r["cases"]
    trend = {m.material_code: TREND[CATEGORIES[m.category_code][1]] for m in materials}
    status = {m.material_code: m.lifecycle_status for m in materials}
    rows = []
    for (mat, acct, p), cases in sorted(by_cell.items()):
        if status[mat] == "delisting" and p >= 11:
            continue                                            # the budget planned the exit at P11
        value = round(cases * (1 + trend[mat]) * 1.03 / 10) * 10
        if value <= 0:
            continue
        rows.append(_entry(f"BP-FY{plan_fy}", 1, "demand.planner@caldera", "2026-06-10", "BUDGET", "primary",
                           mat, acct, f"{plan_fy}P{p:02d}", f"{plan_fy}P{p:02d}", "cases", value, "history_shape"))
    # the budget assumed the adult cups launch from P05 at the two majors; it has since slipped to P07
    for p in range(5, 13):
        for acct in ("WOW", "COL"):
            rows.append(_entry(f"BP-FY{plan_fy}", 7, "demand.planner@caldera", "2026-06-10", "LAUNCH", "primary",
                               "CUP_ADULT-CUP_2x170", acct, f"{plan_fy}P{p:02d}", f"{plan_fy}P{p:02d}", "cases",
                               min(1000 + 250 * (p - 5), 2500), "catchment", "AOP launch assumption"))
    return rows


def latest_view_entries(plan_fy: int, latest_closed: str) -> list[dict]:
    v = f"LV-{latest_closed}"
    dp, kam, pm = "demand.planner@caldera", "demand.planner@caldera", "demand.planner@caldera"
    on = "2026-11-03"
    fy1 = plan_fy + 1
    rows = [
        # layer 2 — judgement at the slice the planner chose; near horizon in cases, far horizon as rates
        _entry(v, 2, dp, on, "MARKET_INTEL", "primary", "SNACK_CUPS", "WOW", f"{plan_fy}P05", f"{plan_fy}P08", "rate_on_baseline", 0.06, "baseline_shape",
               "Account team expects the cups reset to hold through summer"),
        *[_entry(v, 2, dp, on, "CATEGORY_DECLINE", "primary", prod, "ALL", f"{plan_fy}P09", f"{fy1}P04", "rate_on_baseline", -0.03, "baseline_shape",
                 "Scan data shows the category falling faster than the fitted trend; the exiting and delisted lines are left to their own layers")
          for prod in ("PEACH_SL", "PEAR_HV", "PL_PEACH", "PL_PEAR")],
        _entry(v, 2, dp, on, "RANGE_REVIEW", "primary", "PG_REDGUM", "COL", f"{plan_fy}P06", f"{plan_fy}P06", "cases", 4000, "baseline_shape",
               "Pipeline fill for the Redgum shelf relay"),
        # layer 4 — distribution: one listing gained (no history, so catchment), one lost (a rate on what was there)
        *[_entry(v, 4, kam, on, "NEW_LISTING", "primary", "CUP_PEAR-CUP_4x120", "MET", f"{plan_fy}P{p:02d}", f"{plan_fy}P{p:02d}", "cases",
                 min(600 + 300 * (p - 6), 1500), "catchment", "Pear cups ranged at Metcash from P06") for p in range(6, 13)],
        *[_entry(v, 4, kam, on, "NEW_LISTING", "primary", "CUP_PEAR-CUP_4x120", "MET", f"{fy1}P{p:02d}", f"{fy1}P{p:02d}", "cases", 1500, "catchment")
          for p in range(1, 5)],
        _entry(v, 4, kam, on, "DELISTING", "primary", "FRUIT_SAL-CAN_825", "WOW", f"{plan_fy}P07", f"{fy1}P04", "rate_on_baseline", -1.0, "baseline_shape",
               "825 g fruit salad delisted at Woolworths from P07"),
        # layer 7 — innovation: the adult cups launch, typed in by marketing, now from P07; cannibalisation as its own line
        *[_entry(v, 7, pm, on, "LAUNCH", "primary", "CUP_ADULT-CUP_2x170", acct, f"{plan_fy}P{p:02d}", f"{plan_fy}P{p:02d}", "cases",
                 min(800 + 400 * (p - 7), 3000), "catchment", "Launch ramp, both majors") for p in range(7, 13) for acct in ("WOW", "COL")],
        *[_entry(v, 7, pm, on, "LAUNCH", "primary", "CUP_ADULT-CUP_2x170", acct, f"{fy1}P{p:02d}", f"{fy1}P{p:02d}", "cases", 3000, "catchment")
          for p in range(1, 5) for acct in ("WOW", "COL")],
        _entry(v, 7, pm, on, "CANNIBALISATION", "cannibalisation", "CUP_PEAR-CUP_4x120", "WOW", f"{plan_fy}P07", f"{fy1}P04", "rate_on_baseline", -0.05, "baseline_shape",
               "Adult cups take some pear-cup shoppers"),
        _entry(v, 7, pm, on, "CANNIBALISATION", "cannibalisation", "CUP_PEAR-CUP_4x120", "COL", f"{plan_fy}P07", f"{fy1}P04", "rate_on_baseline", -0.05, "baseline_shape"),
        # layer 8 — lifecycle exit: apricot halves run out over P08 and stop at P09
        _entry(v, 8, pm, on, "EXIT_RUN_OUT", "primary", "APRICOT_HV-CAN_410", "ALL", f"{plan_fy}P08", f"{plan_fy}P08", "rate_on_baseline", -0.5, "baseline_shape",
               "Run-out of remaining stock"),
        _entry(v, 8, pm, on, "EXIT_RUN_OUT", "primary", "APRICOT_HV-CAN_410", "ALL", f"{plan_fy}P09", f"{fy1}P04", "rate_on_baseline", -1.0, "baseline_shape"),
    ]
    return rows


def promo_events(weeks: list[Week], plan_fy: int, latest_closed: str, materials: list[Material]) -> list[dict]:
    """The promotions calendar for the open version: dated windows (retailer weeks start mid-week), a mechanic,
    an uplift assumption, the price reduction and funding per case, a fixed fee where there is a catalogue."""
    v = f"LV-{latest_closed}"
    per_kg = {"CANNED_FRUIT": 5.2, "SNACK_CUPS": 9.8, "TOMATOES": 3.6, "BEANS_SPAG": 4.4, "SPREADS": 7.5}
    mat = {m.material_code: m for m in materials}
    def avg_list(group: str) -> float:
        ms = [mat[c] for c in PROMO_GROUPS[group][1]]
        return sum(per_kg[m.category_code] * {"premium": 1.25, "mainstream": 1.0, "value": 0.78}[m.price_tier] * m.case_net_kg for m in ms) / len(ms)
    period_start = {p["period"]: p["period_start"] for p in periods(weeks)}
    plan = [  # (account, promo group, period, offset days into the period, length days, mechanic, uplift, tpr % of list, catalogue)
        ("WOW", "PG_VALLEY_410", f"{plan_fy}P05", 9, 14, "half_price", 1.10, 0.25, True),
        ("COL", "PG_CUPS_4PK",   f"{plan_fy}P06", 2, 7,  "price_cut",  0.60, 0.18, False),
        ("WOW", "PG_BEANS_SPAG", f"{plan_fy}P06", 16, 7, "multi_buy",  0.45, 0.12, False),
        ("COL", "PG_VALLEY_410", f"{plan_fy}P07", 9, 14, "half_price", 1.00, 0.25, True),
        ("MET", "PG_REDGUM",     f"{plan_fy}P08", 2, 14, "price_cut",  0.50, 0.15, True),
        ("WOW", "PG_CUPS_4PK",   f"{plan_fy}P08", 16, 7, "price_cut",  0.70, 0.18, False),
        ("COL", "PG_BEANS_SPAG", f"{plan_fy}P09", 9, 7,  "multi_buy",  0.45, 0.12, False),
        ("WOW", "PG_REDGUM",     f"{plan_fy}P10", 2, 14, "price_cut",  0.55, 0.15, True),
        ("WOW", "PG_VALLEY_410", f"{plan_fy}P11", 9, 14, "half_price", 1.10, 0.25, True),
        ("COL", "PG_CUPS_4PK",   f"{plan_fy}P12", 16, 7, "price_cut",  0.60, 0.18, False),
        ("COL", "PG_VALLEY_410", f"{plan_fy + 1}P02", 9, 14, "half_price", 1.00, 0.25, True),
        ("WOW", "PG_CUPS_4PK",   f"{plan_fy + 1}P03", 2, 7,  "price_cut",  0.70, 0.18, False),
    ]
    scan_accounts = {a[0] for a in ACCOUNTS if a[11] == "Y"}
    rows = []
    for i, (acct, grp, period, off, days, mech, uplift, tpr_pct, catalogue) in enumerate(plan, start=1):
        start = period_start[period].fromordinal(period_start[period].toordinal() + off)   # a Wednesday: retailer weeks start mid-week
        end = start.fromordinal(start.toordinal() + days - 1)
        rows.append({"event_id": f"EV-{plan_fy}-{i:03d}", "version_id": v, "account_code": acct, "promo_group_code": grp,
                     "window_start": start.isoformat(), "window_end": end.isoformat(), "mechanic": mech,
                     "uplift_pct": uplift, "dip_pct": 0.15, "tpr_per_case": round(avg_list(grp) * tpr_pct, 2),
                     "scan_funding_per_case": 1.50 if acct in scan_accounts else 0.0,
                     "fixed_fee": 15000.0 if catalogue else 0.0, "status": "agreed", "owner": "demand.planner@caldera",
                     "baseline_version": v})
    return rows


def terms_register() -> list[dict]:
    """Trading terms by account: each instrument with the attributes that decide its formula and where it lands.
    Flow position, driver basis, conditionality and settlement timing are independent; the band is presentation."""
    def t(acct, code, kind, basis, rate, flow, cond, timing, note=""):
        return {"account_code": acct, "instrument_code": f"{acct}-{code}", "instrument_kind": kind, "driver_basis": basis, "rate": rate,
                "flow_position": flow, "conditionality": cond, "settlement_timing": timing, "scope_material": "ALL",
                "valid_from": "2026-06-29", "valid_to": "", "note": note}
    rows = []
    for acct, *_ in ACCOUNTS:
        if acct in ("WOW", "COL"):
            rows += [t(acct, "RR", "retro_rebate", "pct_of_invoice", 0.025, "off_invoice", "unconditional", "quarterly"),
                     t(acct, "VR", "volume_rebate", "pct_of_invoice", 0.015, "off_invoice", "volume", "annual_retro", "accrual rate; tier reached is a true-up"),
                     t(acct, "WA", "warehouse_allowance", "pct_of_invoice", 0.010, "off_invoice", "unconditional", "in_period")]
        elif acct == "MET":
            rows += [t(acct, "SD", "standing_discount", "pct_of_list", 0.030, "on_invoice", "unconditional", "in_period"),
                     t(acct, "RR", "retro_rebate", "pct_of_invoice", 0.010, "off_invoice", "unconditional", "quarterly"),
                     t(acct, "ST", "settlement_discount", "pct_of_invoice", 0.015, "off_invoice", "payment", "in_period")]
        elif acct == "CST":
            rows += [t(acct, "SD", "standing_discount", "pct_of_list", 0.020, "on_invoice", "unconditional", "in_period")]
        elif acct == "BID":
            rows += [t(acct, "SD", "standing_discount", "pct_of_list", 0.040, "on_invoice", "unconditional", "in_period"),
                     t(acct, "RR", "retro_rebate", "pct_of_invoice", 0.010, "off_invoice", "unconditional", "quarterly")]
        # ALD: contract price, no instruments; EXPJ: FOB price, no instruments
    return rows
