"""Finance's grid as a person types into it: their working copy of Finance's plan, recalculated in the app the moment a
figure is typed, by the same function the run uses (`calc.finance`). Nothing here is the record — a working copy lives
in this process until it is saved (a file in the landing, then the scoped run) or discarded, and a restart loses it.

The base every copy starts from is Finance's plan as the last run left it, with any saved figures the run has not yet
taken in replayed over it — read once per run and shared; a copy holds only the cells its owner has changed. A copy
made before a run is rebased onto the new plan by replaying its figures' cells, so the mix stays as it was typed.

Undo and redo before a save: the copy keeps every step its owner took, in order (`chassis.working.History`). Undo drops
the last step and puts the rest again on the plan as saved — the cells each figure wrote when it was typed, in order, so
an earlier figure a later one had written over comes back; redo puts the step back. Nothing is recorded: nothing was
released.
"""
from __future__ import annotations

import csv
import datetime as dt
import threading
from collections import defaultdict
from dataclasses import dataclass, field

from chassis import CONFIG
from chassis.warehouse import q
from chassis.working import Copies, History

from calc.finance import NEGLIGIBLE, Grid, aggregate, rules_from

COPIES = Copies()
_BASE: dict[str, tuple[tuple, Grid]] = {}
_BASE_LOCK = threading.RLock()
_RULES: dict = {}


def rules() -> dict:
    """The finance grid's rows of the measure register, as the last run left it — the rules the run applied to the plan
    every working copy starts from. Read once per run."""
    stamp = CONFIG.db.stat().st_mtime if CONFIG.db.exists() else 0
    with _BASE_LOCK:
        if _RULES.get("stamp") != stamp:
            _RULES.update(stamp=stamp, rules=rules_from(q("select * from plan.ref_grid_measure order by grid, ord")))
        return _RULES["rules"]


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
        # the version's from point: the grid writes nothing into an actual period, at whatever node a figure is typed
        upto = {r["version_id"]: r["from_period"] for r in q("select version_id, from_period from dims.ctl_version where version_id = ? and from_period is not null", version)}
        g = Grid(acc, mat, source_of, fy_of, rules(), upto).from_plan(q("select * from plan.finance_plan where version_id = ?", version))
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
    base: Grid | None = None                     # the shared plan this copy was made from: what "unsaved" is read against
    history: History = field(default_factory=History)      # every step taken, in order, and those undone

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
        return COPIES.open(who, key, lambda: WorkingCopy(version, stamp, g.copy(), base=g))
    if wc.stamp != stamp:                        # a run since: the same figures, their cells put again on the new plan
        wc.stamp, wc.base = stamp, g
        _rebuild(wc)
    return wc


def _put_again(wc: WorkingCopy, t: Typed) -> None:
    """A figure's cells as they were written when it was typed, put again on the copy — not spread again, so the mix is
    the one typed."""
    written = []
    for a, m, x, _ in t.cells:
        key = (wc.version, a, m, t.period)
        if key not in wc.grid.cells:
            src = wc.grid.source_of(a, m)
            wc.grid.start(key, src, 0.0 if src == "fed" else None, 0.0 if src == "fed" else None)
        wc.grid.put(key, t.measure, x, t.edit_id)
        written.append((key, x))
    _settle(wc, t, written)


def _rebuild(wc: WorkingCopy) -> None:
    """The copy made again from the plan as saved and every step still done, in order."""
    g = wc.base
    wc.grid, wc.touched, wc.typed = g.copy(), defaultdict(set), []
    for t in wc.history.flat():
        _put_again(wc, t)


def undo(wc: WorkingCopy) -> list[Typed] | None:
    """The last step taken out of the copy: the plan as saved, with every earlier step put on it again."""
    step = wc.history.undo()
    if step is not None:
        _rebuild(wc)
    return step


def redo(wc: WorkingCopy) -> list[Typed] | None:
    """The last step undone, put back as it was typed."""
    step = wc.history.redo()
    for t in step or []:
        _put_again(wc, t)
    return step


def discard(who: str, version: str) -> bool:
    return COPIES.drop(who, ("finance", version))


def _touch(wc: WorkingCopy, base_grid: Grid, key: tuple, measure: str) -> None:
    """Mark the cell unsaved for the measure typed and for every other figure of it that now differs from the plan as
    saved — the calculated ones the typed figure moved."""
    wc.touched[measure].add(key)
    was, now = base_grid.cells.get(key) or {}, wc.grid.cells[key]
    for m, r in wc.grid.rules.items():
        if m != measure and was.get(r["field"]) != now.get(r["field"]):
            wc.touched[m].add(key)


def node_value(grid: Grid, version: str, customer: str, material: str, period: str, measure: str, source: bool = False) -> float | None:
    keys = grid.scope(version, customer, material, period)
    cells = [grid.cells[k] for k in keys]
    if source:
        cells = [c for c in cells if c["source"] == "fed"]
        if not cells:
            return None
    return aggregate(cells, measure, grid.rules, source)


def type_figure(wc: WorkingCopy, customer: str, material: str, period: str, measure: str, value: float, join: bool = False) -> Typed | None:
    """One figure into the working copy: spread beneath its node by the rules, kept as that spread. Nothing changes —
    and nothing is recorded — when the node already reads the figure or has nothing beneath it in that period. It is one
    step for undo, or part of the step just taken (`join`: a material started is its volume and its price)."""
    g, v = wc.grid, wc.version
    now = node_value(g, v, customer, material, period, measure)
    if now is not None and abs(now - value) < NEGLIGIBLE[g.rules[measure]["shown_as"]]:
        return None
    if not g.scope(v, customer, material, period) and not g.at_grain(customer, material):
        return None
    src_then = node_value(g, v, customer, material, period, measure, source=True)
    wc.n += 1
    t = Typed(wc.n, customer, material, period, measure, value, src_then, dt.datetime.now().isoformat(timespec="seconds"))
    sf = g.rules[measure]["source_field"]
    written = g.type(v, customer, material, period, measure, value, t.edit_id)
    t.cells = [(k[1], k[2], x, g.cells[k][sf] if g.cells[k]["source"] == "fed" else None) for k, x in written]
    wc.history.take([t], join=join)
    _settle(wc, t, written)
    return t


def _settle(wc: WorkingCopy, t: Typed, written: list[tuple]) -> None:
    """What a figure's cells, once written, do to the copy's marks and its list of figures to save."""
    g, period, measure = wc.grid, t.period, t.measure
    base_grid = wc.base or g
    for k, _ in written:
        _touch(wc, base_grid, k, measure)
    # an earlier figure in the same period and measure whose every cell this one has written over is gone — the same node
    # typed again, or a child under a parent typed since; it no longer stands anywhere, so it is not saved or marked typed
    mine = {(k[1], k[2]) for k, _ in written}
    wc.typed = [e for e in wc.typed if not (e.period == period and e.measure == measure and {(a, m) for a, m, _, _ in e.cells} <= mine)]
    wc.typed.append(t)
    # a cell typed back to what was saved is no longer a change: unmarked, and a figure all of whose cells are as saved
    # is dropped — the copy keeps only what differs from the plan
    for k, _ in written:
        was, now = base_grid.cells.get(k), g.cells[k]
        if was is not None and all(_same(was.get(r["field"]), now.get(r["field"])) for r in g.rules.values()):
            for m in wc.touched:
                wc.touched[m].discard(k)
    if all(base_grid.cells.get(k) is not None and _same(base_grid.cells[k].get(g.rules[measure]["field"]), g.cells[k].get(g.rules[measure]["field"]))
           for k, _ in written):
        wc.typed = [e for e in wc.typed if e is not t]


def _same(a, b) -> bool:
    if a is None or b is None:
        return a is b
    return abs(a - b) < 1e-6 * max(1.0, abs(a))


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


def without(version: str, named: str) -> list[dict]:
    """What withdrawing a save, or one figure, would change — before anyone confirms it. Finance's plan is made again as
    the run makes it — the demand plan valued, then every figure in force replayed in the order typed — leaving out the
    figures `named` covers (a save's every figure, or the one), and laid against the plan as the last run left it. A
    figure the withdrawn one had written over comes back where it reached; nothing needs a rule of its own. Returns the
    cells that change, each with its figures before and after."""
    acc, mat, declared, fy_of = _structures()
    def source_of(a: str, m: str) -> str:
        return declared.get((a, m)) or declared.get((a, "ALL")) or "fed"
    upto = {r["version_id"]: r["from_period"] for r in q("select version_id, from_period from dims.ctl_version where version_id = ? and from_period is not null", version)}
    now = {(r["version_id"], r["account_code"], r["material_code"], r["period"]): r for r in q("select * from plan.finance_plan where version_id = ?", version)}
    g = Grid(acc, mat, source_of, fy_of, rules(), upto).from_source(
        (k[0], k[1], k[2], k[3], r["source_cases"], r["source_net_sales"]) for k, r in now.items() if r["source"] == "fed")
    figures = [f for f in q("""select edit_id, save_id, version_id, scope_customer, scope_material, period, measure, value from plan.finance_edit
                               where version_id = ? and state = 'in_force' order by entered_on, edit_id""", version)
               if named not in (f["edit_id"], f["save_id"])]
    on_record: dict[str, list] = defaultdict(list)
    for r in q("select typed, account_code, material_code, value from plan.finance_edit_cell where version_id = ? order by edit_id", version):
        on_record[r["typed"]].append((r["account_code"], r["material_code"], float(r["value"])))
    g.replay(figures, on_record)
    out = []
    for k in sorted(set(now) | set(g.cells)):
        a, b = now.get(k) or {}, g.cells.get(k) or {}
        if any(not _same(a.get(f), b.get(f)) for f in ("cases", "price", "net_sales")):
            out.append({"account_code": k[1], "material_code": k[2], "period": k[3], "cases_now": a.get("cases"), "cases_after": b.get("cases"),
                        "price_now": a.get("price"), "price_after": b.get("price"), "net_sales_now": a.get("net_sales"), "net_sales_after": b.get("net_sales")})
    return out
