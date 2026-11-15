"""A reload keeps who you are acting as, and where you stand — checked through the routes.

    uv run python -m tests.reload_keeps_who            # from build/, with the warehouse built; writes nothing

Choosing who to act as sets a cookie; a face that restarts (the reloader, a stop and start) has nobody chosen and takes
the person the cookie names, so Finance can still type Finance's figures after it. A browser with no cookie gets the
default person, and a running face is not switched by another browser's cookie. The page's selections are in the address,
so the same address after a restart opens on the same version, year, customer and material.
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
FINANCE = "finance.manager@caldera"


def main() -> None:
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    with app.test_request_context():
        V = M.reads.default_version()
        fy = int(M.reads.version(V)["fiscal_year"])
        cat = next(iter(M.reads.material_tree_under("ALL")))
    addr = f"/revenue?version={V}&fy={fy}&customer=ALL&material={cat}"
    session.state["who"] = None
    r = c.post("/whoami", data={"who": FINANCE, "next": addr})
    assert r.status_code == 302 and "chassis_who=" in r.headers.get("Set-Cookie", ""), r.headers.get("Set-Cookie")
    assert c.get_cookie("chassis_who").value == FINANCE
    html = c.get(addr).data.decode()
    assert f'value="{FINANCE}" selected' in html and 'class="cell"' in html, "acting as Finance, the grid takes figures"

    session.state["who"] = None                                   # the face restarts: nobody chosen in its memory
    html = c.get(addr).data.decode()
    assert f'value="{FINANCE}" selected' in html, "after a restart the browser's choice is taken back"
    assert 'class="cell"' in html and f"<b>{M.reads.node_label('material', cat)}</b>" in html, "the grid takes figures, at the same material"
    print(f"restart        acting as {FINANCE} again, at {cat} — the address kept the selections, the cookie the person")

    other = app.test_client()                                     # a browser that never chose: the running face is unchanged
    assert f'value="{FINANCE}" selected' in other.get(addr).data.decode()
    session.state["who"] = None
    html = other.get(addr).data.decode()
    assert f'value="{FINANCE}" selected' not in html, "with no cookie, the default person"
    with app.test_request_context():
        default = session.who(roles.principals())
    c.set_cookie("chassis_who", "nobody@nowhere")
    session.state["who"] = None
    assert f'value="{default}" selected' in c.get(addr).data.decode(), "a name that is not a person falls back to the default"
    print(f"no cookie      the default person ({default}); a cookie naming nobody falls back to it too")
    session.state["who"] = None


if __name__ == "__main__":
    main()
