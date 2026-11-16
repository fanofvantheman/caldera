"""The material purchase plan and its stock (DEC-20261116-04): for each key raw material at a plant, period by period —
the requirement production draws, the purchase that covers it, and the stock it makes, valued at a monthly weighted
average. The model (models/plan/material_stock.py) and the face's page call the same function, so the page and the run
never disagree.

  campaign  bought in the input's campaign window for what is needed until the next window opens (or the horizon ends),
            less the stock at the window's start, spread evenly over the window's periods
  contract  the requirement plus the declared cover (that many periods of the next period's requirement) less the stock on
  spot      hand — the same quantity rule; they differ in price: a contract's is fixed, or tied to an index, for its term;
            spot is the price in force with its index
A buyer may type a quantity or a price over the calculated one in a period: it replaces it, and is marked.

Average: (opening value + purchases at their price) ÷ (opening quantity + purchases); consumption at that average; the
closing quantity and value carried to the next period. No layers, no batches."""
from __future__ import annotations

from typing import Iterable

SOURCES = ("contract", "spot", "campaign")


def blocks(periods: list[str], window: set[str]) -> list[list[str]]:
    """The runs of consecutive periods inside the campaign window, in order."""
    out, cur = [], []
    for p in periods:
        if p in window:
            cur.append(p)
        elif cur:
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    return out


def plan(periods: list[str], requirement: dict[str, float], price: dict[str, float | None], source: str, cover: float,
         opening_quantity: float, opening_cost: float, window: Iterable[str] = (), typed: dict[str, dict] | None = None) -> list[dict]:
    """One key material at one plant on one version: a row per period, in order. `requirement` and `price` by period;
    `typed` by period — {"quantity": x?, "price": y?, "act_id": ...} — replaces the calculated figure where given."""
    typed = typed or {}
    window = set(window)
    req = {p: float(requirement.get(p) or 0.0) for p in periods}
    starts: dict[str, tuple[list[str], float]] = {}      # a window's first period → (its periods, what is needed until the next opens)
    if source == "campaign":
        bs = blocks(periods, window)
        for i, b in enumerate(bs):
            until = periods.index(bs[i + 1][0]) if i + 1 < len(bs) else len(periods)
            starts[b[0]] = (b, sum(req[p] for p in periods[periods.index(b[0]):until]))
    rows, oq, ov = [], float(opening_quantity or 0.0), float(opening_quantity or 0.0) * float(opening_cost or 0.0)
    rate = 0.0
    for i, p in enumerate(periods):
        nxt = req[periods[i + 1]] if i + 1 < len(periods) else req[p]
        if source == "campaign":
            if p in starts:                                 # less the stock at the window's start, spread over the window
                b, need = starts[p]
                rate = max(0.0, need - oq) / len(b)
            q = max(rate, req[p] - oq) if p in window else 0.0       # never short inside the window
        else:
            q = max(0.0, req[p] + cover * nxt - oq)
        pr = price.get(p)
        t = typed.get(p) or {}
        q_typed, pr_typed = t.get("quantity") is not None, t.get("price") is not None
        if q_typed:
            q = float(t["quantity"])
        if pr_typed:
            pr = float(t["price"])
        pv = q * pr if pr is not None else 0.0
        avg = (ov + pv) / (oq + q) if (oq + q) > 0 else pr
        cq = req[p]
        cv = cq * avg if avg is not None else 0.0
        rows.append({"period": p, "requirement": req[p], "opening_quantity": oq, "opening_value": ov, "purchase_quantity": q, "purchase_price": pr,
                     "purchase_value": pv, "average_cost": avg, "consumption_quantity": cq, "consumption_value": cv,
                     "closing_quantity": oq + q - cq, "closing_value": ov + pv - cv, "quantity_typed": q_typed, "price_typed": pr_typed,
                     "typed_act": t.get("act_id"), "short": oq + q - cq < -1e-9})
        oq, ov = oq + q - cq, ov + pv - cv
    return rows


COLUMNS = ["version_id", "input_code", "plant_code", "period", "fiscal_year", "source", "requirement", "opening_quantity", "opening_value",
           "purchase_quantity", "purchase_price", "purchase_value", "average_cost", "consumption_quantity", "consumption_value",
           "closing_quantity", "closing_value", "quantity_typed", "price_typed", "typed_act", "short"]
TYPES = {c: "DOUBLE" for c in COLUMNS} | {"version_id": "TEXT", "input_code": "TEXT", "plant_code": "TEXT", "period": "TEXT", "fiscal_year": "INT",
                                          "source": "TEXT", "quantity_typed": "BOOLEAN", "price_typed": "BOOLEAN", "typed_act": "TEXT", "short": "BOOLEAN"}
OPENING_MARGIN = 0.05        # a campaign material opens with what it needs until its window, and this much over
MONTHS = {"Jul": 1, "Aug": 2, "Sep": 3, "Oct": 4, "Nov": 5, "Dec": 6, "Jan": 7, "Feb": 8, "Mar": 9, "Apr": 10, "May": 11, "Jun": 12}


def window_periods(spec: str | None, fiscal_period: dict[str, int]) -> set[str]:
    """The periods inside an input's campaign window ('Feb-Apr'), by fiscal period, in every year the plan covers."""
    if not spec or "-" not in spec:
        return set()
    a, b = (MONTHS[x.strip()[:3]] for x in spec.split("-", 1))
    fps = set(range(a, b + 1)) if a <= b else set(range(a, 13)) | set(range(1, b + 1))
    return {p for p, fp in fiscal_period.items() if fp in fps}


def compute_all(fetch, T, version: str | None = None, acts: list[dict] | None = None) -> list[dict]:
    """Every key material at every plant on every plan (or one plan): the inputs read through `fetch(sql)` with table names
    resolved by `T`, the typed acts given or read from plan.purchase_act."""
    where = f" and version_id = '{version}'" if version else ""
    versions = fetch(f"select version_id, from_period, plan_through from {T('dims.ctl_version')} where version_kind <> 'actual' and from_period is not null{where}")
    keys = fetch(f"""select k.*, i.campaign_window from {T('dims.ref_key_material')} k
                     join {T('dims.dim_input_material')} i on i.material_code = k.input_code order by k.input_code, k.plant_code""")
    req = {(r["version_id"], r["input_code"], r["plant_code"], r["period"]): r["quantity"] for r in fetch(f"select * from {T('plan.material_requirement')}{' where ' + where[5:] if version else ''}")}
    price = {(r["version_id"], r["input_code"], r["period"]): r["price"] for r in fetch(f"select * from {T('plan.input_price_in_force')}{' where ' + where[5:] if version else ''}")}
    idx = {(r["version_id"], r["assumption_code"], r["period"]): r["value"] for r in fetch(f"select version_id, assumption_code, period, value from {T('plan.assumption_in_force')}")}
    cal = fetch(f"select period, fiscal_year, fiscal_period from {T('dims.dim_period')} order by period")
    typed = acts if acts is not None else fetch(f"select * from {T('plan.purchase_act')}")
    out: list[dict] = []
    for v in versions:
        ps = [c for c in cal if v["from_period"] < c["period"] <= v["plan_through"]]
        periods, fp, fy = [c["period"] for c in ps], {c["period"]: c["fiscal_period"] for c in ps}, {c["period"]: c["fiscal_year"] for c in ps}
        if not periods:
            continue
        for k in keys:
            def in_term(p: str) -> bool:
                return k["source"] == "contract" and k["contract_price"] is not None and (not k["contract_through"] or p <= k["contract_through"])
            def pr(p: str):
                if in_term(p):
                    i = idx.get((v["version_id"], k["contract_index"], p), 100.0) if k["contract_index"] else 100.0
                    return float(k["contract_price"]) * float(i) / 100.0
                x = price.get((v["version_id"], k["input_code"], p))
                return None if x is None else float(x)
            rq = {p: float(req.get((v["version_id"], k["input_code"], k["plant_code"], p)) or 0.0) for p in periods}
            window = window_periods(k["campaign_window"], fp) if k["source"] == "campaign" else set()
            if window:                                       # last season's intake: what is needed until the window opens, and a margin
                until = next((i for i, p in enumerate(periods) if p in window), len(periods))
                oq = sum(rq[p] for p in periods[:until]) * (1.0 + OPENING_MARGIN)
            else:                                            # periods of requirement on hand
                head = [rq[p] for p in periods[:3]]
                oq = float(k["opening_periods"] or 0.0) * (sum(head) / len(head) if head else 0.0)
            oc = float(price.get((v["version_id"], k["input_code"], periods[0])) or 0.0) * float(k["opening_cost_factor"] or 1.0)
            ty = {a["period"]: a for a in typed if a["version_id"] == v["version_id"] and a["input_code"] == k["input_code"] and a["plant_code"] == k["plant_code"]}
            for r in plan(periods, rq, {p: pr(p) for p in periods}, k["source"], float(k["cover_periods"] or 0.0), oq, oc,
                          window, ty):
                out.append({**r, "version_id": v["version_id"], "input_code": k["input_code"], "plant_code": k["plant_code"],
                            "fiscal_year": fy[r["period"]], "source": k["source"] if k["source"] != "contract" or in_term(r["period"]) else "spot"})
    return out
