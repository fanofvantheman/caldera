"""The thin check of the whole (DEC-20261120-01 point 1): the app starts and every page opens — every GET route that
takes no argument, as the people who between them reach every area, answers without an error. Read only.

    uv run python -m tests.pages_open        # from build/, with the warehouse built
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

from face import SHELL, roles, session                # noqa: E402
from face import __main__ as M                        # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")


WHO = ["finance.manager@caldera", "supply.planner@caldera", "head.demand@caldera"]


def main() -> None:
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    app.testing = False
    c = app.test_client()
    routes = sorted({r.rule for r in app.url_map.iter_rules() if "GET" in r.methods and not r.arguments and not r.rule.startswith("/static")})
    who = [w for w in WHO if w in set(roles.principals())]
    bad, n = [], 0
    for w in who:
        session.become(w)
        for r in routes:
            resp = c.get(r, follow_redirects=False)
            n += 1
            if resp.status_code >= 500:
                bad.append(f"{w} {r} → {resp.status_code}")
    for b in bad:
        print("FAIL", b)
    print(f"pages open      {n - len(bad)} of {n} ({len(routes)} pages × {len(who)} people)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
