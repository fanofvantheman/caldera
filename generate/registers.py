"""Registers the plan reads: the version control, roles, the capacity register, planning
assumptions, campaign windows. Small, declared, effective-dated where it matters."""

from __future__ import annotations

from .calendar import Week, periods
from .structures import LINES, COST_CENTRES


def versions(weeks: list[Week], plan_fy: int, latest_closed: str) -> list[dict]:
    """Every forward view is a version, named by the cycle that produced it, with a horizon.
    ACTUAL is the closed history; BP is the business plan for the year; LV-<period> the latest view
    produced by a cycle, rolling 36 periods from the period after the one it closed; scenarios hang off the version they were read against."""
    return [
        {"version_id": "ACTUAL", "version_kind": "actual", "cycle": "", "fiscal_year": "", "horizon_start": weeks[0].period,
         "horizon_end": latest_closed, "calendar_variant": "4-4-5", "standard_version": "STD-FY2027", "reference_version": "",
         "status": "closed", "owner": "finance", "named_on": "2026-10-26"},
        {"version_id": f"BP-FY{plan_fy}", "version_kind": "business_plan", "cycle": f"AOP FY{plan_fy}", "fiscal_year": plan_fy,
         "horizon_start": f"{plan_fy}P01", "horizon_end": f"{plan_fy}P12", "calendar_variant": "4-4-5", "standard_version": "STD-FY2027",
         "reference_version": "", "status": "frozen", "owner": "finance", "named_on": "2026-06-15"},
        {"version_id": f"LV-{latest_closed}", "version_kind": "latest_view", "cycle": f"IBP {latest_closed}", "fiscal_year": plan_fy,
         "horizon_start": f"{plan_fy}P05", "horizon_end": f"{plan_fy + 3}P04", "calendar_variant": "4-4-5", "standard_version": "STD-FY2027",
         "reference_version": f"BP-FY{plan_fy}", "status": "open", "owner": "finance", "named_on": "2026-11-02"},
    ]


def period_control(weeks: list[Week], latest_closed: str) -> list[dict]:
    rows = []
    for p in periods(weeks):
        state = "CLOSED" if p["period"] <= latest_closed else ("OPEN" if p["period"] == _next(latest_closed) else "FUTURE")
        rows.append({**p, "period_start": p["period_start"].isoformat(), "period_end": p["period_end"].isoformat(), "state": state})
    return rows


def _next(period: str) -> str:
    fy, p = int(period[:4]), int(period[-2:])
    return f"{fy}P{p + 1:02d}" if p < 12 else f"{fy + 1}P01"


# --- roles: a role is a bundle of actions; an assignment binds a principal at a node of a hierarchy -----------------

ROLE_DEFINITIONS = [
    ("DEMAND_PLANNER",       "Demand planner",            "Owns the statistical baseline and the baseline adjustment; the unconstrained demand plan is the sum."),
    ("KEY_ACCOUNT_MANAGER",  "Key account manager",       "Owns distribution and the customer structure for the accounts held."),
    ("TRADE_MARKETING",      "Trade marketing",           "Owns the promotions calendar and the promotion mapping review."),
    ("SALES_FINANCE",        "Sales finance",             "Owns the terms register, the price list and the gross-to-net."),
    ("PORTFOLIO_MARKETING",  "Portfolio marketing",       "Owns innovation and lifecycle exit, and the commercial side of the material structure."),
    ("SUPPLY_PLANNER",       "Supply planner",            "Owns the capacity registers, routes, the production policy entry and the supply constraint."),
    ("MATERIALS_PLANNER",    "Materials and intake planner", "Owns the supply plan by vendor and key material, supplier prices and freight contracts."),
    ("NETWORK_PLANNER",      "Network planner",           "Owns nodes, lanes, sourcing rules and service levels."),
    ("PLANT_MANAGER",        "Plant manager",             "Accepts the production policy and tier steps within site authority; budget holder for the factory cost centres."),
    ("QUALITY",              "Quality and technical",     "Owns yield assumptions, shelf life and specification-driven recipe versions."),
    ("PEOPLE",               "People and culture",        "Holds the position register, roster patterns, the agreement register and unproductive-hours assumptions."),
    ("COMMERCIAL_FINANCE",   "Commercial finance",        "Owns versions, assumptions, the standard, the schedule, the balance sheet and reconciliation at entry."),
    ("RECONCILIATION_OWNER", "Reconciliation owner",      "Enters allocation and timing deltas and records the decision as the named latest view."),
    ("EXECUTIVE",            "Executive",                 "Accepts the decision that resets the reference; approves the business plan and capital."),
    ("HEAD_OF_DEMAND",       "Head of demand planning",   "Leads the demand plan: every unit's demand rolls to them; they alone submit the plan."),
    ("PLAN_READER",          "Plan reader",               "Reads the plan and its readings at a scope and nothing else."),
    ("AUDITOR",              "Auditor",                   "Reads everything, changes nothing."),
]

ROLE_ACTIONS = {
    "DEMAND_PLANNER":       ["layer.1.enter", "layer.2.enter", "layer.1.withdraw", "layer.2.withdraw", "layer.1.submit", "layer.2.submit", "layer.1.reopen", "layer.2.reopen",
                             "demand.unit.submit", "demand.unit.reopen", "read.plan", "read.reading", "read.drill", "read.health"],
    "HEAD_OF_DEMAND":       ["layer.1.enter", "layer.2.enter", "layer.1.withdraw", "layer.2.withdraw", "layer.1.submit", "layer.2.submit", "layer.1.reopen", "layer.2.reopen",
                             "demand.unit.submit", "demand.unit.reopen", "demand.plan.submit", "demand.plan.reopen", "read.plan", "read.reading", "read.drill", "read.health"],
    "KEY_ACCOUNT_MANAGER":  ["layer.4.enter", "layer.9.enter", "layer.4.withdraw", "layer.4.submit", "layer.4.reopen", "structure.customer.maintain", "mapping.accept", "mapping.alter", "read.plan", "read.reading", "read.drill"],
    "TRADE_MARKETING":      ["layer.6.enter", "layer.6.withdraw", "layer.6.submit", "layer.6.reopen", "register.promo_calendar.maintain", "mapping.accept", "mapping.alter", "read.plan", "read.reading", "read.drill"],
    "SALES_FINANCE":        ["register.terms.maintain", "register.price_list.maintain", "mapping.accept", "mapping.alter", "read.plan", "read.reading", "read.drill"],
    "PORTFOLIO_MARKETING":  ["layer.7.enter", "layer.8.enter", "layer.7.withdraw", "layer.8.withdraw", "layer.7.submit", "layer.8.submit", "layer.7.reopen", "layer.8.reopen", "structure.material.maintain", "mapping.accept", "mapping.alter", "read.plan", "read.reading", "read.drill"],
    "SUPPLY_PLANNER":       ["delta.supply.enter", "register.capacity.machine.maintain", "register.capacity.labour.maintain", "register.capacity.storage.maintain", "register.routes.maintain", "register.downtime.maintain", "structure.material.maintain", "structure.location.maintain", "bom.version.release", "run.plan", "read.plan", "read.reading", "read.drill", "read.health"],
    "MATERIALS_PLANNER":    ["register.supply_plan.maintain", "register.supplier_price_list.maintain", "register.freight_contract.maintain", "read.plan", "read.reading", "read.drill"],
    "NETWORK_PLANNER":      ["register.sourcing.maintain", "register.service_level.maintain", "register.capacity.logistics.maintain", "structure.location.maintain", "read.plan", "read.reading", "read.drill"],
    "PLANT_MANAGER":        ["policy.production.accept", "tier.step.accept", "headcount.enter", "schedule.line.enter", "capex.project.enter", "read.plan", "read.reading", "read.drill", "read.health"],
    "QUALITY":              ["register.yield.maintain", "register.shelf_life.maintain", "read.plan", "read.reading", "read.drill"],
    "PEOPLE":               ["structure.position.maintain", "register.agreement.maintain", "register.unproductive_hours.maintain", "read.plan", "read.reading"],
    "COMMERCIAL_FINANCE":   ["register.assumptions.maintain", "register.cost_input.maintain", "register.timing_policy.maintain", "register.customs.maintain", "register.hedge_book.maintain", "register.calendar.maintain", "version.name", "version.freeze", "version.declare_reference", "scenario.create", "standard.derive", "standard.declare", "cycle.open", "cycle.close", "run.plan", "read.plan", "read.reading", "read.drill", "read.health", "read.proof"],
    "RECONCILIATION_OWNER": ["delta.allocation.enter", "delta.timing.enter", "shaping.enter", "register.customer_priority.maintain", "scenario.promote", "decision.record", "review.reconciliation.close", "read.plan", "read.reading", "read.drill", "read.health"],
    "EXECUTIVE":            ["decision.accept", "capex.approve", "review.mbr.close", "read.plan", "read.reading", "read.drill", "read.proof"],
    "PLAN_READER":          ["read.plan", "read.reading"],
    "AUDITOR":              ["read.plan", "read.reading", "read.drill", "read.health", "read.proof"],
}

# principal, role, scope dimension, scope node — demand is planned by unit; one head leads; account managers at their majors
ROLE_ASSIGNMENTS = [
    ("head.demand@caldera",         "HEAD_OF_DEMAND",       "customer",     "ALL"),
    ("planner.westbrook@caldera",   "DEMAND_PLANNER",       "customer",     "PU_WES"),
    ("planner.carters@caldera",     "DEMAND_PLANNER",       "customer",     "PU_CAR"),
    ("planner.merritt@caldera",     "DEMAND_PLANNER",       "customer",     "PU_MER"),
    ("planner.independents@caldera","DEMAND_PLANNER",       "customer",     "PU_IND"),
    ("planner.horeca@caldera",      "DEMAND_PLANNER",       "customer",     "PU_HOR"),
    ("kam.westbrook@caldera",       "KEY_ACCOUNT_MANAGER",  "customer",     "WES"),
    ("kam.carters@caldera",         "KEY_ACCOUNT_MANAGER",  "customer",     "CAR"),
    ("kam.merritt@caldera",         "KEY_ACCOUNT_MANAGER",  "customer",     "MER"),
    ("trade.marketing@caldera",     "TRADE_MARKETING",      "customer",     "ALL"),
    ("portfolio.marketing@caldera", "PORTFOLIO_MARKETING",  "material",     "ALL"),
    ("supply.planner@caldera",  "SUPPLY_PLANNER",       "location",     "ECH"),
    ("supply.planner@caldera",  "SUPPLY_PLANNER",       "location",     "LOX"),
    ("supply.planner@caldera",  "SUPPLY_PLANNER",       "location",     "MEL"),
    ("supply.planner@caldera",  "SUPPLY_PLANNER",       "location",     "SYD"),
    ("supply.planner@caldera",  "SUPPLY_PLANNER",       "location",     "BNE"),
    ("supply.planner@caldera",  "MATERIALS_PLANNER",    "material",     "ALL"),
    ("supply.planner@caldera",  "NETWORK_PLANNER",      "location",     "ALL"),
    ("supply.planner@caldera",  "QUALITY",              "location",     "ECH"),
    ("supply.planner@caldera",  "QUALITY",              "location",     "LOX"),
    ("plant.manager@caldera",   "PLANT_MANAGER",        "location",     "ECH"),
    ("plant.manager@caldera",   "PLANT_MANAGER",        "location",     "LOX"),
    ("plant.manager@caldera",   "PLANT_MANAGER",        "organisation", "OPS"),
    ("finance.manager@caldera", "COMMERCIAL_FINANCE",   "organisation", "CAL"),
    ("finance.manager@caldera", "SALES_FINANCE",        "customer",     "ALL"),
    ("finance.manager@caldera", "RECONCILIATION_OWNER", "organisation", "CAL"),
    ("finance.manager@caldera", "PEOPLE",               "organisation", "CAL"),
    ("gm@caldera",              "EXECUTIVE",            "organisation", "CAL"),
    ("board.pack@caldera",      "PLAN_READER",          "organisation", "CAL"),
    ("auditor@caldera",         "AUDITOR",              "organisation", "CAL"),
]


def roles() -> tuple[list[dict], list[dict], list[dict]]:
    defs = [{"role_code": c, "role_name": n, "built_in": "Y", "description": d} for c, n, d in ROLE_DEFINITIONS]
    acts = [{"role_code": r, "action": a} for r, al in ROLE_ACTIONS.items() for a in al]
    asg = [{"principal": p, "principal_type": "user", "role_code": r, "scope_dimension": d, "scope_node": n,
            "valid_from": "2026-06-29", "valid_to": "", "assigned_by": "gm@caldera", "assigned_on": "2026-06-29"}
           for p, r, d, n in ROLE_ASSIGNMENTS]
    return defs, acts, asg


# --- capacity register: machine availability per line per period, campaign windows widen the hours -------------------

CAMPAIGN = {  # hall → fiscal periods in the campaign window (Jan–Apr ≈ P07–P10), at both plants
    "FRUIT": (7, 10), "TOMATO": (8, 10), "CUPS": (7, 10),
}


def capacity_register(weeks: list[Week]) -> list[dict]:
    """Each line's tier by period: its base shifts on five days outside the campaign; in the campaign window of its hall,
    one more shift (to three at most) on six days."""
    rows = []
    for p in periods(weeks):
        for line_code, _plant, area, _name, _uom, _speed, base_shifts in LINES:
            hall = area.split("_", 1)[1]
            in_campaign = hall in CAMPAIGN and CAMPAIGN[hall][0] <= p["fiscal_period"] <= CAMPAIGN[hall][1]
            shifts = min(3, base_shifts + 1) if in_campaign else base_shifts
            days = p["weeks"] * (6 if in_campaign else 5)
            hours = shifts * 8 * days
            rows.append({"line_code": line_code, "period": p["period"], "tier": f"{shifts}-shift", "shifts": shifts,
                         "working_days": days, "available_hours": hours, "planned_downtime_hours": round(hours * 0.06, 1),
                         "efficiency_assumption": 0.82, "campaign_window": "Y" if in_campaign else "N"})
    return rows


def assumptions() -> list[dict]:
    rows = []
    series = {
        "FX_AUDUSD":   ("AUD/USD spot", "rate", 0.66),
        "CPI":         ("Consumer price inflation, annual", "pct", 0.032),
        "WAGE_INDEX":  ("Wage price index, annual", "pct", 0.038),
        "ENERGY_IDX":  ("Energy price index (FY2027P01 = 100)", "index", 100.0),
        "TINPLATE_IDX":("Tinplate price index (FY2027P01 = 100)", "index", 100.0),
        "RESIN_IDX":   ("PP resin price index (FY2027P01 = 100)", "index", 100.0),
        "SUGAR_IDX":   ("Sugar price index (FY2027P01 = 100)", "index", 100.0),
        "RETURNS_RATE":("Returns and ullage, share of invoice value (history rate)", "pct", 0.004),
        "CLAIMS_RATE": ("Shortage and damage claims, share of invoice value (history rate)", "pct", 0.003),
    }
    for version_id, note in (("BP-FY2027", "flat across the horizon in the business plan"), ("LV-2027P04", "carried from the business plan; no change this cycle")):
        for code, (name, kind, value) in series.items():
            rows.append({"assumption_code": code, "assumption_name": name, "kind": kind, "version_id": version_id,
                         "period": "", "value": value, "owner": "finance.manager@caldera", "note": note})
    return rows
