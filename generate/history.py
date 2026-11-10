"""History: what Caldera shipped, by material × ship-to × week, and what it charged.

Demand history is shipments (the signal the baseline is fitted from, before any constraint the
plan later applies). Each material × ship-to has a base rate, a category trend, a seasonal shape,
promotion weeks and noise — all deterministic from the seed. Prices are per price list, dated,
with one increase event so the history has a step in it. Every shipment row also carries what it
invoiced — gross sales at list and net sales after the terms in force, the promotion's price
reduction and the history deduction rates — because history is revenue and units, from which price
is derived; the plan is units and a price, from which revenue is derived.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict

from .calendar import Week
from .structures import Material, ACCOUNTS, SHIP_TOS, account_ranges, CATEGORIES

TREND = {"declining": -0.045, "growing": 0.09, "flat": 0.005}          # per year, compounding


def _season(cat: str, fiscal_week: int) -> float:
    """Seasonal multiplier by fiscal week (week 1 = early July)."""
    x = 2 * math.pi * (fiscal_week - 1) / 52
    if cat == "CANNED_FRUIT":
        return 1.0 + 0.10 * math.cos(x)                 # winter uplift (July), summer trough
    if cat == "SNACK_CUPS":
        return 1.0 + 0.12 * math.cos(x - math.pi) + (0.10 if 27 <= fiscal_week <= 32 else 0.0)  # summer, back-to-school
    if cat == "TOMATOES":
        return 1.0 + 0.06 * math.cos(x)
    if cat == "BEANS_SPAG":
        return 1.0 + 0.08 * math.cos(x)
    if cat == "PASTA_SAUCE":
        return 1.0 + 0.07 * math.cos(x)                 # a winter lift, like tomatoes but more of it
    return 1.0 + 0.05 * math.cos(x - math.pi / 2)


def generate_demand(materials: list[Material], weeks: list[Week], rng: random.Random, first_fy: int) -> list[dict]:
    acct_of = {s[0]: s[1] for s in SHIP_TOS}
    weight = {s[0]: max(s[5], 60) for s in SHIP_TOS}
    rows: list[dict] = []
    for m in materials:
        eligible = [s for s in SHIP_TOS if account_ranges(acct_of[s[0]], m)]
        total_w = sum(weight[s[0]] for s in eligible) or 1
        trend = TREND[CATEGORIES[m.category_code][1]]
        # a promotion schedule per material: roughly every 8–12 weeks at the majors
        promo_weeks = set()
        wk = rng.randint(2, 9)
        while wk <= 53 * 4:
            promo_weeks.add(wk)
            wk += rng.randint(8, 12)
        for s in eligible:
            share = weight[s[0]] / total_w
            noise_sd = 0.12 if acct_of[s[0]] in ("WES", "CAR") else 0.22
            for w in weeks:
                years = (w.fiscal_year - first_fy) + (w.fiscal_week - 1) / 52
                lifecycle = 1.0
                if m.lifecycle_status == "launching":
                    lifecycle = 0.0                                               # not yet launched: the plan's layer 7 carries it
                if m.lifecycle_status == "delisting" and w.fiscal_year >= first_fy + 3:
                    lifecycle = max(0.0, 1.0 - 0.04 * w.fiscal_week)
                seq = (w.fiscal_year - first_fy) * 53 + w.fiscal_week
                promo = 1.0
                if seq in promo_weeks and acct_of[s[0]] in ("WES", "CAR", "MER"):
                    promo = 1.9
                elif (seq - 1) in promo_weeks and acct_of[s[0]] in ("WES", "CAR", "MER"):
                    promo = 0.85                                                  # post-promotion dip
                base = m.base_cases_per_week * share * ((1 + trend) ** years) * _season(m.category_code, w.fiscal_week)
                cases = base * lifecycle * promo * max(0.0, rng.gauss(1.0, noise_sd))
                cases = round(cases / 5) * 5
                if cases <= 0:
                    continue
                rows.append({"week_id": w.week_id, "period": w.period, "material_code": m.material_code,
                             "ship_to_code": s[0], "account_code": acct_of[s[0]], "cases": cases,
                             "tonnes": round(cases * m.case_net_kg / 1000, 4), "is_promo_week": "Y" if promo > 1.5 else "N"})
    return rows


# Price lists: list price per case by material, dated, with one increase event
PRICE_LISTS = ["PL_GROCERY", "PL_WHOLESALE", "PL_CONTRACT", "PL_FOODSERVICE", "PL_EXPORT"]
LIST_FACTOR = {"PL_GROCERY": 1.00, "PL_WHOLESALE": 1.04, "PL_CONTRACT": 0.82, "PL_FOODSERVICE": 0.96, "PL_EXPORT": 0.90}


# A legible list price per case: a per-kg price by category, scaled by tier and by format (a small can or a portion
# costs more a kilo than a 3 kg can), times the case's net weight.
PER_KG = {"CANNED_FRUIT": 5.2, "SNACK_CUPS": 9.8, "TOMATOES": 3.6, "BEANS_SPAG": 4.4, "SPREADS": 7.5, "PASTA_SAUCE": 6.4}
TIER_FACTOR = {"premium": 1.25, "mainstream": 1.0, "value": 0.78}
FORMAT_FACTOR = {"CAN_130": 1.35, "CAN_220": 1.20, "MP_4x220": 1.25, "MP_4x410": 1.04, "MP_4x400T": 1.04, "CAN_3KG": 0.72,
                 "CUP_6x120": 0.97, "CUP_12x120": 0.92, "CUP_FS_120": 0.88, "JAR_250": 1.20, "BTL_700": 0.85,
                 "PORT_FS": 1.60, "POUCH_2KG": 0.75, "CAN_800T": 0.92, "CAN_825": 0.95}


def list_base(m: Material) -> float:
    return round(PER_KG[m.category_code] * TIER_FACTOR[m.price_tier] * FORMAT_FACTOR.get(m.format_code, 1.0) * m.case_net_kg, 2)


def generate_prices(materials: list[Material], rng: random.Random) -> list[dict]:
    rows: list[dict] = []
    for m in materials:
        base = list_base(m)
        for pl in PRICE_LISTS:
            if pl == "PL_CONTRACT" and m.branded != "private_label":
                continue
            if pl not in ("PL_CONTRACT", "PL_GROCERY") and m.branded == "private_label":
                continue
            factor = LIST_FACTOR["PL_CONTRACT"] if m.branded == "private_label" else LIST_FACTOR[pl]   # private label is contract-priced on any list
            p0 = round(base * factor, 2)
            rows.append({"price_list": pl, "material_code": m.material_code, "currency": "AUD" if pl != "PL_EXPORT" else "USD",
                         "price_per_case": p0 if pl != "PL_EXPORT" else round(p0 * 0.66, 2), "valid_from": "2023-07-03", "valid_to": "2025-09-28", "event": ""})
            inc = 1.045 if pl != "PL_CONTRACT" else 1.025
            p1 = round(p0 * inc, 2)
            rows.append({"price_list": pl, "material_code": m.material_code, "currency": "AUD" if pl != "PL_EXPORT" else "USD",
                         "price_per_case": p1 if pl != "PL_EXPORT" else round(p1 * 0.66, 2), "valid_from": "2025-09-29", "valid_to": "", "event": "PI-2025-10 cost pass-through"})
    return rows


def value_shipments(shipments: list[dict], prices: list[dict], terms: list[dict], weeks: list[Week], rng: random.Random,
                    aud_usd: float = 0.66, returns_rate: float = 0.004, claims_rate: float = 0.003) -> None:
    """Give every shipment row its gross sales at list and its net sales, in AUD: the list in force on the account's
    price list that week; on a promotion week the list less a price reduction of a fifth and the scan funding at scan
    accounts; the account's standing discount on invoice; its off-invoice instruments, returns and claims as rates on
    the invoice; and a little realised-price noise, so the implied price (net ÷ cases) is near the list, never equal to
    it. History is what was invoiced — a fact — not the plan's machinery run backwards."""
    start_of = {w.week_id: w.week_start for w in weeks}
    pl_of = {a[0]: a[7] for a in ACCOUNTS}; scan = {a[0] for a in ACCOUNTS if a[11] == "Y"}
    windows: dict[tuple[str, str], list] = defaultdict(list)
    for r in prices:
        windows[(r["price_list"], r["material_code"])].append((r["valid_from"], r["valid_to"] or "9999-12-31", r["price_per_case"], r["currency"]))
    on_inv: dict[str, float] = defaultdict(float); off_inv: dict[str, float] = defaultdict(float)
    for t in terms:
        (on_inv if t["instrument_kind"] == "standing_discount" else off_inv)[t["account_code"]] += t["rate"]
    for r in shipments:
        d = start_of[r["week_id"]].isoformat()
        hit = next(((p, cur) for vf, vt, p, cur in windows.get((pl_of[r["account_code"]], r["material_code"]), []) if vf <= d <= vt), None)
        if hit is None:
            r["gross_sales"] = r["net_sales"] = None
            continue
        list_price = hit[0] / aud_usd if hit[1] == "USD" else hit[0]
        promo = r["is_promo_week"] == "Y"
        gross = r["cases"] * list_price
        invoice = gross * (1 - on_inv[r["account_code"]]) - (r["cases"] * list_price * 0.20 if promo else 0.0)
        net = invoice * (1 - off_inv[r["account_code"]] - returns_rate - claims_rate) - (r["cases"] * 1.50 if promo and r["account_code"] in scan else 0.0)
        r["gross_sales"] = round(gross, 2)
        r["net_sales"] = round(net * rng.gauss(1.0, 0.01), 2)


# What earlier cycles said: the latest view each IBP cycle produced, kept at the plan's grain for the periods it looked
# into. Forecast accuracy is read from these against shipments — the plan judged as a forecast at lag 1, 2 and 3 periods.
# Each category carries its own bias (declining categories are planned high, growing ones low: the usual story), and the
# error widens with the lag and with the account's noise. Deterministic from the seed, like everything else here.
CATEGORY_BIAS = {"CANNED_FRUIT": 0.055, "SNACK_CUPS": -0.06, "TOMATOES": 0.01, "BEANS_SPAG": 0.02, "SPREADS": -0.015,
                 "PASTA_SAUCE": -0.035}
LAG_SD = {1: 0.06, 2: 0.10, 3: 0.14}


def forecast_snapshots(shipments: list[dict], materials: list[Material], period_order: list[str], latest_closed: str,
                       rng: random.Random, months: int = 24) -> list[dict]:
    acct_sd = {s[1]: (0.5 if s[1] in ("WES", "CAR") else 1.0) for s in SHIP_TOS}
    cat_of = {m.material_code: m.category_code for m in materials}
    actual: dict[tuple[str, str, str], float] = defaultdict(float)
    for r in shipments:
        actual[(r["material_code"], r["account_code"], r["period"])] += r["cases"]
    idx = period_order.index(latest_closed)
    targets = period_order[idx - months + 1: idx + 1]
    rows: list[dict] = []
    for (mat, acct, per), cases in sorted(actual.items()):
        if per not in targets:
            continue
        p = period_order.index(per)
        for lag, sd in LAG_SD.items():
            cycle = period_order[p - lag]
            f = cases * (1 + CATEGORY_BIAS[cat_of[mat]] + rng.gauss(0.0, sd * acct_sd[acct]))
            rows.append({"forecast_version": f"LV-{cycle}", "cycle_period": cycle, "lag": lag, "period": per,
                         "material_code": mat, "account_code": acct, "cases": max(0, round(f / 5) * 5)})
    return rows
