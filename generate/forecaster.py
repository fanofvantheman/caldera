"""The forecasting system: where the statistical baseline of the three largest accounts is made, and what it sends.

Each account says where its baseline comes from (`BASELINE_SOURCE` in structures.py): the forecasting system for
Westbrook, Carters and Merritt; calculated in the plan for every other account. The system is fed from the same ERP the
plan's structures come from, so its material and account codes are ours — where the two disagree it is because one
side has a code the other does not, never because a code needs translating.

A run is one file pair: a header that says what the numbers are (when it was made, the last week of history it used,
how far it reaches, at what grain, whether promotions are in or out, what history it was fitted on) and the series —
material × account × week, cases. It forecasts each series the classical way: a seasonal index per fiscal week from
two years of history with promotion weeks and the week after removed, the level of the last twenty-six weeks with the
season taken out, and the series' own year-on-year trend held within ±15%.

  plan/fcst_run.csv, plan/fcst_series.csv      the run already taken in
  plan/reg_door_act.csv (door FCS)             the resolutions made at onboarding
  sender/FCS-20261109_run.csv, …_series.csv    the next run, waiting: it left promotions in, and says so

The run disagrees with the plan's structures in the ways such a system does: a pack it has renumbered (so the old
code is missing and a new one arrives), a product the plan has not got yet, a pre-packed display shipper the plan
never carries, and two series it dropped.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

from .calendar import Week
from .structures import CATEGORIES, PRODUCTS, Material

SENDER = "FCS"
FIRST_RUN, NEXT_RUN = "FCS-20261102", "FCS-20261109"
HORIZON_WEEKS = 78
METHOD = "seasonal index by fiscal week on two years, level of the last 26 weeks, own trend within ±15%"

RUN_COLUMNS = ["sender", "run_id", "made_on", "last_history_week", "first_week", "horizon_weeks", "grain", "content", "history_basis", "method_note"]
SERIES_COLUMNS = ["sender", "run_id", "material_code", "material_description", "sender_hierarchy", "account_code", "week_start", "cases"]

# a product the plan has not got yet, sent for Westbrook from its ninth week
NEW_CODE, NEW_NAME, NEW_HIERARCHY, NEW_ACCOUNT, NEW_CASES = (
    "CUP_PEACH_MANGO-CUP_4x120", "Peach and mango in juice, 4 × 120 g cups", "Fruit snack cups > Peach and mango in juice", "WES", 340.0)
# a pre-packed display the forecasting system carries as its own code; the plan carries the materials inside it
SHIPPER_CODE, SHIPPER_NAME, SHIPPER_HIERARCHY = "DISPLAY-SHIPPER-XMAS", "Christmas display shipper, mixed canned fruit (pre-packed pallet)", "Canned fruit > Display units"


def _fw(w: Week) -> int:
    return min(w.fiscal_week, 52)


def _fit(obs: dict[int, tuple[float, bool]], hist: list[Week], future: list[Week], trend_cap: float = 0.15) -> list[float]:
    """One series. obs: history position → (cases, promotion week). Returns a forecast per future week, or [] where the
    series has not shipped in the last thirteen weeks."""
    n = len(hist)
    shipped = [i for i, (c, _) in obs.items() if c > 0]
    if not shipped or max(shipped) < n - 13:
        return []
    first = min(shipped)
    clean: dict[int, float] = {}                              # position → cases, promotion weeks and the week after left out
    for i in range(max(first, n - 104), n):
        c, promo = obs.get(i, (0.0, False))
        if promo or obs.get(i - 1, (0.0, False))[1]:
            continue
        clean[i] = c
    if len(clean) < 8:
        return []
    mean_all = sum(clean.values()) / len(clean)
    if mean_all <= 0:
        return []
    by_fw: dict[int, list[float]] = defaultdict(list)
    for i, c in clean.items():
        by_fw[_fw(hist[i])].append(c)
    raw = {fw: (sum(v) / len(v)) / mean_all for fw, v in by_fw.items()}
    index = {}
    for fw in range(1, 53):                                   # a three-week centred average, so one noisy week is not a season
        near = [raw[x] for x in (((fw - 2) % 52) + 1, fw, (fw % 52) + 1) if x in raw]
        index[fw] = sum(near) / len(near) if near else 1.0
    recent = [(i, c) for i, c in clean.items() if i >= n - 26]
    level = sum(c / max(index[_fw(hist[i])], 0.2) for i, c in recent) / len(recent) if recent else mean_all
    last52 = [c for i, c in clean.items() if i >= n - 52]
    prior52 = [c for i, c in clean.items() if i < n - 52]
    trend = 1.0
    if last52 and prior52 and sum(prior52) > 0:
        trend = (sum(last52) / len(last52)) / (sum(prior52) / len(prior52))
        trend = max(1 - trend_cap, min(1 + trend_cap, trend))
    return [round(level * index[_fw(w)] * trend ** ((h + 1) / 52), 1) for h, w in enumerate(future)]


def run(shipments: list[dict], materials: list[Material], weeks: list[Week], latest_closed: str, sources: dict[str, str],
        version: str) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    """The run taken in with the build, the resolutions made at onboarding, and the next run waiting in the outbox."""
    hist = [w for w in weeks if w.period <= latest_closed]
    future = [w for w in weeks if w.period > latest_closed][:HORIZON_WEEKS]
    pos = {w.week_id: i for i, w in enumerate(hist)}
    takes = sorted(a for a, s in sources.items() if s == "FORECAST")
    name_of = {m.material_code: m for m in materials}
    product_name = {p[0]: p[1] for p in PRODUCTS}

    obs: dict[tuple[str, str], dict[int, tuple[float, bool]]] = defaultdict(dict)
    for r in shipments:
        if r["account_code"] in takes:
            c, p = obs[(r["material_code"], r["account_code"])].get(pos[r["week_id"]], (0.0, False))
            obs[(r["material_code"], r["account_code"])][pos[r["week_id"]]] = (c + r["cases"], p or r["is_promo_week"] == "Y")

    fitted = {k: f for k in sorted(obs) if (f := _fit(obs[k], hist, future))}
    by_volume = {a: sorted((k for k in fitted if k[1] == a), key=lambda k: -sum(fitted[k])) for a in takes}
    renumbered = by_volume["CAR"][40] if len(by_volume.get("CAR", [])) > 40 else None           # sent under a new code
    dropped = set(by_volume["MER"][i] for i in (25, 60) if len(by_volume.get("MER", [])) > i)   # not sent at all

    def series(run_id: str, keys, scale: float = 1.0) -> list[dict]:
        rows = []
        for mat, acct in keys:
            m = name_of[mat]
            code, desc = mat, m.material_name
            if (mat, acct) == renumbered:
                code, desc = f"{mat}-N", f"{m.material_name} (new outer)"
            hier = f"{CATEGORIES[m.category_code][0]} > {product_name.get(m.product_code, m.product_code)}"
            for w, c in zip(future, fitted[(mat, acct)]):
                if c * scale >= 0.05:
                    rows.append({"sender": SENDER, "run_id": run_id, "material_code": code, "material_description": desc, "sender_hierarchy": hier,
                                 "account_code": acct, "week_start": w.week_start.isoformat(), "cases": round(c * scale, 1)})
        return rows

    def header(run_id: str, made_on: str, content: str) -> dict:
        return {"sender": SENDER, "run_id": run_id, "made_on": made_on, "last_history_week": hist[-1].week_id, "first_week": future[0].week_start.isoformat(),
                "horizon_weeks": len(future), "grain": "material × account × week", "content": content,
                "history_basis": "shipments, promotion weeks and the week after removed", "method_note": METHOD}

    sent = series(FIRST_RUN, [k for k in fitted if k not in dropped])
    for w in future[8:]:
        sent.append({"sender": SENDER, "run_id": FIRST_RUN, "material_code": NEW_CODE, "material_description": NEW_NAME, "sender_hierarchy": NEW_HIERARCHY,
                     "account_code": NEW_ACCOUNT, "week_start": w.week_start.isoformat(), "cases": NEW_CASES})
    for acct in ("WES", "CAR"):
        for w in future[3:9]:
            sent.append({"sender": SENDER, "run_id": FIRST_RUN, "material_code": SHIPPER_CODE, "material_description": SHIPPER_NAME,
                         "sender_hierarchy": SHIPPER_HIERARCHY, "account_code": acct, "week_start": w.week_start.isoformat(), "cases": 120.0})
    stamp = {"version_id": version, "taken_in_at": "2026-11-03T08:10:00", "taken_in_by": "head.demand@caldera"}
    plan = {
        "fcst_run": [{**header(FIRST_RUN, "2026-11-02", "baseline_only"), **stamp}],
        "fcst_series": [{**r, "version_id": version, "taken_in_at": stamp["taken_in_at"]} for r in sent],
        "reg_door_act": [
            {"act_id": "FR-0001", "door": SENDER, "kind": "theirs_not_ours", "item_code": SHIPPER_CODE, "scope_code": "ALL",
             "resolution": "leave_out", "target_code": "", "state": "decided", "origin": "person", "confidence": "", "rationale": "",
             "item_description": SHIPPER_NAME, "reason": "a pre-packed display of materials the plan already carries — counting it would count them twice",
             "acted_by": "head.demand@caldera", "acted_at": "2026-11-03T08:30:00"}],
    }
    # the next run, waiting: the same series for Westbrook's largest forty with promotions left in, and the header says so
    waiting = {
        f"{NEXT_RUN}_run": [header(NEXT_RUN, "2026-11-09", "total_forecast")],
        f"{NEXT_RUN}_series": series(NEXT_RUN, by_volume.get("WES", [])[:40], scale=1.09),
    }
    return plan, waiting
