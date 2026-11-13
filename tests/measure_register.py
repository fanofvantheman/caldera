"""The measure register and the calculation agree — checked against the warehouse, without the face.

    uv run python -m tests.measure_register          # from build/, with the warehouse built; read only, a few seconds

1. Every formula the register states in words has a check here that proves the calculation does exactly that — on every
   cell of Finance's plan as the run left it, and on a small grid where the figures the plan cannot have yet (a standard
   cost) are given. A row whose words change without a check that proves them fails; so does a check left for words no
   row says any more.
2. Every setting's words match the setting: a sum says so, a ratio names its two figures, a spread says how.
3. The settings drive: the same figures typed into the same small grid behave differently when a row's spread or roll-up
   is changed — the calculation obeys the register, it does not keep its own copy.
"""
from __future__ import annotations

import sys
from pathlib import Path

BUILD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BUILD))

import chassis                                        # noqa: E402
from chassis.warehouse import q                       # noqa: E402

from calc.finance import Grid, aggregate, rules_from, typed   # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
CENT = 0.005


def close(a, b, tol=1e-6) -> bool:
    return (a is None and b is None) or (a is not None and b is not None and abs(a - b) <= tol * max(1.0, abs(b)))


# ---- one check per formula, keyed by the words the register uses for it ----
def revenue_is_volume_times_price(c: dict) -> bool:
    if c["volume_edit_id"] is None and c["price_edit_id"] is None and c["source"] == "fed":
        return close(c["net_sales"], c["source_net_sales"])            # the demand plan's own net sales where nothing is typed
    if c["cases"] is None or c["price"] is None:
        return c["net_sales"] is None
    return close(c["net_sales"], c["cases"] * c["price"])


def cogs_is_volume_times_standard(c: dict) -> bool:
    if c.get("std_cost") is None or c["cases"] is None:
        return c.get("cogs") is None
    return close(c["cogs"], c["cases"] * c["std_cost"])


def margin_is_revenue_less_cogs(c: dict) -> bool:
    if c["net_sales"] is None or c.get("cogs") is None:
        return c.get("margin") is None
    return close(c["margin"], c["net_sales"] - c["cogs"])


FORMULAS = {
    ("finance", "revenue", "volume × price"): revenue_is_volume_times_price,
    ("finance", "cogs", "volume × standard cost"): cogs_is_volume_times_standard,
    ("finance", "margin", "revenue − cost of goods"): margin_is_revenue_less_cogs,
}


def small_grid(rules: dict, std: float | None = None) -> Grid:
    """One account, two materials, one period: M1 fed by 100 cases at 10.00, M2 by 300 at 20.00."""
    g = Grid({"ALL": {"A1"}, "A1": {"A1"}}, {"ALL": {"M1", "M2"}, "M1": {"M1"}, "M2": {"M2"}}, lambda a, m: "fed", {"P1": 2027}, rules)
    g.start(("V", "A1", "M1", "P1"), "fed", 100.0, 1000.0, std_cost=std)
    g.start(("V", "A1", "M2", "P1"), "fed", 300.0, 6000.0, std_cost=None if std is None else std * 2)
    return g


def main() -> None:
    rows = q("select * from plan.ref_grid_measure order by grid, ord")
    failures: list[str] = []
    def fail(s: str):
        failures.append(s); print("✕", s)

    for grid in sorted({r["grid"] for r in rows}):
        rules = rules_from(rows, grid)
        label = {m: r["label"].lower() for m, r in rules.items()}

        # 1 · formulas: every one stated has its proof, and every proof has its row
        stated = {(grid, m, r["formula_says"]) for m, r in rules.items() if r["formula_says"]}
        for k in sorted(stated - set(FORMULAS)):
            fail(f"{k[0]}.{k[1]}: the register says '{label[k[1]]} = {k[2]}' and no check here proves the calculation does it")
        for k in sorted(set(FORMULAS) - stated):
            if k[0] == grid:
                fail(f"{k[0]}.{k[1]}: a check for '{k[2]}', which no row of the register says")
        plan = q("select * from plan.finance_plan")
        g = Grid({}, {}, lambda a, m: "fed", {}, rules).from_plan(plan)
        for k in sorted(stated & set(FORMULAS)):
            bad = [c for c in g.cells.values() if not FORMULAS[k](c)]
            if bad:
                fail(f"{grid}.{k[1]}: '{label[k[1]]} = {k[2]}' fails on {len(bad)} of {len(g.cells):,} cells of Finance's plan, e.g. {bad[0]}")
            else:
                print(f"✓ {grid}.{k[1]}: {label[k[1]]} = {k[2]} — holds on all {len(g.cells):,} cells of Finance's plan")
        s = small_grid(rules, std=4.0)
        s.type("V", "ALL", "ALL", "P1", "volume", 800.0, "T1")
        s.type("V", "A1", "M2", "P1", "price", 25.0, "T2")
        for k in sorted(stated & set(FORMULAS)):
            ok = all(FORMULAS[k](c) for c in s.cells.values())
            (print(f"✓ {grid}.{k[1]}: holds on a small grid with a standard cost given, after a typed volume and price") if ok
             else fail(f"{grid}.{k[1]}: fails on the small grid: {list(s.cells.values())}"))

        # 2 · the words of each setting match the setting
        for m, r in rules.items():
            if r["rollup"] == "sum" and r["rollup_says"] != "the sum of the figures beneath it":
                fail(f"{grid}.{m}: adds up as a sum but says '{r['rollup_says']}'")
            if r["rollup"] == "ratio" and f"{label[r['rollup_num']]} ÷ {label[r['rollup_den']]}" not in r["rollup_says"]:
                fail(f"{grid}.{m}: reads {r['rollup_num']} ÷ {r['rollup_den']} at a total but says '{r['rollup_says']}'")
            says = {"source_shape": "split by the demand plan's volumes", "proportional": "by the same proportion", None: "not typed"}[r["breakback"]]
            if says not in r["breakback_says"]:
                fail(f"{grid}.{m}: spreads by {r['breakback']} but says '{r['breakback_says']}'")
            if bool(r["verb"]) != bool(r["breakback"]):
                fail(f"{grid}.{m}: typed ({r['breakback']}) and the verb that types it ({r['verb']}) must come together")
        cells = list(small_grid(rules, std=4.0).cells.values())
        for m, r in rules.items():
            want = (sum(c[r["field"]] for c in cells if c[r["field"]] is not None) if r["rollup"] == "sum"
                    else aggregate(cells, r["rollup_num"], rules) / aggregate(cells, r["rollup_den"], rules))
            if not close(aggregate(cells, m, rules), want):
                fail(f"{grid}.{m}: reads {aggregate(cells, m, rules)} at a total, the rule gives {want}")
        settings = ", ".join(f"{m} {r['rollup']}/{r['breakback'] or 'not typed'}" for m, r in rules.items())
        print(f"✓ {grid}: every roll-up and spread says what it does ({settings})")

    # 3 · the settings drive the calculation: change a row, the same typing behaves differently
    rules = rules_from(rows, "finance")
    def child_then_parent(rs: dict) -> tuple[float, float]:
        g = small_grid(rs)
        g.type("V", "A1", "M1", "P1", "volume", 200.0, "T1")            # a child first: 200 against 300 beside it
        g.type("V", "ALL", "ALL", "P1", "volume", 1000.0, "T2")         # then the total
        return g.cells[("V", "A1", "M1", "P1")]["cases"], g.cells[("V", "A1", "M2", "P1")]["cases"]
    as_registered = child_then_parent(rules)
    changed = {**rules, "volume": {**rules["volume"], "breakback": "proportional"}}
    as_changed = child_then_parent(changed)
    if rules["volume"]["breakback"] == "source_shape" and not (close(as_registered[0], 250.0) and close(as_changed[0], 400.0)):
        fail(f"volume's spread: by the demand plan gives {as_registered}, by the figures standing gives {as_changed}; expected (250, 750) and (400, 600)")
    else:
        print(f"✓ volume typed at the total after a child: spread {rules['volume']['breakback']} → {as_registered}; the row changed to proportional → {as_changed}")
    cells = list(small_grid(rules).cells.values())
    summed = {**rules, "price": {**rules["price"], "rollup": "sum", "rollup_num": None, "rollup_den": None}}
    a, b = aggregate(cells, "price", rules), aggregate(cells, "price", summed)
    if not (close(a, 7000.0 / 400.0) and close(b, 30.0)):
        fail(f"price at the total: as registered {a}, the row changed to a sum {b}; expected 17.5 and 30")
    else:
        print(f"✓ price at the total: registered ratio → {a:.2f}; the row changed to a sum → {b:.2f}")
    try:
        small_grid({**rules, "price": {**rules["price"], "breakback": None}}).type("V", "ALL", "ALL", "P1", "price", 12.0, "T3")
        fail("price with its spread removed could still be typed")
    except ValueError:
        print(f"✓ price with its spread removed from the row is no longer typed (typed measures: {typed(rules)} → "
              f"{typed({**rules, 'price': {**rules['price'], 'breakback': None}})})")

    if failures:
        raise SystemExit(f"{len(failures)} disagreement{'s' if len(failures) != 1 else ''} between the register and the calculation")
    print("the register and the calculation agree")


if __name__ == "__main__":
    main()
