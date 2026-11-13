"""Finance's plan at its grain — account × material × period: volume, price and revenue, with the demand plan beneath.

Written once, called from two places:

- the run (`models/plan/finance_plan.py`) starts each fed cell at the demand plan valued and replays every figure on
  file, in the order typed;
- the face (`face/finance_live.py`) applies one figure to a person's working copy the moment it is typed.

Both go through `Grid.type` (a figure typed at a node, spread to the cells beneath it) and `Grid.put` (a value at the
grain), so what the grid shows before a save is what the run makes of it after. A figure typed above the grain is
spread at the moment of typing and kept as that spread: the parent is then the sum of its children, a later figure
anywhere beneath or above simply overwrites the cells it reaches, and the mix is fixed as it was when typed.

How each measure is set, read at a node above the grain, and spread when typed there is declared once, in MEASURES;
the code below reads its roll-up, its breakback and its formula from there.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Callable, Iterable

# ---- the rules, one row per measure ----
# set        — how a value at the grain comes to be (words for a reader)
# aggregate  — how it reads at a node above the grain (words); `rollup` is the same rule as the code reads it:
#              ("sum",) — the sum of the children; ("ratio", a, b) — the node's a ÷ the node's b, never stored
# spread     — what a figure typed at a node does beneath it (words); `breakback` is the same rule as the code reads it:
#              "source_shape" — split by the source's values beneath (the cell's own where nothing feeds it), evenly
#              where they are all zero; "proportional" — every value beneath moves by one factor so the node reads what
#              was typed, a cell with no value taking the typed one; None — not typed
# formula    — a measure that is calculated at the grain from two others: ("product", a, b)
MEASURES: dict[str, dict] = {
    "volume": {
        "label": "cases", "field": "cases", "source_field": "source_cases",
        "set": "typed, or from the source: the demand plan's cases",
        "aggregate": "the sum of its children", "rollup": ("sum",),
        "spread": "by the source's volumes beneath it (Finance's own where built); evenly where they are all zero", "breakback": "source_shape",
        "formula": None,
    },
    "price": {
        "label": "net / case", "field": "price", "source_field": "source_price",
        "set": "typed, or from the source: the demand plan's net sales ÷ its cases",
        "aggregate": "calculated: revenue ÷ volume", "rollup": ("ratio", "revenue", "volume"),
        "spread": "proportionally: every price beneath moves by one factor, so the node reads what was typed; a cell with no price takes it",
        "breakback": "proportional", "formula": None,
    },
    "revenue": {
        "label": "net sales", "field": "net_sales", "source_field": "source_net_sales",
        "set": "calculated: volume × price — the demand plan's own net sales where nothing has been typed",
        "aggregate": "the sum of its children", "rollup": ("sum",),
        "spread": "not typed", "breakback": None,
        "formula": ("product", "volume", "price"),
    },
}
TYPED = [m for m, r in MEASURES.items() if r["breakback"]]                  # the measures a person types
TOLERANCE = {"volume": 0.5, "price": 0.005}                                  # half a case, half a cent: a figure that changes nothing

COLUMNS = ["version_id", "account_code", "material_code", "period", "fiscal_year", "source", "source_cases", "source_net_sales",
           "source_price", "cases", "price", "net_sales", "volume_edit_id", "price_edit_id"]

Key = tuple   # (version, account, material, period)


def aggregate(cells: Iterable[dict], measure: str, source: bool = False) -> float | None:
    """A measure read at a node: the cells beneath it rolled up by the measure's declared rule."""
    rule = MEASURES[measure]["rollup"]
    cells = cells if isinstance(cells, list) else list(cells)
    if rule[0] == "sum":
        f = MEASURES[measure]["source_field" if source else "field"]
        vals = [c[f] for c in cells if c.get(f) is not None]
        return sum(vals) if vals else None
    if rule[0] == "ratio":
        a, b = aggregate(cells, rule[1], source), aggregate(cells, rule[2], source)
        return a / b if a is not None and b not in (None, 0) else None
    raise ValueError(f"unknown roll-up {rule!r} for {measure}")


class Grid:
    """The cells of Finance's plan and the two operations on them. A copy shares its cells with the grid it was copied
    from until it writes one — a person's working copy costs only the cells they have changed."""

    def __init__(self, accounts_under: dict[str, set], materials_under: dict[str, set], source_of: Callable[[str, str], str],
                 fy_of: dict[str, int]):
        self.accounts_under, self.materials_under, self.source_of, self.fy_of = accounts_under, materials_under, source_of, fy_of
        self.cells: dict[Key, dict] = {}
        self.by_period: dict[tuple, list[Key]] = defaultdict(list)    # (version, period) → its cells, for scope matching
        self._owned: set | None = None                                  # None: every cell is this grid's own

    # ---- building ----
    def start(self, key: Key, src: str, source_cases: float | None, source_net_sales: float | None, **now) -> dict:
        """A cell. Fed: the source is the demand plan valued and the cell starts as it. Built: no source."""
        price = source_net_sales / source_cases if source_cases not in (None, 0) and source_net_sales is not None else None
        c = {"version_id": key[0], "account_code": key[1], "material_code": key[2], "period": key[3], "fiscal_year": self.fy_of.get(key[3]),
             "source": src, "source_cases": source_cases, "source_net_sales": source_net_sales, "source_price": price,
             "cases": source_cases if source_cases is not None else 0.0, "price": price, "net_sales": source_net_sales,
             "volume_edit_id": None, "price_edit_id": None}
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
        g = Grid(self.accounts_under, self.materials_under, self.source_of, self.fy_of)
        g.cells, g.by_period, g._owned = dict(self.cells), dict(self.by_period), set()
        return g

    # ---- the two operations ----
    def scope(self, version: str, customer: str, material: str, period: str) -> list[Key]:
        A, M = self.accounts_under.get(customer, ()), self.materials_under.get(material, ())
        return [k for k in self.by_period.get((version, period), ()) if k[1] in A and k[2] in M]

    def at_grain(self, customer: str, material: str) -> bool:
        return customer in self.accounts_under.get(customer, ()) and material in self.materials_under.get(material, ())

    def type(self, version: str, customer: str, material: str, period: str, measure: str, value: float, edit_id: str) -> list[tuple[Key, float]]:
        """A figure typed at a node: spread to every cell beneath it by the measure's breakback, and kept as that spread.
        At the grain, where nothing is yet, the cell is started — a built material, or a fed one the demand plan lacks.
        Returns the cells written and the value each now holds; none where the node has nothing in that period."""
        if self.at_grain(customer, material) and (version, customer, material, period) not in self.cells:
            src = self.source_of(customer, material)
            self.start((version, customer, material, period), src, 0.0 if src == "fed" else None, 0.0 if src == "fed" else None)
        keys = self.scope(version, customer, material, period)
        values = self.breakback(keys, measure, value)
        for k, x in zip(keys, values):
            self.put(k, measure, x, edit_id)
        return list(zip(keys, values))

    def breakback(self, keys: list[Key], measure: str, value: float) -> list[float]:
        rule, f = MEASURES[measure]["breakback"], MEASURES[measure]["field"]
        cells = [self.cells[k] for k in keys]
        if not cells:
            return []
        if rule == "source_shape":
            sf = MEASURES[measure]["source_field"]
            w = [max((c[sf] if c["source"] == "fed" else c[f]) or 0.0, 0.0) for c in cells]
            W = sum(w)
            return [value * (wi / W if W > 0 else 1 / len(cells)) for wi in w]
        if rule == "proportional":
            _, num, den = MEASURES[measure]["rollup"]               # a ratio: num ÷ den at the node, so den weighs each cell
            df = MEASURES[den]["field"]
            priced = [c for c in cells if c[f] is not None]
            wd = sum(c[df] or 0.0 for c in priced)
            wn = sum((c[df] or 0.0) * c[f] for c in priced)
            k = value * wd / wn if wd > 0 and wn > 0 else None
            return [c[f] * k if (k is not None and c[f] is not None) else value for c in cells]
        raise ValueError(f"{measure} is not typed")

    def put(self, key: Key, measure: str, value: float, edit_id: str) -> dict:
        """A value at the grain: it stands, and the calculated measures follow."""
        c = self._own(key)
        c[MEASURES[measure]["field"]] = value
        c[f"{measure}_edit_id"] = edit_id
        self._revalue(c)
        return c

    def replay(self, figures: Iterable[dict], on_record: dict[str, list[tuple]]) -> None:
        """Every figure on file, in the order typed. A figure whose spread is on record puts it, cell by cell; one saved
        before spreads were recorded is spread now, by the same rule."""
        for e in figures:
            cells = on_record.get(e["edit_id"])
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

    def _revalue(self, c: dict) -> None:
        untouched = all(c.get(f"{m}_edit_id") is None for m in TYPED)
        for m, r in MEASURES.items():
            if not r["formula"]:
                continue
            op, a, b = r["formula"]
            if untouched and c["source"] == "fed":
                c[r["field"]] = c[r["source_field"]]                   # exactly the demand plan valued, even where it has no cases
                continue
            x, y = c[MEASURES[a]["field"]], c[MEASURES[b]["field"]]
            c[r["field"]] = x * y if (op == "product" and x is not None and y is not None) else None
