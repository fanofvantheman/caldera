"""The capital plan: the assets as loaded, the projects, the sustaining rate and the leases — each walked period by period
into cash out, additions, depreciation and the net book value it leaves.

Written once, called from three places:

- the run (`models/plan/capex_line.py`) walks every item of every version over that version's plan periods;
- the generator (`generate/costs.py`) walks the assets as loaded over the closed periods, which is what the ledgers'
  depreciation actuals are;
- the face (`face/capex.py`) reads the run's rows and checks a new project with `check_item` before it is placed.

An item is one of four kinds:
  asset       on the fixed-asset register as loaded: cost and accumulated depreciation at the register's date
  project     a spend profile (even over its spend periods), capitalised whole at its in-service period, depreciated from it
  sustaining  an annual rate on the gross cost of the cost centre's assets, spent every period and in service as spent
  lease       a fixed charge per period over its term; no cash at the start, no asset, no liability

Depreciation by the asset class's method:
  straight_line        (cost − residual) ÷ (life in years × 12) a period, from the in-service period, never below residual
  units_of_production  (cost − residual) × the period's units ÷ the item's lifetime units — the units are the cases made
                       at the item's plant (Caldera plans no production by line yet)
"""
from __future__ import annotations

from typing import Callable, Iterable

PER_YEAR = 12
METHODS = ("straight_line", "units_of_production")
KINDS = ("asset", "project", "sustaining", "lease")
DEPRECIATION, LEASES = "6750", "6700"          # the accounts the charges land on in the opex schedule
COLUMNS = ["version_id", "item_id", "kind", "item_name", "asset_class", "entity_code", "cost_centre_code", "plant_code", "period", "fiscal_year",
           "spend", "additions", "depreciation", "lease_charge", "opening_nbv", "closing_nbv", "units"]


class Inputs:
    """What the walk reads (a plain class: SQLMesh carries this module into the model by its source).
      periods     every period of the calendar, in order; fy_of period → fiscal year
      plan        the version's plan periods: after its from point, to the last it plans
      upto        the version's from point (its last actual period)
      classes     asset class → {method, life_years, residual_pct, class_name}
      assets      the register as loaded
      units       (plant, period) → cases made in the version's plan periods; actual the same from shipments, closed periods"""

    def __init__(self, version, periods, fy_of, plan, upto, classes, assets, units):
        self.version, self.periods, self.fy_of, self.plan, self.upto = version, periods, fy_of, plan, upto
        self.classes, self.assets, self.units = classes, assets, units
        self.actual: dict = {}
        self._plan = set(plan)

    def u(self, plant: str, period: str) -> float:
        """Cases made at a plant in a period: the version's plan in its plan periods, the shipments before."""
        return self.units.get((plant, period), 0.0) if period in self._plan else self.actual.get((plant, period), 0.0)


def read_inputs(fetch: Callable[[str], list[dict]], T: Callable[[str], str], version: str) -> Inputs:
    v = version.replace("'", "")
    per = fetch(f"select period, fiscal_year from {T('dims.dim_period')} order by period")
    ver = (fetch(f"select from_period, plan_through from {T('dims.ctl_version')} where version_id = '{v}'") or [{}])[0]
    upto, through = ver.get("from_period") or "", ver.get("plan_through") or ""
    periods = [p["period"] for p in per]
    plan = [p for p in periods if upto < p <= through] if upto and through else []
    classes = {c["asset_class"]: c for c in fetch(f"select * from {T('dims.ref_asset_class')}")}
    assets = fetch(f"select * from {T('dims.reg_asset')} order by asset_id")
    route = f"(select material_code, plant_code from {T('dims.ref_route')} where is_primary)"
    units: dict = {}
    actual: dict = {}
    for r in fetch(f"""select r.plant_code, s.period, sum(s.cases) q from {T('history.shipments')} s join {route} r using (material_code)
                       group by all"""):
        actual[(r["plant_code"], r["period"])] = float(r["q"] or 0)
    pinn = ",".join(f"'{p}'" for p in plan) or "''"
    for r in fetch(f"""select r.plant_code, d.period, sum(d.cases) q from {T('plan.demand_financialised')} d join {route} r using (material_code)
                       where d.version_id = '{v}' and d.period in ({pinn}) group by all"""):
        units[(r["plant_code"], r["period"])] = float(r["q"] or 0)
    inp = Inputs(version, periods, {p["period"]: int(p["fiscal_year"]) for p in per}, plan, upto, classes, assets, units)
    inp.actual = actual
    return inp


def _f(x, default=0.0) -> float:
    try:
        return default if x is None or x == "" else float(x)
    except (TypeError, ValueError):
        return default


def charge(item: dict, cls: dict, base: float, units: float) -> float:
    """One period's depreciation on a depreciable base (cost − residual) — before the floor at residual."""
    if cls.get("method") == "units_of_production":
        life = _f(item.get("lifetime_units"))
        return base * units / life if life > 0 else 0.0
    years = _f(item.get("life_years")) or _f(cls.get("life_years"))
    return base / (years * PER_YEAR) if years > 0 else 0.0


def in_force(acts: Iterable[dict]) -> list[dict]:
    """The items the plan's people entered that stand: the latest row per item (an amendment is a later row of the same
    item), less any a `withdraw` row names. Acts in the order typed."""
    acts = list(acts)
    out_ = {a["withdraws"] for a in acts if a.get("action") == "withdraw" and a.get("withdraws")}
    latest: dict = {}
    for a in acts:
        if a.get("action") != "withdraw":
            latest[a["item_id"]] = a
    return [a for a in latest.values() if a["item_id"] not in out_ and a.get("act_id") not in out_]


def _row(inp: Inputs, item: dict, kind: str, p: str, **x) -> dict:
    return {"version_id": inp.version, "item_id": item.get("item_id") or item.get("asset_id"), "kind": kind,
            "item_name": item.get("item_name") or item.get("asset_name"), "asset_class": item.get("asset_class") or "",
            "entity_code": item["entity_code"], "cost_centre_code": item["cost_centre_code"], "plant_code": item.get("plant_code") or "",
            "period": p, "fiscal_year": inp.fy_of.get(p), "spend": 0.0, "additions": 0.0, "depreciation": 0.0, "lease_charge": 0.0,
            "opening_nbv": 0.0, "closing_nbv": 0.0, "units": None, **x}


def walk_asset(inp: Inputs, a: dict, periods: list[str]) -> list[dict]:
    """An asset as loaded: its book value at the register's date, walked back to the version's from point by the charges
    of the closed periods between (or forward), then forward over `periods`."""
    cls = inp.classes.get(a["asset_class"], {})
    cost, residual = _f(a["cost"]), _f(a["cost"]) * _f(cls.get("residual_pct"))
    base = cost - residual
    plant = a.get("plant_code") or ""
    nbv = cost - _f(a["accumulated"])
    at = a["as_at_period"]
    start = inp.upto if periods else at
    lo, hi = (start, at) if start < at else (at, start)
    for p in inp.periods:                          # the closed periods between the register's date and the from point
        if lo < p <= hi and p >= a["in_service_period"]:
            c = charge(a, cls, base, inp.u(plant, p))
            nbv = nbv + c if start < at else max(residual, nbv - c)
    out = []
    for p in periods:
        if p < a["in_service_period"]:
            continue
        u = inp.u(plant, p)
        d = min(max(nbv - residual, 0.0), charge(a, cls, base, u))
        out.append(_row(inp, a, "asset", p, depreciation=d, opening_nbv=nbv, closing_nbv=nbv - d,
                        units=u if cls.get("method") == "units_of_production" else None))
        nbv -= d
    return out


def walk_project(inp: Inputs, it: dict) -> list[dict]:
    cls = inp.classes.get(it["asset_class"], {})
    cost = _f(it["spend"])
    residual = cost * _f(cls.get("residual_pct"))
    spend_p = [p for p in inp.periods if it["spend_from"] <= p <= it["spend_to"]] or [it["in_service_period"]]
    plant = it.get("plant_code") or ""
    nbv, out = 0.0, []
    for p in inp.periods:
        if p > (inp.plan[-1] if inp.plan else ""):
            break
        cash = cost / len(spend_p) if p in spend_p else 0.0
        add = cost if p == it["in_service_period"] else 0.0
        opening = nbv
        nbv += add
        d = 0.0
        if p >= it["in_service_period"]:
            d = min(max(nbv - residual, 0.0), charge(it, cls, cost - residual, inp.u(plant, p)))
        nbv -= d
        if p in inp.plan:
            out.append(_row(inp, it, "project", p, spend=cash, additions=add, depreciation=d, opening_nbv=opening, closing_nbv=nbv,
                            units=inp.u(plant, p) if cls.get("method") == "units_of_production" else None))
    return out


def walk_sustaining(inp: Inputs, it: dict) -> list[dict]:
    """The rate on the gross cost of the cost centre's assets as loaded, spent each plan period and in service as spent:
    each period's spend a vintage of its own, straight-line over the class's life."""
    cls = inp.classes.get(it["asset_class"], {})
    gross = sum(_f(a["cost"]) for a in inp.assets if a["cost_centre_code"] == it["cost_centre_code"] and a["entity_code"] == it["entity_code"])
    each = gross * _f(it["rate"]) / PER_YEAR
    res = _f(cls.get("residual_pct"))
    nbv, vintages, out = 0.0, 0, []
    for p in inp.plan:
        if p < (it.get("spend_from") or "") or (it.get("spend_to") and p > it["spend_to"]):
            each_p = 0.0
        else:
            each_p = each
        opening = nbv
        vintages += 1 if each_p else 0
        nbv += each_p
        d = sum(charge(it, cls, each * (1 - res), 0.0) for _ in range(vintages))
        nbv -= d
        out.append(_row(inp, it, "sustaining", p, spend=each_p, additions=each_p, depreciation=d, opening_nbv=opening, closing_nbv=nbv))
    return out


def walk_lease(inp: Inputs, it: dict) -> list[dict]:
    per = _f(it["lease_charge"])
    return [_row(inp, it, "lease", p, lease_charge=per) for p in inp.plan
            if it["in_service_period"] <= p and (not it.get("lease_to_period") or p <= it["lease_to_period"])]


def lease_actual(it: dict, p: str) -> float:
    return _f(it["lease_charge"]) if it["in_service_period"] <= p and (not it.get("lease_to_period") or p <= it["lease_to_period"]) else 0.0


def compute(inp: Inputs, acts: Iterable[dict]) -> list[dict]:
    """Every item of the version × its plan periods. `acts` the version's items in force (in_force)."""
    rows: list[dict] = []
    for a in inp.assets:
        rows += walk_asset(inp, a, inp.plan)
    for it in acts:
        k = it["kind"]
        rows += walk_project(inp, it) if k == "project" else walk_sustaining(inp, it) if k == "sustaining" else walk_lease(inp, it) if k == "lease" else []
    return rows


def actuals(classes: dict, assets: list[dict], leases: list[dict], periods: list[str], units: dict, first: dict) -> list[dict]:
    """The ledgers' depreciation and lease charges over closed periods, from the assets as loaded and the leases running —
    the same charge the plan walks forward. `first` entity → its first period in the ledger. Draws nothing."""
    rows = []
    for a in assets:
        cls = classes[a["asset_class"]]
        base = float(a["cost"]) * (1 - float(cls["residual_pct"]))
        for p in periods:
            if p < a["in_service_period"] or p < first[a["entity_code"]]:
                continue
            c = charge(a, cls, base, units.get((a.get("plant_code") or "", p), 0.0))
            if c:
                rows.append({"entity_code": a["entity_code"], "cost_centre_code": a["cost_centre_code"], "account_code": DEPRECIATION, "period": p, "amount": round(c, 2)})
    for it in leases:
        for p in periods:
            c = lease_actual(it, p)
            if c and p >= first[it["entity_code"]]:
                rows.append({"entity_code": it["entity_code"], "cost_centre_code": it["cost_centre_code"], "account_code": LEASES, "period": p, "amount": round(c, 2)})
    return rows


def check_item(it: dict, classes: dict, periods: list[str], plan: list[str]) -> list[dict]:
    """The checks a new item must pass before it is placed: each {check, ok, says}."""
    k = it.get("kind")
    cls = classes.get(it.get("asset_class") or "", {})
    out = [{"check": "a kind we plan", "ok": k in ("project", "sustaining", "lease"), "says": k or "no kind"},
           {"check": "a name", "ok": bool((it.get("item_name") or "").strip()), "says": it.get("item_name") or "no name"}]
    if k != "lease":
        out.append({"check": "an asset class", "ok": bool(cls), "says": cls.get("class_name") or f"{it.get('asset_class') or 'none'} is not a class"})
    if k == "project":
        sp = _f(it.get("spend"), None)
        out += [{"check": "a spend", "ok": sp is not None and 0 < sp <= 1e9, "says": f"{sp:,.0f}" if sp is not None else "not an amount"},
                {"check": "spend periods in order", "ok": it.get("spend_from") in periods and it.get("spend_to") in periods and it["spend_from"] <= it["spend_to"],
                 "says": f"{it.get('spend_from')} to {it.get('spend_to')}"},
                {"check": "in service after the first spend", "ok": it.get("in_service_period") in periods and it["in_service_period"] >= (it.get("spend_from") or ""),
                 "says": it.get("in_service_period") or "no period"},
                {"check": "spend inside the plan", "ok": bool(plan) and (it.get("spend_from") or "") >= plan[0],
                 "says": f"the plan's periods are {plan[0]} to {plan[-1]}" if plan else "the version plans no period"}]
        if cls.get("method") == "units_of_production":
            out.append({"check": "lifetime units for units of production", "ok": _f(it.get("lifetime_units")) > 0, "says": it.get("lifetime_units") or "none given"})
        else:
            out.append({"check": "a useful life", "ok": 0 < (_f(it.get("life_years")) or _f(cls.get("life_years"))) <= 100,
                        "says": f"{_f(it.get('life_years')) or _f(cls.get('life_years')):g} years"})
    if k == "sustaining":
        r = _f(it.get("rate"), None)
        out.append({"check": "a rate a year", "ok": r is not None and 0 < r < 1, "says": f"{r:.1%}" if r is not None else "not a rate"})
    if k == "lease":
        c = _f(it.get("lease_charge"), None)
        out += [{"check": "a charge a period", "ok": c is not None and 0 < c <= 1e8, "says": f"{c:,.0f}" if c is not None else "not an amount"},
                {"check": "a term in order", "ok": it.get("in_service_period") in periods and (not it.get("lease_to_period") or it["lease_to_period"] >= it["in_service_period"]),
                 "says": f"{it.get('in_service_period')} to {it.get('lease_to_period') or 'open'}"}]
    return out
