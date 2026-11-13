"""The opex schedule at its grain — entity × the plan's cost centre × account × period: each line a driver and a rate,
each month calculated as driver × rate until someone types it.

Written once, called from two places:

- the run (`models/plan/opex_schedule.py`) computes the schedule from its inputs and every act on file, in the order
  typed;
- the face (`face/schedule_live.py`) computes the same from the same inputs, the acts on file and the person's unsaved
  acts, the moment one is typed.

Both read their inputs through `read_inputs` (the same queries, the table names resolved by the caller) and hand the
rules of `plan.ref_grid_measure` (grid `schedule`) to `rules_from`; so what the page shows before a save is what the run
makes of it after.

The rules the calculation obeys from the register: how a figure reads at a total (`rollup`: the sum of every figure
beneath; the sum of one line's months; or the line's own figure, not added across lines) and which figures are typed
(a `verb`). The formulas are written below, in `compute`, and `tests/measure_register.py` checks them against the
register's words.

An act is one of four, applied in the order typed:
  driver   the line's driver (a typed rate goes back to calculated — it was in the old driver's units; typed months stay)
  rate     the rate in use, typed over the calculated one; no value returns it to calculated
  month    a month's amount, typed — it holds; the calculated amount when it was typed is kept beside it
  reset    a typed month back to calculated, or every typed month of the line when no period is named
"""
from __future__ import annotations

from collections import defaultdict
from typing import Callable, Iterable

ROLLUPS = ("sum", "months", "line")
QUANTITY = ("cases_made_ech", "cases_made_lox", "cases_shipped", "net_sales")
DRIVERS = QUANTITY + ("none", "last_year", "labour_model")
MOVED = 0.5                    # half a dollar: a calculated amount that has moved since a month was typed
HORIZON = 12                   # periods planned after the last closed one
WINDOW = 12                    # the rolling year a rate is calculated over

COLUMNS = ["version_id", "entity_code", "cost_centre_code", "account_code", "period", "fiscal_year", "driver", "driver_qty",
           "rate_calc", "rate", "rate_typed", "amount_calc", "amount", "state", "typed_calc", "moved", "rate_edit_id", "month_edit_id"]

Line = tuple       # (entity, cost centre, account)
Rules = dict


def rules_from(rows: Iterable[dict], grid: str = "schedule") -> Rules:
    out = {r["measure"]: dict(r) for r in sorted((r for r in rows if r["grid"] == grid), key=lambda r: r["ord"])}
    for m, r in out.items():
        if r["rollup"] not in ROLLUPS:
            raise ValueError(f"{grid}.{m}: roll-up {r['rollup']!r} is not one the schedule knows")
    if not out:
        raise ValueError(f"no measures registered for the {grid} grid")
    return out


def total(cells: list[dict], measure: str, rules: Rules) -> float | None:
    """A figure read over several cells by its registered roll-up."""
    r = rules[measure]
    f = r["field"]
    vals = [c[f] for c in cells if c.get(f) is not None]
    if not vals:
        return None
    lines = {(c["entity_code"], c["cost_centre_code"], c["account_code"]) for c in cells}
    if r["rollup"] == "sum":
        return sum(vals)
    if len(lines) != 1:
        return None                                   # a line's figure is never added across lines
    return sum(vals) if r["rollup"] == "months" else vals[0]


class Inputs:
    """What the schedule is computed from (a plain class: SQLMesh carries this module into the model by its source).
      periods       planned: the next twelve after the last closed, in the version's horizon
      window        the last twelve closed
      prior         period → the same period a year earlier
      actual        (line, period) → actual, over the window
      driver_plan   (driver, period) → the version's plan quantity
      driver_actual driver → its actual over the window
      index         last year's index: 1 + CPI on the version
      labour        (line, period) → the labour model's amount; labour_lines the lines it fills"""

    def __init__(self, version, open_, periods, window, fy_of, prior, lines, actual, driver_plan, driver_actual, index):
        self.version, self.open, self.periods, self.window, self.fy_of, self.prior = version, open_, periods, window, fy_of, prior
        self.lines, self.actual, self.driver_plan, self.driver_actual, self.index = lines, actual, driver_plan, driver_actual, index
        self.labour: dict = {}
        self.labour_lines: set = set()


def read_inputs(fetch: Callable[[str], list[dict]], T: Callable[[str], str], version: str, labour: bool = True) -> Inputs:
    """The schedule's inputs, read the same way by the run and by the face. `fetch(sql)` → rows as dicts; `T(name)` the
    table a model name resolves to. `version` is a version id (no quotes in ids)."""
    v = version.replace("'", "")
    per = fetch(f"select period, fiscal_year, prior_year_period, period_state from {T('dims.dim_period')} order by period")
    closed = [p["period"] for p in per if p["period_state"] == "CLOSED"]
    window = closed[-WINDOW:]
    ver = (fetch(f"select horizon_start, horizon_end, status from {T('dims.ctl_version')} where version_id = '{v}'") or [{}])[0]
    is_open = ver.get("status") == "open"
    after = [p["period"] for p in per if p["period"] > (closed[-1] if closed else "")][:HORIZON]
    periods = [p for p in after if ver and ver["horizon_start"] <= p <= ver["horizon_end"]] if is_open else []
    fy_of = {p["period"]: int(p["fiscal_year"]) for p in per}
    prior = {p["period"]: p["prior_year_period"] for p in per}
    inn = ",".join(f"'{p}'" for p in window) or "''"
    act = fetch(f"""select entity_code, cost_centre_code, account_code, period, sum(amount) amount from {T('plan.cost_actual')}
                    where state = 'mapped' and period in ({inn}) group by all""")
    actual = {((a["entity_code"], a["cost_centre_code"], a["account_code"]), a["period"]): float(a["amount"]) for a in act}
    lines = sorted({k[0] for k in actual})
    plant = f"""(select material_code, lower(plant_code) plant from {T('dims.ref_route')} where is_primary)"""
    da = fetch(f"""select 'cases_shipped' driver, sum(s.cases) q from {T('history.shipments')} s where s.period in ({inn})
                   union all select 'net_sales', sum(s.net_sales) from {T('history.shipments')} s where s.period in ({inn})
                   union all select 'cases_made_' || r.plant, sum(s.cases) from {T('history.shipments')} s join {plant} r using (material_code)
                             where s.period in ({inn}) group by r.plant""")
    driver_actual = {d["driver"]: float(d["q"] or 0) for d in da}
    pinn = ",".join(f"'{p}'" for p in periods) or "''"
    dp = fetch(f"""select 'cases_shipped' driver, d.period, sum(d.cases) q from {T('plan.demand_financialised')} d where d.version_id = '{v}' and d.period in ({pinn}) group by all
                   union all select 'net_sales', d.period, sum(d.net_sales) from {T('plan.demand_financialised')} d where d.version_id = '{v}' and d.period in ({pinn}) group by all
                   union all select 'cases_made_' || r.plant, d.period, sum(d.cases) from {T('plan.demand_financialised')} d join {plant} r using (material_code)
                             where d.version_id = '{v}' and d.period in ({pinn}) group by all""")
    driver_plan = {(d["driver"], d["period"]): float(d["q"] or 0) for d in dp}
    # CPI in force at the first period the schedule plans (amendments included) — one index for its twelve periods; the
    # version's own value where it plans none
    first = periods[0] if periods else (ver.get("horizon_start") or "")
    cpi = fetch(f"select value from {T('plan.assumption_in_force')} where assumption_code = 'CPI' and version_id = '{v}' and period = '{first}'") or \
        fetch(f"select value from {T('dims.reg_assumption')} where assumption_code = 'CPI' and version_id = '{v}' and period = 'ALL'")
    inp = Inputs(version, is_open, periods, window, fy_of, prior, lines, actual, driver_plan, driver_actual, 1 + float(cpi[0]["value"] if cpi else 0))
    if labour:
        for r in fetch(f"""select entity_code, cost_centre_code, account_code, period, sum(amount) amount from {T('plan.labour_cost')}
                           where version_id = '{v}' group by all"""):
            line = (r["entity_code"], r["cost_centre_code"], r["account_code"])
            inp.labour[(line, r["period"])] = float(r["amount"])
            inp.labour_lines.add(line)
    return inp


def calculated_rate(inp: Inputs, line: Line, driver: str) -> float | None:
    """Line actuals ÷ driver actuals over the last twelve closed periods; a flat amount is the year ÷ 12; last year's
    rate is the index on it."""
    if driver == "last_year":
        return inp.index
    if driver == "labour_model":
        return None
    act = sum(inp.actual.get((line, p), 0.0) for p in inp.window)
    if driver == "none":
        return act / len(inp.window) if inp.window else None
    d = inp.driver_actual.get(driver) or 0.0
    return act / d if d else None


def driver_quantity(inp: Inputs, line: Line, driver: str, period: str) -> float | None:
    if driver == "none":
        return 1.0
    if driver == "last_year":
        return inp.actual.get((line, inp.prior.get(period)), 0.0)
    if driver == "labour_model":
        return None
    return inp.driver_plan.get((driver, period), 0.0)


def compute(inp: Inputs, acts: Iterable[dict], rules: Rules | None = None) -> dict[tuple, dict]:
    """Every cell of the schedule: (entity, cost centre, account, period) → its figures. Acts in the order typed."""
    driver: dict[Line, str] = {l: "last_year" for l in inp.lines}
    rate_typed: dict[Line, tuple] = {}
    typed: dict[tuple, tuple] = {}
    for e in acts:
        line = (e["entity_code"], e["cost_centre_code"], e["account_code"])
        driver.setdefault(line, "last_year")
        a, p = e["action"], e.get("period") or None
        if a == "driver":
            driver[line] = e["driver"]
            rate_typed.pop(line, None)
        elif a == "rate":
            if e.get("value") is None:
                rate_typed.pop(line, None)
            else:
                rate_typed[line] = (float(e["value"]), e["edit_id"])
        elif a == "month" and p:
            typed[(line, p)] = (float(e["value"]), None if e.get("calc_at_entry") is None else float(e["calc_at_entry"]), e["edit_id"])
        elif a == "reset":
            for k in [k for k in typed if k[0] == line and (p is None or k[1] == p)]:
                typed.pop(k)
    for line in inp.labour_lines:
        driver[line] = "labour_model"
    out: dict[tuple, dict] = {}
    for line, d in driver.items():
        if d not in DRIVERS:
            raise ValueError(f"{line}: driver {d!r} is not one the schedule knows")
        rc = calculated_rate(inp, line, d)
        rt = rate_typed.get(line) if d != "labour_model" else None
        rate = rt[0] if rt else rc
        for p in inp.periods:
            q = driver_quantity(inp, line, d, p)
            if d == "labour_model":
                calc = inp.labour.get((line, p), 0.0)               # the labour model's amount: not typed here
            else:
                calc = q * rate if q is not None and rate is not None else None
            t = typed.get((line, p)) if d != "labour_model" else None
            amount = t[0] if t else calc
            moved = bool(t and t[1] is not None and calc is not None and abs(calc - t[1]) > MOVED)
            out[(*line, p)] = {"version_id": inp.version, "entity_code": line[0], "cost_centre_code": line[1], "account_code": line[2],
                               "period": p, "fiscal_year": inp.fy_of.get(p), "driver": d, "driver_qty": q, "rate_calc": rc, "rate": rate,
                               "rate_typed": bool(rt), "amount_calc": calc, "amount": amount,
                               "state": "model" if d == "labour_model" else ("typed" if t else "calculated"),
                               "typed_calc": t[1] if t else None, "moved": moved, "rate_edit_id": rt[1] if rt else None,
                               "month_edit_id": t[2] if t else None}
    return out


def lines_of(cells: dict[tuple, dict]) -> dict[Line, list[dict]]:
    by: dict[Line, list[dict]] = defaultdict(list)
    for c in cells.values():
        by[(c["entity_code"], c["cost_centre_code"], c["account_code"])].append(c)
    return by
