"""Finance's grid as a person types into it: their working copy of Finance's plan, recalculated in the app the moment a
figure is typed, by the same function the run uses (`calc.finance`). Nothing here is the record — a working copy lives
in this process until it is saved (a file in the landing, then the scoped run) or discarded, and a restart loses it.

The base every copy starts from is Finance's plan as the last run left it, with any saved figures the run has not yet
taken in replayed over it — read once per run and shared; a copy holds only the cells its owner has changed. A copy
made before a run is rebased onto the new plan by replaying its figures' cells, so the mix stays as it was typed.
"""
from __future__ import annotations

import csv
import datetime as dt
import threading
from collections import defaultdict
from dataclasses import dataclass, field

from chassis import CONFIG
from chassis.warehouse import q
from chassis.working import Copies

from calc.finance import MEASURES, TOLERANCE, Grid, aggregate

COPIES = Copies()
_BASE: dict[str, tuple[tuple, Grid]] = {}
_BASE_LOCK = threading.Lock()


def _structures() -> tuple[dict, dict, dict, dict]:
    accounts_under: dict[str, set] = defaultdict(set)
    for r in q("select ancestor_code a, descendant_code d from dims.dim_customer_hierarchy where descendant_level = 'account'"):
        accounts_under[r["a"]].add(r["d"])
    materials_under: dict[str, set] = defaultdict(set)
    for r in q("select ancestor_code a, descendant_code d from dims.dim_material_hierarchy where descendant_level = 'material'"):
        materials_under[r["a"]].add(r["d"])
    declared = {(r["account_code"], r["material_code"]): r["source"] for r in q("select account_code, material_code, source from plan.finance_source where valid")}
    fy_of = {r["period"]: int(r["fiscal_year"]) for r in q("select period, fiscal_year from dims.dim_period")}
    return dict(accounts_under), dict(materials_under), declared, fy_of


def _pending_rows(landing, version: str) -> tuple[list[dict], dict[str, list]]:
    """Saved figures the last run has not taken in: (figures in the order typed, their cells by figure)."""
    figures, cells = [], defaultdict(list)
    for path in landing.pending():
        with open(path, newline="") as fh:
            for r in csv.DictReader(fh):
                if r.get("version_id") != version:
                    continue
                if r["action"] == "enter":
                    figures.append({**r, "value": float(r["value"])})
                elif r["action"] == "cell":
                    cells[r["typed"]].append((r["scope_customer"], r["scope_material"], float(r["value"])))
    figures.sort(key=lambda e: (e["entered_on"], e["edit_id"]))
    return figures, cells


def base(version: str, landing) -> tuple[tuple, Grid]:
    """Finance's plan as the last run left it, plus what is saved and waiting for the run. Shared; never written."""
    stamp = (CONFIG.db.stat().st_mtime if CONFIG.db.exists() else 0, tuple(p.name for p in landing.pending()))
    with _BASE_LOCK:
        hit = _BASE.get(version)
        if hit and hit[0] == stamp:
            return hit
        acc, mat, declared, fy_of = _structures()
        def source_of(a: str, m: str) -> str:
            return declared.get((a, m)) or declared.get((a, "ALL")) or "fed"
        g = Grid(acc, mat, source_of, fy_of).from_plan(q("select * from plan.finance_plan where version_id = ?", version))
        figures, cells = _pending_rows(landing, version)
        g.replay(figures, cells)
        _BASE[version] = (stamp, g)
        return _BASE[version]


@dataclass
class Typed:
    """One figure typed into the working copy, and the cells it wrote — what a save puts on record."""
    n: int
    customer: str
    material: str
    period: str
    measure: str
    value: float
    source_at_entry: float | None
    at: str
    cells: list[tuple] = field(default_factory=list)      # (account, material, value, source at the cell then)

    @property
    def edit_id(self) -> str:
        return f"W-{self.n:04d}"


@dataclass
class WorkingCopy:
    version: str
    stamp: tuple
    grid: Grid
    typed: list[Typed] = field(default_factory=list)
    touched: dict[str, set] = field(default_factory=lambda: defaultdict(set))
    n: int = 0

    def unsaved(self) -> bool:
        return bool(self.typed)


def working_copy(who: str, version: str, landing, create: bool = False) -> WorkingCopy | None:
    """The person's copy of this version — made on their first edit; rebased if a run has changed the plan since."""
    key = ("finance", version)
    wc = COPIES.get(who, key)
    if wc is None and not create:
        return None
    stamp, g = base(version, landing)
    if wc is None:
        return COPIES.open(who, key, lambda: WorkingCopy(version, stamp, g.copy()))
    if wc.stamp != stamp:                        # a run since: the same figures, their cells put again on the new plan
        wc.grid, wc.stamp, wc.touched = g.copy(), stamp, defaultdict(set)
        for t in wc.typed:
            for a, m, x, _ in t.cells:
                key_ = (version, a, m, t.period)
                if key_ not in wc.grid.cells:
                    src = wc.grid.source_of(a, m)
                    wc.grid.start(key_, src, 0.0 if src == "fed" else None, 0.0 if src == "fed" else None)
                wc.grid.put(key_, t.measure, x, t.edit_id)
                _touch(wc, key_, t.measure)
    return wc


def discard(who: str, version: str) -> bool:
    return COPIES.drop(who, ("finance", version))


def _touch(wc: WorkingCopy, key: tuple, measure: str) -> None:
    wc.touched[measure].add(key)
    for m, r in MEASURES.items():
        if r["formula"] and measure in r["formula"][1:]:
            wc.touched[m].add(key)


def node_value(grid: Grid, version: str, customer: str, material: str, period: str, measure: str, source: bool = False) -> float | None:
    keys = grid.scope(version, customer, material, period)
    cells = [grid.cells[k] for k in keys]
    if source:
        cells = [c for c in cells if c["source"] == "fed"]
        if not cells:
            return None
    return aggregate(cells, measure, source)


def type_figure(wc: WorkingCopy, customer: str, material: str, period: str, measure: str, value: float) -> Typed | None:
    """One figure into the working copy: spread beneath its node by the rules, kept as that spread. Nothing changes —
    and nothing is recorded — when the node already reads the figure or has nothing beneath it in that period."""
    g, v = wc.grid, wc.version
    now = node_value(g, v, customer, material, period, measure)
    if now is not None and abs(now - value) < TOLERANCE[measure]:
        return None
    if not g.scope(v, customer, material, period) and not g.at_grain(customer, material):
        return None
    src_then = node_value(g, v, customer, material, period, measure, source=True)
    wc.n += 1
    t = Typed(wc.n, customer, material, period, measure, value, src_then, dt.datetime.now().isoformat(timespec="seconds"))
    sf = MEASURES[measure]["source_field"]
    written = g.type(v, customer, material, period, measure, value, t.edit_id)
    t.cells = [(k[1], k[2], x, g.cells[k][sf] if g.cells[k]["source"] == "fed" else None) for k, x in written]
    for k, _ in written:
        _touch(wc, k, measure)
    # the same node, period and measure typed again: the earlier figure's cells are all overwritten — keep the later only
    wc.typed = [e for e in wc.typed if (e.customer, e.material, e.period, e.measure) != (customer, material, period, measure)]
    wc.typed.append(t)
    return t


def rows_for_save(wc: WorkingCopy, save_id: str, stamp: dt.datetime, who: str, reason: str, note: str) -> list[dict]:
    """The save as one file: an `enter` row per figure typed, in the order typed, and a `cell` row per cell it wrote."""
    rows, on = [], stamp.isoformat(timespec="microseconds")
    common = {"withdraws": "", "save_id": save_id, "version_id": wc.version, "reason_code": reason, "entered_by": who, "entered_on": on}
    for i, t in enumerate(wc.typed, start=1):
        eid = f"{save_id.replace('FS-', 'FE-')}-{i:03d}"
        rows.append({**common, "edit_id": eid, "action": "enter", "scope_customer": t.customer, "scope_material": t.material, "period": t.period,
                     "measure": t.measure, "value": repr(t.value), "source_at_entry": None if t.source_at_entry is None else repr(t.source_at_entry),
                     "note": note, "typed": ""})
        for j, (a, m, x, s) in enumerate(t.cells, start=1):
            rows.append({**common, "edit_id": f"{eid}-C{j:04d}", "action": "cell", "scope_customer": a, "scope_material": m, "period": t.period,
                         "measure": t.measure, "value": repr(x), "source_at_entry": None if s is None else repr(s), "note": "", "typed": eid})
    return rows
