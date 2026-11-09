"""History: what Caldera shipped, by material × ship-to × week, and what it charged.

Demand history is shipments (the signal the baseline is fitted from, before any constraint the
plan later applies). Each material × ship-to has a base rate, a category trend, a seasonal shape,
promotion weeks and noise — all deterministic from the seed. Prices are per price list, dated,
with one increase event so the history has a step in it.
"""

from __future__ import annotations

import math
import random

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


def generate_prices(materials: list[Material], rng: random.Random) -> list[dict]:
    rows: list[dict] = []
    for m in materials:
        # a legible per-kg price by category, tier and container
        per_kg = {"CANNED_FRUIT": 5.2, "SNACK_CUPS": 9.8, "TOMATOES": 3.6, "BEANS_SPAG": 4.4, "SPREADS": 7.5}[m.category_code]
        per_kg *= {"premium": 1.25, "mainstream": 1.0, "value": 0.78}[m.price_tier]
        base = round(per_kg * m.case_net_kg, 2)
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
