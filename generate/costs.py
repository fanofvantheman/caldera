"""Caldera's cost side: the legal entities, each one's ledger and its cost centres, the plan's own cost centres over them
(the mapping), the chart of accounts, and the actuals by entity × ledger cost centre × account × period.

Two entities. Caldera Foods keeps every function and the Echuca plant; Riverbend Fruit Co is the Loxton business, bought
at the start of FY2026 and still on its own ledger, with its cost centres numbered and cut its own way — one production
centre where Echuca has a hall each, sales split by state where Caldera has one. One chart of accounts: Riverbend was
moved onto Caldera's accounts at acquisition and kept its cost centres. Intercompany charges between the two are left
out. The plants stay one supply network; the entity is a dimension of the cost side, never a consolidation.

The plan's cost centres are the organisation's (`structures.COST_CENTRES`); the mapping carries each ledger cost centre
up to one of them, effective-dated. One of Riverbend's is left unmapped, so the queue has something true to show.

Actuals come from a declared driver and rate per ledger line — the plant's cases made, cases shipped, net sales, a flat
amount, or last year's amount carried forward — read off the shipments already generated, with noise from a random
stream of their own: nothing already generated moves. Labour accounts are a declared headcount × average cost per
ledger centre, with a casual pool in the campaign periods. Everything is invented; no figure is any real company's.
"""
from __future__ import annotations

import random
from collections import defaultdict

ENTITIES = [
    # code, name, ledger, state (payroll tax), joined (the fiscal period its ledger enters the plan), note
    ("CF",  "Caldera Foods",     "Caldera ledger",   "VIC", "2025P01", "every function, and the Echuca plant"),
    ("RBF", "Riverbend Fruit Co", "Riverbend ledger", "SA",  "2026P01", "the Loxton business, bought at the start of FY2026 and still on its own ledger"),
]

# entity, ledger cost centre, its name in the ledger, the plan's cost centre it maps to ('' = not mapped)
LEDGER_COST_CENTRES = [
    ("CF", "1100", "Echuca fruit hall",                 "CC_E_FRUIT"),
    ("CF", "1110", "Echuca tomato hall",                "CC_E_TOM"),
    ("CF", "1120", "Echuca beans and spaghetti",        "CC_E_BEANS"),
    ("CF", "1130", "Echuca spreads",                    "CC_E_SPRD"),
    ("CF", "1150", "Echuca engineering",                "CC_E_MAINT"),
    ("CF", "1160", "Echuca warehouse",                  "CC_E_WHSE"),
    ("CF", "1200", "Logistics",                         "CC_LOG"),
    ("CF", "1300", "Quality and technical",             "CC_QA"),
    ("CF", "2100", "Procurement and grower intake",     "CC_PROC"),
    ("CF", "2200", "Supply planning",                   "CC_PLAN"),
    ("CF", "3100", "Sales",                             "CC_SALES"),
    ("CF", "3200", "Marketing",                         "CC_MKT"),
    ("CF", "3300", "Trade marketing",                   "CC_TM"),
    ("CF", "4100", "Finance",                           "CC_FIN"),
    ("CF", "4200", "People and culture",                "CC_HR"),
    ("CF", "4300", "Information technology",            "CC_IT"),
    ("CF", "4400", "Executive office",                  "CC_EXEC"),
    ("RBF", "LX-PRD", "Production — fruit and cups",    "CC_L_PROD"),
    ("RBF", "LX-ENG", "Engineering",                    "CC_L_MAINT"),
    ("RBF", "LX-WHS", "Warehouse and dispatch",         "CC_L_WHSE"),
    ("RBF", "LX-QA",  "Quality",                        "CC_QA"),
    ("RBF", "LX-SSA", "Sales — South Australia",        "CC_SALES"),
    ("RBF", "LX-SWA", "Sales — Western Australia",      "CC_SALES"),
    ("RBF", "LX-ADM", "Administration",                 "CC_FIN"),
    ("RBF", "LX-ENV", "Environment and water licences", ""),          # left unmapped: the queue's item
]

# the one chart: account, name, cost family (for reading), labour
GL_ACCOUNTS = [
    ("6100", "Wages and salaries",            "labour",                   True),
    ("6150", "Labour on-costs",               "labour",                   True),
    ("6200", "Electricity",                   "energy",                   False),
    ("6210", "Gas and steam",                 "energy",                   False),
    ("6300", "Repairs and maintenance",       "maintenance",              False),
    ("6400", "Consumables and cleaning",      "maintenance",              False),
    ("6500", "Outbound freight",              "freight and warehousing",  False),
    ("6600", "Storage and handling",          "freight and warehousing",  False),
    ("6700", "Rent and leases",               "occupancy",                False),
    ("6720", "Insurance",                     "occupancy",                False),
    ("6800", "IT and software",               "other overhead",           False),
    ("6900", "Marketing and advertising",     "other overhead",           False),
    ("6950", "Travel",                        "other overhead",           False),
    ("6990", "Fees, licences and services",   "other overhead",           False),
]
ON_COST = 0.185            # super, payroll tax and workers' compensation over wages, in the actuals

# the drivers a line may declare (the schedule's list) — what each multiplies
DRIVERS = [
    # code, label, unit, what its plan quantity is
    ("cases_made_ech", "Cases made at Echuca", "cases",     "the demand plan's cases of the materials whose primary route is at Echuca"),
    ("cases_made_lox", "Cases made at Loxton", "cases",     "the demand plan's cases of the materials whose primary route is at Loxton"),
    ("cases_shipped",  "Cases shipped",        "cases",     "the demand plan's cases"),
    ("net_sales",      "Net sales",            "$",         "the demand plan valued through the gross-to-net"),
    ("none",           "None — a flat amount", "period",    "one per period: the rate is the amount"),
    ("last_year",      "Last year",            "$",         "the same period's actual a year earlier; the rate is the index on it"),
]

# a ledger line's actuals: entity, ledger cost centre, account, driver, rate (per unit of driver; per period for none;
# for last_year the FY2025 base per period, carried forward at 3% a year)
_HALLS = {"1100": (0.05, 0.08, 0.060), "1110": (0.10, 0.12, 0.050), "1120": (0.06, 0.10, 0.050), "1130": (0.04, 0.03, 0.040)}
COST_LINES = [
    *[("CF", cc, acct, "cases_made_ech", r) for cc, rs in _HALLS.items() for acct, r in zip(("6200", "6210", "6400"), rs)],
    ("RBF", "LX-PRD", "6200", "cases_made_lox", 0.20), ("RBF", "LX-PRD", "6210", "cases_made_lox", 0.18), ("RBF", "LX-PRD", "6400", "cases_made_lox", 0.10),
    ("CF", "1150", "6300", "none", 180_000), ("CF", "1150", "6400", "none", 25_000),
    ("RBF", "LX-ENG", "6300", "none", 110_000), ("RBF", "LX-ENG", "6400", "none", 15_000),
    ("CF", "1160", "6200", "none", 30_000), ("CF", "1160", "6600", "cases_made_ech", 0.10),
    ("RBF", "LX-WHS", "6200", "none", 20_000), ("RBF", "LX-WHS", "6600", "cases_made_lox", 0.11),
    ("CF", "1200", "6500", "cases_shipped", 0.85), ("CF", "1200", "6600", "cases_shipped", 0.55),
    ("CF", "1300", "6990", "last_year", 25_000), ("RBF", "LX-QA", "6990", "last_year", 10_000),
    ("CF", "2100", "6950", "last_year", 10_000), ("CF", "2200", "6800", "none", 12_000),
    ("CF", "3100", "6950", "last_year", 30_000), ("RBF", "LX-SSA", "6950", "last_year", 6_000), ("RBF", "LX-SWA", "6950", "last_year", 5_000),
    ("CF", "3200", "6900", "net_sales", 0.018), ("CF", "3300", "6900", "net_sales", 0.004),
    ("CF", "4100", "6990", "last_year", 45_000), ("CF", "4100", "6720", "none", 70_000),
    ("CF", "4200", "6990", "last_year", 20_000), ("CF", "4300", "6800", "none", 140_000),
    ("CF", "4400", "6700", "none", 95_000), ("CF", "4400", "6950", "last_year", 15_000), ("CF", "4400", "6990", "last_year", 30_000),
    ("RBF", "LX-ADM", "6700", "none", 20_000), ("RBF", "LX-ADM", "6990", "last_year", 8_000),
    ("RBF", "LX-ENV", "6990", "none", 18_000),
]

# labour in the actuals: ledger cost centre → (FTE, average annual cost in FY2026); a casual pool in the campaign periods
LABOUR = {
    "1100": (55, 72_000), "1110": (70, 71_000), "1120": (45, 70_000), "1130": (25, 69_000), "1150": (30, 95_000), "1160": (20, 68_000),
    "1200": (8, 90_000), "1300": (14, 85_000), "2100": (6, 110_000), "2200": (5, 115_000), "3100": (12, 140_000), "3200": (7, 125_000),
    "3300": (5, 120_000), "4100": (10, 120_000), "4200": (4, 110_000), "4300": (6, 125_000), "4400": (3, 380_000),
    "LX-PRD": (80, 70_000), "LX-ENG": (18, 92_000), "LX-WHS": (12, 66_000), "LX-QA": (6, 82_000), "LX-SSA": (2, 130_000),
    "LX-SWA": (1, 125_000), "LX-ADM": (4, 100_000), "LX-ENV": (1, 95_000),
}
CAMPAIGN_HALLS = {"1100": 0.35, "1110": 0.40, "LX-PRD": 0.40}         # casual pool over the base, P07–P10
CAMPAIGN = (7, 10)
WAGE_STEP = 0.035                                                     # the agreement's increase each 1 July


def plant_of(routes: list[dict]) -> dict[str, str]:
    return {r["material_code"]: r["plant_code"] for r in routes if r["is_primary"] == "Y"}


def driver_actuals(shipments: list[dict], routes: list[dict]) -> dict[tuple[str, str], float]:
    """(driver, period) → the quantity the actuals were made from: cases made at each plant (cases shipped of the
    materials whose primary route is there — Caldera has no production history; shipments stand in), cases shipped,
    net sales."""
    plant = plant_of(routes)
    out: dict[tuple[str, str], float] = defaultdict(float)
    for s in shipments:
        p, c = s["period"], float(s["cases"])
        out[("cases_shipped", p)] += c
        out[("net_sales", p)] += float(s["net_sales"])
        pl = plant.get(s["material_code"])
        if pl:
            out[(f"cases_made_{pl.lower()}", p)] += c
    return out


def cost_actuals(shipments: list[dict], routes: list[dict], periods: list[dict], latest_closed: str, seed: int) -> list[dict]:
    """The ledgers' actuals: entity × ledger cost centre × account × period, from each entity's first period to the last
    closed one. A stream of its own, drawn in a fixed order."""
    rng = random.Random(seed * 7 + 6_100)
    drv = driver_actuals(shipments, routes)
    joined = {e[0]: e[4] for e in ENTITIES}
    entity_of = {cc: e for e, cc, _, _ in LEDGER_COST_CENTRES}
    rows = []
    for p in periods:
        per, fy, fp, wk = p["period"], int(p["fiscal_year"]), int(p["fiscal_period"]), int(p["weeks"])
        if per > latest_closed:
            break
        for ent, cc, acct, driver, rate in COST_LINES:
            if per < joined[ent]:
                continue
            if driver == "none":
                amt = rate * rng.uniform(0.93, 1.07)
            elif driver == "last_year":
                amt = rate * (1.03 ** (fy - 2025)) * (wk / 4.33) * rng.uniform(0.85, 1.15)
            else:
                amt = drv.get((driver, per), 0.0) * rate * rng.uniform(0.95, 1.05)
            rows.append({"entity_code": ent, "ledger_cost_centre": cc, "account_code": acct, "period": per, "amount": round(amt, 2)})
        for cc, (fte, avg) in LABOUR.items():
            ent = entity_of[cc]
            if per < joined[ent]:
                continue
            casual = CAMPAIGN_HALLS.get(cc, 0.0) if CAMPAIGN[0] <= fp <= CAMPAIGN[1] else 0.0
            wages = fte * (1 + casual) * avg * (1 + WAGE_STEP) ** (fy - 2026) / 52 * wk * rng.uniform(0.98, 1.02)
            rows.append({"entity_code": ent, "ledger_cost_centre": cc, "account_code": "6100", "period": per, "amount": round(wages, 2)})
            rows.append({"entity_code": ent, "ledger_cost_centre": cc, "account_code": "6150", "period": per, "amount": round(wages * ON_COST, 2)})
    return rows


def reference(periods: list[dict]) -> dict[str, list[dict]]:
    start = {p["period"]: p["period_start"] for p in periods}
    return {
        "dim_entity": [{"entity_code": e[0], "entity_name": e[1], "ledger": e[2], "state": e[3], "joined_period": e[4],
                        "joined_on": str(start[e[4]]), "note": e[5]} for e in ENTITIES],
        "dim_ledger_cost_centre": [{"entity_code": e, "ledger_cost_centre": cc, "ledger_name": n} for e, cc, n, _ in LEDGER_COST_CENTRES],
        # the mapping as loaded: one row per ledger cost centre mapped, from the entity's first period; LX-ENV has none
        "reg_cost_centre_map": [{"entity_code": e, "ledger_cost_centre": cc, "cost_centre_code": to, "valid_from": str(start[dict((x[0], x[4]) for x in ENTITIES)[e]]),
                                 "valid_to": "", "mapped_by": "finance.manager@caldera", "note": ""}
                                for e, cc, _, to in LEDGER_COST_CENTRES if to],
        "dim_gl_account": [{"account_code": a, "account_name": n, "cost_family": f, "is_labour": "Y" if lab else "N"} for a, n, f, lab in GL_ACCOUNTS],
        "ref_cost_driver": [{"driver": d, "driver_label": l, "unit": u, "says": s, "ord": i} for i, (d, l, u, s) in enumerate(DRIVERS, start=1)],
    }


# ---- the schedule as Finance left it at onboarding, and what has been typed since --------------------------------------
SCHEDULE_COLUMNS = ["edit_id", "save_id", "version_id", "entity_code", "cost_centre_code", "account_code", "action", "period", "value", "driver",
                    "calc_at_entry", "reason_code", "note", "entered_by", "entered_on", "withdraws"]


def schedule_edits(version: str, actuals: list[dict], window: list[str]) -> list[dict]:
    """Each line's driver as its history follows it (declared by Finance when the schedule was set up); then three things
    typed since: a rate on Loxton production's electricity for the energy contract signed in October, a boiler overhaul at
    Echuca in P08, and the Christmas campaign in P06 — typed on 2 November against a calculated amount the demand plan has
    since moved, so it is marked. The overhaul was typed against the calculated amount then, which nothing has moved:
    a flat line's year ÷ 12 over the window."""
    to = {(e, cc): p for e, cc, _, p in LEDGER_COST_CENTRES if p}
    lines: dict[tuple, str] = {}
    for ent, cc, acct, driver, _ in COST_LINES:
        if (ent, cc) in to:
            lines.setdefault((ent, to[(ent, cc)], acct), driver)
    rows, fin = [], "finance.manager@caldera"
    def row(i, save, ent, cc, acct, action, on, period="", value="", driver="", calc="", reason="METHOD", note="", by=fin):
        rows.append({"edit_id": f"SE-{save[3:]}-{i:03d}", "save_id": save, "version_id": version, "entity_code": ent, "cost_centre_code": cc,
                     "account_code": acct, "action": action, "period": period, "value": value, "driver": driver, "calc_at_entry": calc,
                     "reason_code": reason, "note": note, "entered_by": by, "entered_on": on, "withdraws": ""})
    for i, ((ent, cc, acct), d) in enumerate(sorted(lines.items()), start=1):
        row(i, "SS-20261102-0900", ent, cc, acct, "driver", "2026-11-02T09:00:00", driver=d, note="the driver its history follows")
    row(1, "SS-20261102-1015", "CF", "CC_MKT", "6900", "month", "2026-11-02T10:15:00", period="2027P06", value=750000.0, calc=552000.0,
        reason="TIMING", note="the Christmas campaign lands in one period")
    row(1, "SS-20261105-1400", "RBF", "CC_L_PROD", "6200", "rate", "2026-11-05T14:00:00", value=0.23, reason="CONTRACT",
        note="energy contract from 1 January: 23 cents a case made")
    row(1, "SS-20261106-1100", "CF", "CC_E_MAINT", "6300", "month", "2026-11-06T11:00:00", period="2027P08", value=320000.0,
        calc=sum(a["amount"] for a in actuals if (a["entity_code"], a["ledger_cost_centre"], a["account_code"]) == ("CF", "1150", "6300") and a["period"] in window) / len(window),
        reason="ONE_OFF", note="boiler overhaul in the shutdown", by="plant.manager@caldera")
    return rows


# ---- labour: two models (DEC-20261113-02) — by role in the factory cost centres, by name in the overhead ones ----------
# each entity's agreement: classification → (name, hourly rate before the increase); the increase from the period that
# holds 1 January 2027. Riverbend kept its own agreement, about 3% below Caldera's.
AGREEMENTS = {"CF": ("CFPA-2025", "Caldera Food Processing Agreement 2025", 1.00), "RBF": ("RBF-2024", "Riverbend Fruit Agreement 2024", 0.97)}
CLASSIFICATIONS = [
    ("PO1", "Process operator grade 1", 34.50), ("PO2", "Process operator grade 2", 37.00), ("PO3", "Leading hand", 40.50),
    ("TT", "Trades technician", 47.50), ("ST", "Storeperson", 34.00), ("LT", "Laboratory technician", 42.50), ("LOG", "Logistics coordinator", 44.00),
]
AGREEMENT_STEP, STEP_PERIOD, CASUAL_LOADING, HOURS = 0.035, "2027P07", 0.25, 38.0

# The kinds of entitlement the labour model has a calculation for — closed: an entitlement is a row under one of these,
# and a clause that fits none is an item to resolve, never forced into one (DEC-20261114-03). `priced`: the labour model
# reads it today.
ENTITLEMENT_KINDS = [
    ("base_rate", "Base rate", "a rate per hour by classification", "paid hours × the rate", True),
    ("loading", "Loading", "a share on the base rate, for hours of a pattern (casual, afternoon shift, night, weekend)", "the hours of the pattern × the base rate × the share", True),
    ("allowance", "Allowance", "an amount per shift, week or occurrence", "the count × the amount", False),
    ("leave_accrual", "Leave accrual and loading", "hours of leave accrued per hour or year worked, and the loading paid on leave", "the accrual × the rate in force, and the loading on leave taken", False),
    ("on_cost", "On-cost", "a share paid on top of wages (superannuation, payroll tax, workers' compensation)", "wages × the share", True),
    ("dated_increase", "Dated increase", "a share by which every base rate rises from a period", "each base rate × (1 + the share), to the cent, from the period", True),
    ("one_off", "One-off payment", "an amount paid once, at a date", "the amount in the period it falls", False),
]
ENTITLEMENT_COLUMNS = ["entitlement_id", "layer", "instrument", "instrument_name", "entity_code", "jurisdiction", "kind", "classification",
                       "classification_name", "applies_to", "value", "valid_from_period", "clause_ref", "clause", "specimen", "entered_by", "entered_on"]


def entitlement_kinds() -> list[dict]:
    return [{"kind": k, "kind_label": l, "what": w, "calculates": c, "priced": "Y" if p else "N", "ord": i}
            for i, (k, l, w, c, p) in enumerate(ENTITLEMENT_KINDS, start=1)]


# The statutory floor for the jurisdictions Caldera's plants are in — a SPECIMEN awaiting sources: no statute or official
# rate table is inside the boundary, so no figure is drafted. Each row says what it is and the source it is to be drafted
# from; its value is empty until the set is drafted from that source, dated and accepted (DEC-20261114-03 point 5).
STATUTORY = [
    # jurisdiction, kind, applies to, what, the source it is to be drafted from
    ("AU", "on_cost", "super", "Superannuation guarantee, a share of ordinary time earnings", "Superannuation Guarantee (Administration) Act 1992 and the rate in force for the year"),
    ("AU", "base_rate", "minimum", "The national minimum wage, per hour", "the national minimum wage order of the annual wage review"),
    ("AU", "leave_accrual", "annual", "Annual leave accrued per ordinary hour worked, and any loading", "Fair Work Act 2009, National Employment Standards (annual leave)"),
    ("AU", "leave_accrual", "personal", "Personal / carer's leave accrued per ordinary hour worked", "Fair Work Act 2009, National Employment Standards (personal / carer's leave)"),
    ("VIC", "on_cost", "payroll_tax", "Payroll tax, a share of wages above the threshold", "Payroll Tax Act 2007 (Vic) and the rate and threshold in force"),
    ("VIC", "on_cost", "workers_comp", "Workers' compensation premium, a share of wages", "the Victorian scheme's premium order for the year and the employer's industry rate"),
    ("SA", "on_cost", "payroll_tax", "Payroll tax, a share of wages above the threshold", "Payroll Tax Act 2009 (SA) and the rate and threshold in force"),
    ("SA", "on_cost", "workers_comp", "Workers' compensation premium, a share of wages", "the South Australian scheme's premium determination and the employer's industry rate"),
]
JURISDICTION_NAME = {"AU": "Commonwealth", "VIC": "Victoria", "SA": "South Australia"}


def statutory_specimen() -> list[dict]:
    return [{"entitlement_id": f"ST-{j}-{i:03d}", "layer": "statute", "instrument": f"STATUTE-{j}", "instrument_name": f"Statutory floor · {JURISDICTION_NAME[j]}",
             "entity_code": "", "jurisdiction": j, "kind": k, "classification": "", "classification_name": "", "applies_to": a, "value": "",
             "valid_from_period": "2025P01", "clause_ref": f"to be drafted from {src}", "clause": f"Specimen — {what}; no source given, nothing drafted.",
             "specimen": "Y", "entered_by": "", "entered_on": ""} for i, (j, k, a, what, src) in enumerate(STATUTORY, start=1)]


def entitlements() -> list[dict]:
    """Each entity's agreement as rows under the kinds, each with the clause it came from: a base rate per classification
    (the rates schedule), the increase from January 2027, and the casual loading. Riverbend's rates sit about 3% under
    Caldera's; the increase is on the schedule's rates, to the cent."""
    rows, by = [], "people@caldera"
    for e, (a, n, f) in AGREEMENTS.items():
        def row(kind, value, clause_ref, clause, classification="", cname="", applies="", vp="2025P01"):
            rows.append({"entitlement_id": f"EN-{a}-{len(rows) + 1:03d}", "layer": "agreement", "instrument": a, "instrument_name": n, "entity_code": e,
                         "jurisdiction": "", "kind": kind, "classification": classification, "classification_name": cname, "applies_to": applies,
                         "value": value, "valid_from_period": vp, "clause_ref": clause_ref, "clause": clause, "specimen": "N",
                         "entered_by": by, "entered_on": "2026-07-01T09:00:00"})
        for i, (c, cn, r) in enumerate(CLASSIFICATIONS, start=1):
            row("base_rate", round(r * f, 2), f"Schedule A, item {i}", f"{cn}: ${round(r * f, 2):.2f} per ordinary hour.", c, cn)
        row("dated_increase", AGREEMENT_STEP, "cl. 12.2", "Rates in Schedule A increase by 3.5% from the first full pay period commencing on or after 1 January 2027.",
            vp=STEP_PERIOD)
        row("loading", CASUAL_LOADING, "cl. 10.3", "A casual employee is paid the ordinary hourly rate for their classification plus a casual loading of 25%.",
            applies="casual")
    return rows
ON_COSTS = {"CF": {"super": 0.12, "payroll_tax": 0.0485, "workers_comp": 0.025}, "RBF": {"super": 0.12, "payroll_tax": 0.0495, "workers_comp": 0.025}}
# the mix of classifications by the kind of factory centre, from the ledger centre's headcount
MIX = {"hall": [("PO1", 0.55), ("PO2", 0.27), ("PO3", 0.10), ("TT", 0.08)], "maint": [("TT", 0.8), ("PO2", 0.2)],
       "whse": [("ST", 0.85), ("PO3", 0.15)], "qa": [("LT", 0.85), ("PO3", 0.15)], "log": [("LOG", 1.0)]}
KIND_OF = {"1100": "hall", "1110": "hall", "1120": "hall", "1130": "hall", "LX-PRD": "hall", "1150": "maint", "LX-ENG": "maint",
           "1160": "whse", "LX-WHS": "whse", "1300": "qa", "LX-QA": "qa", "1200": "log"}
FIRST = ["Aisha", "Ben", "Chloe", "Dev", "Elena", "Finn", "Grace", "Hamish", "Ines", "Jack", "Keira", "Liam", "Mei", "Noah", "Olive", "Priya",
         "Quinn", "Rosa", "Sam", "Tara", "Umar", "Vera", "Will", "Xin", "Yasmin", "Zac"]
LAST = ["Abbott", "Barlow", "Castellan", "Dunmore", "Ellery", "Fairweather", "Galloway", "Hartigan", "Ivers", "Jardine", "Kellaway", "Lindqvist",
        "Marchetti", "Northey", "Okafor", "Pemberton", "Quarrie", "Rennick", "Sallis", "Tregear", "Underhill", "Varga", "Whitlam", "Yeoh"]
TITLES = {"CC_PROC": ("Head of procurement", "Grower liaison officer"), "CC_PLAN": ("Supply planning manager", "Supply planner"),
          "CC_SALES": ("National sales manager", "Key account manager"), "CC_MKT": ("Marketing director", "Brand manager"),
          "CC_TM": ("Trade marketing manager", "Trade marketing analyst"), "CC_FIN": ("Finance manager", "Financial analyst"),
          "CC_HR": ("People and culture manager", "People partner"), "CC_IT": ("IT manager", "Systems analyst"),
          "CC_EXEC": ("Managing director", "General manager")}


def labour_registers(periods: list[dict]) -> dict[str, list[dict]]:
    """The agreements, the positions (role-based) and the people (name-based), from each ledger centre's headcount in the
    actuals; deterministic, drawing nothing."""
    start = {p["period"]: p["period_start"] for p in periods}
    to = {(e, cc): p for e, cc, _, p in LEDGER_COST_CENTRES if p}
    entity_of = {cc: e for e, cc, _, _ in LEDGER_COST_CENTRES}
    agreement = entitlements() + statutory_specimen()
    on_cost = [{"entity_code": e, "component": k, "rate": v} for e, comps in ON_COSTS.items() for k, v in comps.items()]
    positions, people = [], []
    n = 0
    for cc, kind in KIND_OF.items():
        ent = entity_of[cc]; plan_cc = to[(ent, cc)]; fte = LABOUR[cc][0]
        for cls, share in MIX[kind]:
            n += 1
            positions.append({"position_id": f"POS-{n:03d}", "entity_code": ent, "cost_centre_code": plan_cc, "agreement": AGREEMENTS[ent][0],
                              "classification": cls, "employment_type": "permanent", "fte": round(fte * share, 1), "hours_per_week": HOURS,
                              "from_period": "2025P01", "to_period": "", "shown_name": ""})
        if cc in CAMPAIGN_HALLS:
            for fy in (2027, 2028):
                n += 1
                positions.append({"position_id": f"POS-{n:03d}", "entity_code": ent, "cost_centre_code": plan_cc, "agreement": AGREEMENTS[ent][0],
                                  "classification": "PO1", "employment_type": "casual", "fte": round(fte * CAMPAIGN_HALLS[cc], 1), "hours_per_week": HOURS,
                                  "from_period": f"{fy}P{CAMPAIGN[0]:02d}", "to_period": f"{fy}P{CAMPAIGN[1]:02d}", "shown_name": "campaign casual pool"})
    positions[0]["shown_name"] = "Rosa Marchetti (shown; carries nothing)"
    i = 0
    for cc, (fte, avg) in LABOUR.items():
        if cc in KIND_OF or cc == "LX-ENV":
            continue
        ent = entity_of[cc]; plan_cc = to[(ent, cc)]
        head, staff = TITLES.get(plan_cc, ("Manager", "Officer"))
        for k in range(fte):
            i += 1
            lead = k == 0 and ent == "CF"
            incentive = 0.30 if plan_cc == "CC_EXEC" else (0.15 if lead else 0.05)
            pay = avg * (1.6 if lead and plan_cc != "CC_EXEC" else 1.0) * (0.92 + 0.04 * (i % 5)) / (1 + incentive) * (1 + WAGE_STEP)
            people.append({"person_id": f"PER-{i:03d}", "entity_code": ent, "cost_centre_code": plan_cc,
                           "name": f"{FIRST[(i * 7) % len(FIRST)]} {LAST[(i * 5) % len(LAST)]}", "title": head if lead else staff,
                           "annual_salary": round(pay, -2), "incentive_pct": incentive, "start_date": "2019-07-01", "end_date": "", "vacancy": "N"})
    # one leaver and one starter in the horizon, and a named vacancy at a typed figure
    people[3]["end_date"] = str(start["2027P09"] - __import__("datetime").timedelta(days=1))
    i += 1
    people.append({"person_id": f"PER-{i:03d}", "entity_code": "CF", "cost_centre_code": "CC_IT", "name": "Hana Okafor", "title": "Data engineer",
                   "annual_salary": 132_000.0, "incentive_pct": 0.05, "start_date": str(start["2027P07"]), "end_date": "", "vacancy": "N"})
    i += 1
    people.append({"person_id": f"PER-{i:03d}", "entity_code": "CF", "cost_centre_code": "CC_MKT", "name": "Vacant — category manager", "title": "Category manager",
                   "annual_salary": 145_000.0, "incentive_pct": 0.05, "start_date": str(start["2027P08"]), "end_date": "", "vacancy": "Y"})
    return {"reg_entitlement": agreement, "ref_on_cost": on_cost, "reg_position": positions, "reg_person": people}
