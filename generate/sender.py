"""The promotions sender: the trade promotion system the two major chains' calendars are planned in, and what it sends.

Promotions are mastered in one place per account (`PROMOTIONS_MASTER` in structures.py). For Westbrook and Carters the
calendar is negotiated and kept in the sender's system, which exports it in its own codes — its own planning accounts,
product groups, tactics, fund types and status words — as two files: an event header (our layout, their codes) and a
funding package of one or more lines per event. Every other account's events are typed in the plan.

This module re-issues the calendar through the doors and writes what the sender would send:

  plan/tpm_event.csv, plan/tpm_funding.csv   the export already taken in (Westbrook's and Carters' events)
  plan/reg_promo_event.csv                   the events typed in the plan (Merritt's), uplift and dip left to the
                                             mechanic's defaults
  plan/reg_door_act.csv                      the sender's codes mapped to ours at onboarding, every row accepted (door TPM)
  sender/TPM-20261112_events.csv, …_funding.csv
                                             the next export, waiting to be taken in: new events, one moved, one
                                             cancelled, one for an account whose promotions are mastered in the plan,
                                             and codes the mapping has not seen

The reference lists the mapping lands on — mechanics with their family and default response, funding types with the
ones the financialisation prices, status words — are here too.
"""

from __future__ import annotations

import datetime as dt

SENDER = "TPM"
FIRST_FILE, NEXT_FILE = "TPM-20261103", "TPM-20261112"

# our mechanic register — one or more mechanics in each of the seven families, the family named as the conformed list
# names it: (mechanic, name, family, default uplift on baseline, default dip after the window). An event has one
# mechanic, the one that sets its volume shape; a catalogue page or display supporting a price promotion is a funding
# line on the price event, not a second mechanic. Display and feature: modest uplift, small dip; a points offer: small
# uplift, no dip; clearance: uplift, no dip (the range is leaving).
MECHANICS = [
    ("half_price",        "Half price — 50% off the shelf price",                     "price",                    1.00, 0.15),
    ("price_cut",         "Temporary price reduction, less than half off",            "price",                    0.50, 0.15),
    ("multi_buy",         "Multi-buy — x for $y, buy-one-get-one",                    "price",                    0.45, 0.15),
    ("catalogue_feature", "Catalogue feature, no price change",                       "feature_and_display",      0.20, 0.05),
    ("gondola_end",       "Gondola end or off-location display, no price change",     "feature_and_display",      0.30, 0.05),
    ("bonus_pack",        "Bonus pack or on-pack offer",                              "pack",                     0.30, 0.10),
    ("seasonal_event",    "Seasonal or themed event — Christmas, Easter, back to school", "theme_and_seasonal",   0.35, 0.10),
    ("sampling",          "In-store sampling or demonstration",                       "trial_and_experience",     0.10, 0.00),
    ("points_offer",      "Loyalty points or personalised offer",                     "loyalty_and_personalised", 0.10, 0.00),
    ("clearance",         "Clearance — run-out of a range leaving the shelf",         "clearance",                0.40, 0.00),
    ("unclassified",      "A mechanic nobody can place yet",                          "unclassified",             0.00, 0.00),
]

# our funding types: (type, name, driver basis, priced by the financialisation, event column it fills)
FUNDING_TYPES = [
    ("price_reduction_per_case", "Price reduction per case, on invoice in the window",  "per_case", "Y", "tpr_per_case"),
    ("scan_per_case",            "Scan funding per case sold in the window",            "per_case", "Y", "scan_funding_per_case"),
    ("fixed_fee",                "Fixed fee for a placement — catalogue, display",       "lump_sum", "Y", "fixed_fee"),
    ("case_deal",                "Case deal per case bought in the buy-in window",       "per_case", "N", ""),
    ("bill_back",                "Bill-back per unit, claimed after the event",          "per_case", "N", ""),
    ("free_goods",               "Free goods — units shipped at no charge",              "units",    "N", ""),
    ("media",                    "Media or retail-media funding",                        "lump_sum", "Y", "media_fee"),
    ("envelope_drawdown",        "Spend drawn from an annual co-op envelope",            "lump_sum", "Y", "envelope_drawdown"),
    ("unclassified",             "A funding type nobody can place yet",                  "",         "N", ""),
]

# our status words: (status, name, enters the calendar)
STATUSES = [
    ("proposed",  "Proposed — a candidate, not yet agreed with the customer", "N"),
    ("agreed",    "Agreed with the customer",                                  "Y"),
    ("executed",  "Running or run",                                            "Y"),
    ("evaluated", "Run and evaluated",                                         "Y"),
    ("cancelled", "Cancelled — removed from the calendar",                     "N"),
]

# the sender's own codes, as its export describes them, and what onboarding mapped each to
ACCOUNTS = {"PA-1001": ("Westbrook Supermarkets — national", "WES"), "PA-1002": ("Carters Supermarkets — national", "CAR")}
GROUPS = {"PG-VG410": ("Valley Gold canned fruit 410g", "PG_VALLEY_410"), "PG-CUP4": ("Fruit snack cups 4 x 120g", "PG_CUPS_4PK"),
          "PG-BNSP": ("Baked beans & spaghetti cans", "PG_BEANS_SPAG"), "PG-RG400": ("Redgum tomatoes 400g", "PG_REDGUM"),
          "PG-RV500": ("Rosso Vale pasta sauce 500g jar", "PG_ROSSO_JARS"), "PG-VG825": ("Valley Gold canned fruit 825g", "PG_VALLEY_825"),
          "PG-FS825": ("Valley Gold fruit salad 825g", "PG_FRUITSAL_825")}
TACTICS = {"T50": ("Half price on shelf", "half_price"), "TPR": ("Temporary price reduction", "price_cut"),
           "MB": ("Multibuy 2 for $X", "multi_buy"), "GE": ("Gondola end display", "gondola_end"),
           "XMAS": ("Christmas seasonal display", "seasonal_event"), "PTS": ("Loyalty points offer", "points_offer"),
           "CLR": ("Clearance run-out", "clearance")}
FUNDS = {"OI": ("Off-invoice deal per case", "price_reduction_per_case"), "SCN": ("Scan rebate per case sold", "scan_per_case"),
         "CATF": ("Catalogue placement fee", "fixed_fee"), "GEF": ("Display placement fee", "fixed_fee"),
         "RMN": ("Retail media network placement", "media"), "COOP": ("Co-op fund drawdown", "envelope_drawdown")}
STATUS_WORDS = {"Draft": "proposed", "Approved": "agreed", "Executed": "executed", "Cancelled": "cancelled"}
ACCOUNT_OF = {ours: theirs for theirs, (_, ours) in ACCOUNTS.items()}
GROUP_OF = {ours: theirs for theirs, (_, ours) in GROUPS.items()}
TACTIC_OF = {ours: theirs for theirs, (_, ours) in TACTICS.items()}

EVENT_COLUMNS = ["event_id", "planning_account", "planning_account_name", "product_group", "product_group_name", "tactic", "tactic_name",
                 "shopper_start", "shopper_end", "status", "uplift_pct", "dip_pct", "baseline_version"]
FUNDING_COLUMNS = ["event_id", "line_no", "fund_type", "fund_type_name", "rate_basis", "rate"]


def reference() -> dict[str, list[dict]]:
    return {
        "ref_mechanic": [{"mechanic": m, "mechanic_name": n, "family": f, "default_uplift_pct": u, "default_dip_pct": d} for m, n, f, u, d in MECHANICS],
        "ref_funding_type": [{"funding_type": t, "funding_type_name": n, "driver_basis": b, "priced": p, "event_column": c} for t, n, b, p, c in FUNDING_TYPES],
        "ref_promo_status": [{"status": s, "status_name": n, "enters_calendar": e} for s, n, e in STATUSES],
    }


def _header(ev: dict, account: str, group: str, tactic: str, status: str = "Approved", shift_days: int = 0) -> dict:
    s = dt.date.fromisoformat(ev["window_start"]) + dt.timedelta(days=shift_days)
    e = dt.date.fromisoformat(ev["window_end"]) + dt.timedelta(days=shift_days)
    acct_name = ACCOUNTS.get(account, (ev.get("_account_name", ""),))[0]
    grp_name = GROUPS.get(group, (ev.get("_group_name", ""),))[0]
    tac_name = TACTICS.get(tactic, (ev.get("_tactic_name", ""),))[0]
    return {"event_id": ev["event_id"], "planning_account": account, "planning_account_name": acct_name, "product_group": group,
            "product_group_name": grp_name, "tactic": tactic, "tactic_name": tac_name, "shopper_start": s.isoformat(),
            "shopper_end": e.isoformat(), "status": status, "uplift_pct": ev["uplift_pct"], "dip_pct": ev["dip_pct"],
            "baseline_version": ev["baseline_version"]}


def _funding(ev: dict) -> list[dict]:
    lines = []
    for code, col, basis in (("OI", "tpr_per_case", "CASE"), ("SCN", "scan_funding_per_case", "CASE"), (ev.get("_fee_code") or "CATF", "fixed_fee", "LUMP"),
                             ("RMN", "media_fee", "LUMP"), ("COOP", "envelope_drawdown", "LUMP")):
        if ev.get(col):
            lines.append({"event_id": ev["event_id"], "line_no": len(lines) + 1, "fund_type": code, "fund_type_name": FUNDS[code][0],
                          "rate_basis": basis, "rate": ev[col]})
    return lines


def _stamped(rows: list[dict], file_id: str, version: str, at: str, by: str | None) -> list[dict]:
    return [{"sender": SENDER, "sender_file": file_id, "version_id": version, "taken_in_at": at, **({"taken_in_by": by} if by else {}), **r}
            for r in rows]


def through_the_doors(events: list[dict], masters: dict[str, str]) -> dict[str, list[dict]]:
    """Split the calendar by where each account's promotions are mastered. The sender's events go out in its codes and
    come back in as the export already taken in; the plan's own events are typed, uplift and dip left to the mechanic's
    defaults where they are the defaults."""
    defaults = {m: (u, d) for m, _, _, u, d in MECHANICS}
    version = events[0]["version_id"] if events else ""
    at, by = "2026-11-03T09:00:00", "trade.marketing@caldera"
    head, fund, typed = [], [], []
    for ev in events:
        if masters.get(ev["account_code"]) == "TPM":
            head.append(_header(ev, ACCOUNT_OF[ev["account_code"]], GROUP_OF[ev["promo_group_code"]], TACTIC_OF[ev["mechanic"]]))
            fund += _funding(ev)
        else:
            u, d = defaults[ev["mechanic"]]
            typed.append({**{k: x for k, x in ev.items() if not k.startswith("_")},
                          "uplift_pct": "" if ev["uplift_pct"] == u else ev["uplift_pct"], "dip_pct": "" if ev["dip_pct"] == d else ev["dip_pct"],
                          "note": "", "entered_on": "2026-11-03"})
    mapping = []
    for subject, codes in (("customer", {k: v for k, v in ACCOUNTS.items()}), ("material", GROUPS), ("mechanic", TACTICS), ("funding_type", FUNDS),
                           ("status", {w: (w, s) for w, s in STATUS_WORDS.items()})):
        for code, (desc, target) in codes.items():
            mapping.append({"act_id": f"MP-{len(mapping) + 1:04d}", "door": SENDER, "kind": subject, "item_code": code, "scope_code": "ALL",
                            "resolution": "accept", "target_code": target, "state": "decided", "origin": "person", "confidence": "", "rationale": "",
                            "item_description": desc, "reason": "mapped when the sender was connected", "acted_by": by, "acted_at": "2026-07-01T09:00:00"})
    return {"tpm_event": _stamped(head, FIRST_FILE, version, at, by), "tpm_funding": _stamped(fund, FIRST_FILE, version, at, None),
            "reg_promo_event": typed, "reg_door_act": mapping}


def next_export(events: list[dict], period_start: dict[str, dt.date], plan_fy: int) -> dict[str, list[dict]]:
    """The export that waits to be taken in during the demo, in the sender's layout (no version, nothing stamped): three
    new events — one in codes the mapping knows, one on a product group it has not seen, one on a new tactic funded
    partly by a fund type it has not seen — one event moved a week, one cancelled, and one for an account whose
    promotions are mastered in the plan (a planning account the mapping has not seen either)."""
    by_id = {e["event_id"]: e for e in events}
    v = events[0]["baseline_version"]

    def new(eid, period, off, days, uplift, dip, **funding):
        s = period_start[period] + dt.timedelta(days=off)
        return {"event_id": eid, "window_start": s.isoformat(), "window_end": (s + dt.timedelta(days=days - 1)).isoformat(),
                "uplift_pct": uplift, "dip_pct": dip, "baseline_version": v, **funding}

    n1 = new(f"EV-{plan_fy}-015", f"{plan_fy}P11", 16, 7, 0.55, 0.15, tpr_per_case=2.65, scan_funding_per_case=1.5)
    n2 = new(f"EV-{plan_fy}-016", f"{plan_fy}P10", 9, 14, 0.50, 0.15, tpr_per_case=3.10, scan_funding_per_case=1.5)
    n3 = new(f"EV-{plan_fy}-017", f"{plan_fy}P09", 2, 14, 0.25, 0.05, fixed_fee=15000.0)
    n4 = new(f"EV-{plan_fy}-018", f"{plan_fy}P10", 2, 7, 0.45, 0.15, tpr_per_case=2.93)
    moved, cancelled = by_id[f"EV-{plan_fy}-006"], by_id[f"EV-{plan_fy}-010"]
    head = [
        _header(n1, "PA-1001", "PG-RG400", "TPR"),
        _header({**n2, "_group_name": "Orchard House jam 500g jar"}, "PA-1002", "PG-OH500", "TPR"),
        _header({**n3, "_tactic_name": "Catalogue + gondola end, no price change"}, "PA-1001", "PG-VG410", "CATG"),
        _header({**n4, "_account_name": "Merritt Independents — wholesale banner"}, "PA-2040", "PG-BNSP", "MB"),
        _header(moved, ACCOUNT_OF[moved["account_code"]], GROUP_OF[moved["promo_group_code"]], TACTIC_OF[moved["mechanic"]], shift_days=7),
        _header(cancelled, ACCOUNT_OF[cancelled["account_code"]], GROUP_OF[cancelled["promo_group_code"]], TACTIC_OF[cancelled["mechanic"]], status="Cancelled"),
    ]
    fund = _funding(n1) + _funding(n2) + _funding(n3) + _funding(n4) + _funding(moved) + _funding(cancelled)
    fund.append({"event_id": n3["event_id"], "line_no": 2, "fund_type": "DSPA", "fund_type_name": "Display build allowance",
                 "rate_basis": "LUMP", "rate": 8000.0})
    return {f"{NEXT_FILE}_events": head, f"{NEXT_FILE}_funding": fund}
