"""The inventory plan (DEC-20261117-02): replenishment at each stocking point, mapped back to the plant that supplies it —
the production requirement the supply side owes the rest of the plan. The model (models/plan/inventory_flow.py), the
supply pages and the storage page's stress test call the same function, so a reading on a page is the plan's arithmetic.

Two tiers, the default topology (`location_and_drp.md`): ship-to → its serving DC → the plant that supplies the DC.

  demand at a DC      the plan's cases at the ship-tos it serves, by week
  safety stock        solved for the declared fill rate of the material's class: z such that σ√(L+R) × G(z) ÷ Q = 1 − target,
                      Q a review period's demand; safety stock = z × σ√(L+R). σ is the weekly variability of what the node
                      shipped over the last 52 closed weeks — the note's fallback (demand variability, an upper bound):
                      Caldera keeps no weekly residual of the plan, and the page says so
  order-up-to         S = the demand over the next L + R weeks + safety stock; each week the node receives max(0, S − opening)
                      and ships its demand; the closing is carried
  the plant           the DCs' receipts, each sent L weeks before it lands (the lane's transit, in whole weeks), by the share
                      of the sourcing rule, are the plant's demand; it holds its own safety stock on the same rule and makes
                      max(0, S − opening): the production requirement — a quantity by material × plant × week, read at the
                      period, not sequenced against the lines
  opening             the target at the first week (Caldera loads no stock position — a declared stand-in)

A typed production quantity for a period replaces the plant's proposal in that period, spread over its weeks by the
proposal's shape (evenly where the proposal is nil). `hold` — production held as planned for a run of weeks while demand
moves (the stress test) — is the same replacement, by week."""
from __future__ import annotations

import math
from collections import defaultdict

Z_MAX = 4.0


def loss(z: float) -> float:
    """The standard normal loss function G(z) = φ(z) − z(1 − Φ(z))."""
    phi = math.exp(-z * z / 2) / math.sqrt(2 * math.pi)
    return phi - z * (1 - 0.5 * math.erfc(-z / math.sqrt(2)))


def safety_stock(sigma: float, mean: float, lead_weeks: int, review_weeks: int, fill_rate: float) -> float:
    """Fill-rate safety stock (location_and_drp.md §Replenishment logic): find z with σ√(L+R) G(z) / Q = 1 − target."""
    if not sigma or sigma <= 0 or not mean or mean <= 0 or fill_rate is None:
        return 0.0
    s = sigma * math.sqrt(max(lead_weeks + review_weeks, 1))
    q = mean * review_weeks
    want = (1 - fill_rate) * q / s                    # G(z) must fall to this; G decreases in z
    if want >= loss(0.0):
        return 0.0                                    # the review quantity alone meets the fill rate: no buffer
    lo, hi = 0.0, Z_MAX
    for _ in range(60):
        mid = (lo + hi) / 2
        if loss(mid) > want:
            lo = mid
        else:
            hi = mid
    return hi * s


def walk(demand: list[float], ss: float, cover: int, opening: float | None = None, fixed: dict[int, float] | None = None) -> list[dict]:
    """One node × material over its weeks: order-up-to S = the demand over the next `cover` weeks + safety stock. `fixed`
    by week index replaces the receipt (a production held or typed). Opening at the first week's target unless given."""
    n = len(demand)
    fixed = fixed or {}
    target = [sum(demand[w:w + cover]) + ss for w in range(n)]
    stock = target[0] if opening is None else opening
    rows = []
    for w in range(n):
        receipt = fixed[w] if w in fixed else max(0.0, target[w] - stock)
        peak = stock + receipt
        close = peak - demand[w]
        rows.append({"opening": stock, "receipt": receipt, "demand": demand[w], "closing": close, "peak": peak, "target": target[w], "safety_stock": ss})
        stock = close
    return rows


def flow(weeks: list[str], period_of: dict[str, str], demand: dict[tuple, float], sourcing: dict[tuple, list[tuple]], lead: dict[tuple, int],
         sigma: dict[tuple, float], fill: dict[str, float], review_weeks: int = 1, typed: dict[tuple, float] | None = None,
         hold: dict[tuple, float] | None = None) -> dict:
    """The whole network on one plan.
    demand      (dc, material, week) → cases
    sourcing    (dc, material) → [(plant, share)]
    lead        (plant, dc) → weeks
    sigma       (node, material) → weekly σ
    fill        material → the fill rate of its class
    typed       (material, plant, period) → a production quantity typed for the period
    hold        (material, plant, week) → production held at this quantity in that week
    Returns {"nodes": {(node, material): [weekly rows]}, "production": {(material, plant): [weekly]}, "sources": {(material, plant, week): {dc: cases}}}."""
    typed, hold = typed or {}, hold or {}
    idx = {w: i for i, w in enumerate(weeks)}
    n = len(weeks)
    dcs = sorted({(d, m) for d, m, _ in demand})
    nodes: dict[tuple, list[dict]] = {}
    orders: dict[tuple, list[float]] = defaultdict(lambda: [0.0] * n)            # (plant, material) → weekly demand on the plant
    sources: dict[tuple, dict] = defaultdict(lambda: defaultdict(float))         # (material, plant, week) → {dc: cases}
    for d, m in dcs:
        dem = [float(demand.get((d, m, w)) or 0.0) for w in weeks]
        rules = sourcing.get((d, m)) or []
        lmax = max((lead.get((p, d), 0) for p, _ in rules), default=0)
        mean = sum(dem) / n if n else 0.0
        ss = safety_stock(sigma.get((d, m), 0.0), mean, lmax, review_weeks, fill.get(m))
        rows = walk(dem, ss, lmax + review_weeks)
        nodes[(d, m)] = rows
        for p, share in rules:
            L = lead.get((p, d), 0)
            for w, r in enumerate(rows):
                sent = w - L                           # sent L weeks before it lands; a receipt in the first L weeks is in transit already
                if sent >= 0 and r["receipt"]:
                    orders[(p, m)][sent] += r["receipt"] * share
                    sources[(m, p, weeks[sent])][d] += r["receipt"] * share
    production: dict[tuple, list[dict]] = {}
    for (p, m), dem in orders.items():
        mean = sum(dem) / n if n else 0.0
        ss = safety_stock(sigma.get((p, m), 0.0), mean, 0, review_weeks, fill.get(m))
        proposed = walk(dem, ss, review_weeks)
        fixed: dict[int, float] = {}
        by_period: dict[str, list[int]] = defaultdict(list)
        for w in range(n):
            by_period[period_of[weeks[w]]].append(w)
        for per, ws in by_period.items():
            t = typed.get((m, p, per))
            if t is not None:
                base = [proposed[w]["receipt"] for w in ws]
                tot = sum(base)
                for w, b in zip(ws, base):
                    fixed[w] = t * (b / tot if tot > 0 else 1 / len(ws))
        for w in range(n):
            h = hold.get((m, p, weeks[w]))
            if h is not None:
                fixed[w] = h
        rows = walk(dem, ss, review_weeks, opening=proposed[0]["opening"], fixed=fixed) if fixed else proposed
        for w, r in enumerate(rows):
            r["proposed"] = proposed[w]["receipt"]
            r["typed"] = w in fixed and (m, p, period_of[weeks[w]]) in typed
        production[(m, p)] = rows
        nodes[(p, m)] = rows
    return {"nodes": nodes, "production": production, "sources": sources, "weeks": weeks, "period_of": period_of}


def by_period(weekly: list[dict], weeks: list[str], period_of: dict[str, str]) -> list[dict]:
    """A node's weeks read at the period: flows summed, the closing at the period's last week, the peak the most it held."""
    out: dict[str, dict] = {}
    for w, r in zip(weeks, weekly):
        p = period_of[w]
        o = out.setdefault(p, {"period": p, "demand": 0.0, "receipt": 0.0, "proposed": 0.0, "opening": r["opening"], "peak": 0.0,
                               "safety_stock": r["safety_stock"], "typed": False, "weeks": 0})
        o["demand"] += r["demand"]; o["receipt"] += r["receipt"]; o["proposed"] += r.get("proposed", r["receipt"])
        o["peak"] = max(o["peak"], r["peak"]); o["closing"] = r["closing"]; o["target"] = r["target"]
        o["typed"] |= bool(r.get("typed")); o["weeks"] += 1
    return list(out.values())


COLUMNS = ["version_id", "node_code", "node_kind", "material_code", "period", "fiscal_year", "weeks", "demand", "receipt", "proposed", "opening",
           "closing", "peak", "safety_stock", "target", "typed"]
TYPES = {c: "DOUBLE" for c in COLUMNS} | {"version_id": "TEXT", "node_code": "TEXT", "node_kind": "TEXT", "material_code": "TEXT", "period": "TEXT",
                                          "fiscal_year": "INT", "weeks": "INT", "typed": "BOOLEAN"}


def read_inputs(fetch, T, version: str) -> dict:
    """What the flow is made from, read the same way by the run and the face. `fetch(sql)` → rows as dicts."""
    v = version.replace("'", "")
    ver = (fetch(f"select from_period, plan_through from {T('dims.ctl_version')} where version_id = '{v}'") or [{}])[0]
    if not ver.get("from_period"):
        return {}
    wk = fetch(f"""select week_id, period, fiscal_year from {T('dims.dim_week')} where period > '{ver['from_period']}' and period <= '{ver['plan_through']}' order by week_id""")
    weeks = [r["week_id"] for r in wk]
    period_of = {r["week_id"]: r["period"] for r in wk}
    fy_of = {r["period"]: int(r["fiscal_year"]) for r in wk}
    demand = {(r["node_code"], r["material_code"], r["week_id"]): float(r["cases"] or 0) for r in fetch(
        f"""select s.node_code, d.material_code, d.week_id, sum(d.cases) cases from {T('plan.unconstrained_demand')} d
            join {T('dims.ref_serving_node')} s using (ship_to_code) where d.version_id = '{v}' group by all""")}
    sourcing: dict[tuple, list] = defaultdict(list)
    for r in fetch(f"select node_code, material_code, plant_code, share from {T('plan.sourcing_rule')}"):
        sourcing[(r["node_code"], r["material_code"])].append((r["plant_code"], float(r["share"])))
    lead = {(r["from_node"], r["to_code"]): int(r["lead_weeks"]) for r in fetch(
        f"select from_node, to_code, cast(floor(transit_days / 7) as int) lead_weeks from {T('dims.ref_lane')} where to_kind = 'node'")}
    sigma = {(r["node_code"], r["material_code"]): float(r["sigma"] or 0) for r in fetch(f"select node_code, material_code, sigma from {T('plan.demand_variability')}")}
    fill = {r["material_code"]: float(r["fill_rate"]) for r in fetch(f"select material_code, fill_rate from {T('plan.service_class')} where version_id = '{v}'")}
    review = fetch(f"select review_weeks from {T('dims.ref_replenishment')} limit 1")
    typed = {(r["material_code"], r["plant_code"], r["period"]): float(r["quantity"]) for r in fetch(
        f"select material_code, plant_code, period, quantity from {T('plan.production_act')} where version_id = '{v}'")}
    kinds = {r["node_code"]: r["node_kind"] for r in fetch(f"select node_code, node_kind from {T('dims.dim_node')}")}
    return {"weeks": weeks, "period_of": period_of, "fy_of": fy_of, "demand": demand, "sourcing": dict(sourcing), "lead": lead, "sigma": sigma,
            "fill": fill, "review_weeks": int(review[0]["review_weeks"]) if review else 1, "typed": typed, "kinds": kinds}


def compute(inp: dict, version: str, demand: dict | None = None, hold: dict | None = None) -> tuple[dict, list[dict]]:
    """The flow on the inputs (or on a demand given instead — a stress test), and its rows at the period."""
    if not inp:
        return {}, []
    f = flow(inp["weeks"], inp["period_of"], demand if demand is not None else inp["demand"], inp["sourcing"], inp["lead"], inp["sigma"],
             inp["fill"], inp["review_weeks"], inp["typed"], hold)
    rows = []
    for (node, m), weekly in f["nodes"].items():
        for r in by_period(weekly, inp["weeks"], inp["period_of"]):
            rows.append({**r, "version_id": version, "node_code": node, "node_kind": inp["kinds"].get(node, ""), "material_code": m,
                         "fiscal_year": inp["fy_of"][r["period"]]})
    return f, rows
