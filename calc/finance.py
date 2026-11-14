"""Finance's plan at its grain — account × material × period: volume, price and revenue, with the demand plan beneath;
cost of goods and margin where a standard cost per case is known.

Written once, called from two places:

- the run (`models/plan/finance_plan.py`) starts each fed cell at the demand plan valued and replays every figure on
  file, in the order typed;
- the face (`face/finance_live.py`) applies one figure to a person's working copy the moment it is typed.

Both go through `Grid.type` (a figure typed at a node, spread to the cells beneath it) and `Grid.put` (a value at the
grain), so what the grid shows before a save is what the run makes of it after. A figure typed above the grain is
spread at the moment of typing and kept as that spread: the parent is then the sum of its children, a later figure
anywhere beneath or above simply overwrites the cells it reaches, and the mix is fixed as it was when typed.

A version's actual periods — up to its from point — take nothing: given the from point (`actual_through`), the grid
writes no figure into one, whoever asks and at whatever node, so a figure typed above the grain reaches plan periods only.

The rules are a register, `plan.ref_grid_measure`, which both callers read from the warehouse and hand to the grid
(`rules_from`). The grid obeys its settings — how a figure reads at a total (`rollup`), how one typed at a total spreads
(`breakback`) and so which figures are typed — and keeps no copy of them. The formulas are not read from the register:
they are written below, in `_revalue`, and `tests/measure_register.py` checks them against the register's words.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Callable, Iterable

ROLLUPS = ("sum", "ratio")
BREAKBACKS = ("source_shape", "proportional", None)
NEGLIGIBLE = {"count": 0.5, "rate": 0.005, "money": 0.005}    # half a case, half a cent: a figure that changes nothing

COLUMNS = ["version_id", "account_code", "material_code", "period", "fiscal_year", "source", "source_cases", "source_net_sales",
           "source_price", "cases", "price", "net_sales", "std_cost", "cogs", "margin", "volume_edit_id", "price_edit_id"]

Key = tuple   # (version, account, material, period)
Rules = dict  # measure → its register row


def rules_from(rows: Iterable[dict], grid: str = "finance") -> Rules:
    """The register's rows for one grid, in order, keyed by measure — checked for settings the grid knows."""
    out = {r["measure"]: dict(r) for r in sorted((r for r in rows if r["grid"] == grid), key=lambda r: r["ord"])}
    for m, r in out.items():
        if r["rollup"] not in ROLLUPS or r["breakback"] not in BREAKBACKS:
            raise ValueError(f"{grid}.{m}: roll-up {r['rollup']!r} / spread {r['breakback']!r} is not one the calculation knows")
        if r["rollup"] == "ratio" and (r["rollup_num"] not in out or r["rollup_den"] not in out):
            raise ValueError(f"{grid}.{m}: a ratio of {r['rollup_num']} ÷ {r['rollup_den']}, which are not measures of the grid")
    if not out:
        raise ValueError(f"no measures registered for the {grid} grid")
    return out


def typed(rules: Rules) -> list[str]:
    """The measures a person types: those with a spread."""
    return [m for m, r in rules.items() if r["breakback"]]


def aggregate(cells: Iterable[dict], measure: str, rules: Rules, source: bool = False) -> float | None:
    """A measure read at a node: the cells beneath it rolled up by the measure's registered rule."""
    r = rules[measure]
    cells = cells if isinstance(cells, list) else list(cells)
    if r["rollup"] == "sum":
        f = r["source_field" if source else "field"]
        if not f:
            return None
        vals = [c[f] for c in cells if c.get(f) is not None]
        return sum(vals) if vals else None
    a, b = aggregate(cells, r["rollup_num"], rules, source), aggregate(cells, r["rollup_den"], rules, source)
    return a / b if a is not None and b not in (None, 0) else None


class Grid:
    """The cells of Finance's plan and the two operations on them. A copy shares its cells with the grid it was copied
    from until it writes one — a person's working copy costs only the cells they have changed."""

    def __init__(self, accounts_under: dict[str, set], materials_under: dict[str, set], source_of: Callable[[str, str], str],
                 fy_of: dict[str, int], rules: Rules, actual_through: dict[str, str] | None = None):
        self.accounts_under, self.materials_under, self.source_of, self.fy_of = accounts_under, materials_under, source_of, fy_of
        self.rules = rules
        self.actual_through = dict(actual_through or {})                # version → its from point: the last actual period
        self.cells: dict[Key, dict] = {}
        self.by_period: dict[tuple, list[Key]] = defaultdict(list)    # (version, period) → its cells, for scope matching
        self._owned: set | None = None                                  # None: every cell is this grid's own

    # ---- building ----
    def start(self, key: Key, src: str, source_cases: float | None, source_net_sales: float | None, **now) -> dict:
        """A cell. Fed: the source is the demand plan valued and the cell starts as it. Built: no source. The standard cost
        per case comes from the cost of goods step's source, which Caldera has not built: none, unless given."""
        price = source_net_sales / source_cases if source_cases not in (None, 0) and source_net_sales is not None else None
        c = {"version_id": key[0], "account_code": key[1], "material_code": key[2], "period": key[3], "fiscal_year": self.fy_of.get(key[3]),
             "source": src, "source_cases": source_cases, "source_net_sales": source_net_sales, "source_price": price,
             "cases": source_cases if source_cases is not None else 0.0, "price": price, "net_sales": source_net_sales,
             "std_cost": None, "cogs": None, "margin": None, "volume_edit_id": None, "price_edit_id": None}
        c.update(now)
        self.cells[key] = c
        if self._owned is None:
            self.by_period[(key[0], key[3])].append(key)
        else:                                                           # never append to a list the base still shares
            self.by_period[(key[0], key[3])] = self.by_period.get((key[0], key[3]), []) + [key]
            self._owned.add(key)
        self._revalue(c)
        return c

    def from_source(self, rows: Iterable[tuple]) -> "Grid":
        """The run's start: (version, account, material, period, cases, net_sales) of the demand plan valued — every fed cell."""
        for v, a, m, p, sc, sn in rows:
            if self.source_of(a, m) == "fed":
                self.start((v, a, m, p), "fed", float(sc or 0), float(sn or 0))
        return self

    def from_plan(self, rows: Iterable[dict]) -> "Grid":
        """The face's start: Finance's plan as the last run left it, cell for cell."""
        for r in rows:
            key = (r["version_id"], r["account_code"], r["material_code"], r["period"])
            c = dict(r)
            self.cells[key] = c
            self.by_period[(key[0], key[3])].append(key)
        return self

    def copy(self) -> "Grid":
        g = Grid(self.accounts_under, self.materials_under, self.source_of, self.fy_of, self.rules, self.actual_through)
        g.cells, g.by_period, g._owned = dict(self.cells), dict(self.by_period), set()
        return g

    # ---- the two operations ----
    def scope(self, version: str, customer: str, material: str, period: str) -> list[Key]:
        A, M = self.accounts_under.get(customer, ()), self.materials_under.get(material, ())
        return [k for k in self.by_period.get((version, period), ()) if k[1] in A and k[2] in M]

    def actual(self, version: str, period: str) -> bool:
        """An actual period of the version: at or before its from point. Nothing is written into one."""
        return period <= self.actual_through.get(version, "")

    def at_grain(self, customer: str, material: str) -> bool:
        return customer in self.accounts_under.get(customer, ()) and material in self.materials_under.get(material, ())

    def type(self, version: str, customer: str, material: str, period: str, measure: str, value: float, edit_id: str) -> list[tuple[Key, float]]:
        """A figure typed at a node: spread to every cell beneath it by the measure's breakback, and kept as that spread.
        At the grain, where nothing is yet, the cell is started — a built material, or a fed one the demand plan lacks.
        Returns the cells written and the value each now holds; none where the node has nothing in that period, and none in
        an actual period of the version."""
        if self.actual(version, period):
            return []
        if self.at_grain(customer, material) and (version, customer, material, period) not in self.cells:
            src = self.source_of(customer, material)
            self.start((version, customer, material, period), src, 0.0 if src == "fed" else None, 0.0 if src == "fed" else None)
        keys = self.scope(version, customer, material, period)
        values = self.breakback(keys, measure, value)
        for k, x in zip(keys, values):
            self.put(k, measure, x, edit_id)
        return list(zip(keys, values))

    def breakback(self, keys: list[Key], measure: str, value: float) -> list[float]:
        r = self.rules[measure]
        rule, f = r["breakback"], r["field"]
        cells = [self.cells[k] for k in keys]
        if not cells:
            return []
        if rule is None:
            raise ValueError(f"{measure} is not typed")
        if rule == "source_shape" or (rule == "proportional" and r["rollup"] == "sum"):
            # by the source's figures beneath (the cell's own where nothing feeds it), or proportionally — by the figures
            # standing now; evenly where they are all zero
            sf = r["source_field"] if rule == "source_shape" else None
            w = [max(((c[sf] if (sf and c["source"] == "fed") else c[f]) or 0.0), 0.0) for c in cells]
            W = sum(w)
            return [value * (wi / W if W > 0 else 1 / len(cells)) for wi in w]
        # proportional on a ratio: num ÷ den at the node, so den weighs each cell; one factor moves every figure beneath
        df = self.rules[r["rollup_den"]]["field"]
        priced = [c for c in cells if c[f] is not None]
        wd = sum(c[df] or 0.0 for c in priced)
        wn = sum((c[df] or 0.0) * c[f] for c in priced)
        k = value * wd / wn if wd > 0 and wn > 0 else None
        return [c[f] * k if (k is not None and c[f] is not None) else value for c in cells]

    def put(self, key: Key, measure: str, value: float, edit_id: str) -> dict:
        """A value at the grain: it stands, and the calculated measures follow."""
        c = self._own(key)
        c[self.rules[measure]["field"]] = value
        c[f"{measure}_edit_id"] = edit_id
        self._revalue(c)
        return c

    def replay(self, figures: Iterable[dict], on_record: dict[str, list[tuple]]) -> None:
        """Every figure on file, in the order typed. A figure whose spread is on record puts it, cell by cell; one saved
        before spreads were recorded is spread now, by the same rule."""
        for e in figures:
            cells = on_record.get(e["edit_id"])
            if self.actual(e["version_id"], e["period"]):
                continue                                               # an actual period takes nothing, as when typed
            if cells:
                for a, m, x in cells:
                    key = (e["version_id"], a, m, e["period"])
                    if key not in self.cells:                          # nothing feeds it now: started, as when it was typed
                        src = self.source_of(a, m)
                        self.start(key, src, 0.0 if src == "fed" else None, 0.0 if src == "fed" else None)
                    self.put(key, e["measure"], x, e["edit_id"])
            else:
                self.type(e["version_id"], e["scope_customer"], e["scope_material"], e["period"], e["measure"], e["value"], e["edit_id"])

    # ---- inside ----
    def _own(self, key: Key) -> dict:
        if self._owned is not None and key not in self._owned:
            self.cells[key] = dict(self.cells[key])
            self._owned.add(key)
        return self.cells[key]

    @staticmethod
    def _revalue(c: dict) -> None:
        """The formulas — written here, once; the register states each in words (formula_says) and a test holds the two
        together. Revenue = volume × price, except that a fed cell nothing has been typed on is exactly the demand plan
        valued, even where it has no cases. Cost of goods = volume × standard cost; margin = revenue − cost of goods."""
        if c.get("volume_edit_id") is None and c.get("price_edit_id") is None and c["source"] == "fed":
            c["net_sales"] = c["source_net_sales"]
        else:
            c["net_sales"] = c["cases"] * c["price"] if c["cases"] is not None and c["price"] is not None else None
        std = c.get("std_cost")
        c["cogs"] = c["cases"] * std if std is not None and c["cases"] is not None else None
        c["margin"] = c["net_sales"] - c["cogs"] if c["net_sales"] is not None and c["cogs"] is not None else None
