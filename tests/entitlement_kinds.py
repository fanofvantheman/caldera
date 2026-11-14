"""The kinds of entitlement and the agreements recast beneath them — checked against the warehouse and through the page.

    uv run python -m tests.entitlement_kinds          # from build/, with the warehouse built; read only

1. The kinds are a closed list of seven; every entitlement is a row under one of them, with its clause.
2. The rates the labour model reads are made from the entitlements: each agreement's base rates, and from the dated
   increase each rate × (1 + the increase) to the cent — equal to the agreement's figures except where the increase on
   the schedule's rate differs from the generator's old unrounded step, which is three of Riverbend's rates by a cent.
3. The casual loading the labour model applies is the agreement's own row.
4. The page lists the kinds (which are priced, which are not yet), each agreement's entitlements with their clauses, and
   says what it is for.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BUILD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BUILD))
if os.environ.get("FACE_ROOT"):
    sys.path.insert(0, os.environ["FACE_ROOT"])

import chassis                                        # noqa: E402
from chassis import app as chassis_app                # noqa: E402
from chassis.warehouse import q                       # noqa: E402

from face import SHELL, roles, session                # noqa: E402
from face import __main__ as M                        # noqa: E402
from generate.costs import AGREEMENTS, AGREEMENT_STEP, CLASSIFICATIONS, STEP_PERIOD   # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")


def main() -> None:
    kinds = {k["kind"]: k for k in q("select * from dims.ref_entitlement_kind")}
    assert len(kinds) == 7 and {k for k, v in kinds.items() if v["priced"]} == {"base_rate", "loading", "on_cost", "dated_increase"}
    rows = q("select * from dims.reg_entitlement")
    assert rows and all(r["kind_known"] and r["clause"] and r["clause_ref"] for r in rows)
    print(f"kinds           {len(kinds)}, closed; {len(rows)} entitlements beneath them, every one with its clause")

    reg = {(r["agreement"], r["classification"], r["valid_from_period"]): r["hourly_rate"] for r in q("select * from dims.reg_agreement")}
    moved = []
    for e, (a, _, f) in AGREEMENTS.items():
        for c, _, r in CLASSIFICATIONS:
            assert abs(reg[(a, c, "2025P01")] - round(r * f, 2)) < 1e-9
            old, now = round(r * f * (1 + AGREEMENT_STEP), 2), reg[(a, c, STEP_PERIOD)]
            assert abs(now - round(round(r * f, 2) * (1 + AGREEMENT_STEP), 2)) < 1e-9, (a, c, now)
            if abs(now - old) > 1e-9:
                moved.append((a, c, old, now))
    assert len(reg) == 2 * len(AGREEMENTS) * len(CLASSIFICATIONS)
    assert {(a, c) for a, c, _, _ in moved} == {("RBF-2024", "PO1"), ("RBF-2024", "PO3"), ("RBF-2024", "TT")}, moved
    print(f"rates           {len(reg)} read from the entitlements; the increase on the schedule's rate moves {', '.join(f'{a} {c} {o:.2f}→{n:.2f}' for a, c, o, n in moved)}")

    loading = {r["instrument"]: r["value"] for r in rows if r["kind"] == "loading" and r["applies_to"] == "casual"}
    cas = q("""select l.wages, l.fte, p.hours_per_week, d.weeks_in_period, l.rate, p.agreement from plan.labour_line l
               join dims.reg_position p on p.position_id = l.line_id join dims.dim_period d using (period)
               where l.model = 'role' and l.employment_type = 'casual' and l.fte > 0 limit 20""")
    assert cas
    for x in cas:
        assert abs(x["wages"] / (x["fte"] * x["hours_per_week"] * x["weeks_in_period"] * x["rate"]) - (1 + loading[x["agreement"]])) < 1e-9
    print(f"casual loading  the labour model's casual wages carry each agreement's own loading ({', '.join(f'{k} {v:.0%}' for k, v in loading.items())})")

    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    session.become("finance.manager@caldera")
    page = c.get("/labour/entitlements").data.decode()
    assert all(k["kind_label"] in page for k in kinds.values()) and "not yet priced" in page and "not an interpretation" in page
    assert "Caldera Food Processing Agreement 2025" in page and "cl. 12.2" in page and "casual loading of 25%" in page
    print("page            the kinds with what is priced and what is not yet, both agreements' entitlements with their clauses, and what it is for")


if __name__ == "__main__":
    main()
