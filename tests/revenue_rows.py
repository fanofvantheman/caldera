"""The rows of Finance's grid show the material structure — checked on the page.

    uv run python -m tests.revenue_rows                # from build/, with the warehouse built; writes nothing

At a category the rows are the category (the total of the rows beneath), each product one level in and each product's
materials a level further. Under each name its level; a node that opens says how many it opens to and carries ▸, and is
the only kind of name that is a link; a name with nothing beneath it is plain text. Nothing is set bold to say "not a link".
"""
from __future__ import annotations

import os
import re
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
NODE = re.compile(r'<td rowspan="\d+" class="node (d\d)(?: lv-(\w+))?"><div class="nm">(.*?)</div></div></td>', re.S)


def main() -> None:
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    session.become("finance.manager@caldera")
    with app.test_request_context():
        V = M.reads.default_version()
        cat = next(n for n, k in M.reads.material_tree_under("ALL").items() if k["lvl"] == "category")
    html = c.get(f"/revenue?version={V}&customer=ALL&material={cat}").data.decode()
    rows = NODE.findall(html)
    assert rows and rows[0][0] == "d0" and "the total of the rows beneath" in rows[0][2]
    seen = {"product": 0, "material": 0, "opens": 0, "plain": 0}
    for depth, lvl, body in rows[1:]:
        assert (depth, lvl) in (("d1", "product"), ("d2", "material")), (depth, lvl)
        seen[lvl] += 1
        link = "<a " in body
        assert link == ("▸" in body), body[:200]
        if link:
            assert re.search(r"· \d+ (materials?|beneath)", body), body[:300]
            seen["opens"] += 1
        else:
            assert "<b>" not in body
            seen["plain"] += 1
    assert seen["product"] and seen["material"] and seen["opens"] and seen["plain"], seen
    assert "a name with ▸ opens one level down" in html
    assert re.search(r'name="v\|[^|"]+\|\d{4}P\d{2}"', html) and re.search(r'name="v\|[^|"]+\|FY"', html), "the periods and the year take figures"
    print(f"rows           {cat}: {seen['product']} products one level in, {seen['material']} materials beneath them; "
          f"{seen['opens']} names open (▸, with how many), {seen['plain']} plain")


if __name__ == "__main__":
    main()
