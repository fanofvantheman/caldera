"""Individual pay is read under its own verb — checked through the pages, read only.

    uv run python -m tests.pay_verb          # from build/, with the warehouse built

The name-based cost centres' labour lines (and the people behind them) show for a login holding read.pay and for no
other: the schedule, the headcount by name, and the cost centres' actuals. A login without it sees the role-based labour
and the rest of every name-based cost centre, and is told what is withheld.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

BUILD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BUILD))

import chassis                                        # noqa: E402
from chassis import app as chassis_app                # noqa: E402
from chassis.warehouse import q                       # noqa: E402

from face import SHELL, roles, session                # noqa: E402
from face import __main__ as M                        # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
HOLDER = "finance.manager@caldera"
WITHOUT = ["gm@caldera", "auditor@caldera", "plant.manager@caldera"]


def exec_group(html: str) -> str:
    """The executive office's rows on the actuals page read at the ledger's cost centres: its group row to the next."""
    m = re.search(r"4400 Executive office</b>(.*?)(<tr class=\"l0\">|<tr class=\"total\">)", html, re.S)
    return m.group(1) if m else ""


def main() -> None:
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    named = [r["cost_centre_code"] for r in q("select cost_centre_code from dims.dim_cost_centre where labour_model = 'name'")]
    person = q("select person_name, annual_salary from dims.reg_person where not vacancy order by person_id limit 1")[0]
    salary = f"{person['annual_salary']:,.0f}"
    exec_line = 'id="sch-l-CF~CC_EXEC~6100"'
    hall_line = 'id="sch-l-CF~CC_E_TOM~6100"'
    failures = []

    def check(ok: bool, says: str) -> None:
        print(("✓ " if ok else "✕ ") + says)
        if not ok:
            failures.append(says)

    with app.test_request_context():
        assert roles.may(HOLDER, "read.pay") and not any(roles.may(w, "read.pay") for w in WITHOUT)
    session.become(HOLDER)
    sch = c.get("/schedule?cc=CAL").data.decode()
    check(exec_line in sch and hall_line in sch, f"{HOLDER} (read.pay) sees the executive's labour line and the tomato hall's on the schedule")
    hn = c.get("/headcount/name").data.decode()
    check(person["person_name"] in hn and salary in hn, f"{HOLDER} reads {person['person_name']}'s salary on Headcount by name")
    act = c.get("/costs/actuals?at=ledger").data.decode()
    check("6100 Wages" in exec_group(act), f"{HOLDER} sees the executive office's wages in the actuals")
    for who in WITHOUT:
        session.become(who)
        sch = c.get("/schedule").data.decode()
        hn = c.get("/headcount/name").data.decode()
        act = c.get("/costs/actuals?at=ledger").data.decode()
        cc = c.get("/costs/centres").data.decode()
        check(exec_line not in sch and person["person_name"] not in hn and salary not in hn,
              f"{who} (no read.pay): no name-based labour line on the schedule, no person or salary on Headcount by name")
        check("individual pay" in hn and "read.pay" in hn, f"{who} is told who reads it")
        check("6100 Wages" not in exec_group(act), f"{who}: the executive office's wages are not in the actuals")
        check(("planned by name" in act and "planned by name" in cc) or who == "plant.manager@caldera", f"{who}: the actuals and cost centre pages say labour is withheld")
        if who != "plant.manager@caldera":
            check(hall_line in c.get("/schedule?cc=CAL").data.decode(), f"{who} still sees a role-based labour line (the tomato hall's)")
        else:
            check(hall_line in sch, f"{who} sees the tomato hall's labour line in their own cost centres")
    if failures:
        raise SystemExit(f"{len(failures)} failure{'s' if len(failures) != 1 else ''}")
    print(f"individual pay is read by the holders of read.pay only ({len(named)} cost centres planned by name)")


if __name__ == "__main__":
    main()
