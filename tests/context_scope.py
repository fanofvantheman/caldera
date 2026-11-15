"""What a screen is scoped to (DEC-20261115-02 points 1–4) — read only, through the routes.

    uv run python -m tests.context_scope        # from build/, with the warehouse built; writes nothing

1. The context block shows the selections the screen applies and only those; a value the address holds for one it does
   not apply is carried, so the next screen that applies it opens on it.
2. A person whose assignments reach one cost centre lands in it, with nothing else offered.
3. The opex schedule at a node above a cost centre is that node's total by account, read only, and each total is the sum
   of the plan's cells beneath it; at a cost centre the lines are typed, and only that cost centre's.
4. Headcount at a node is one table, not a table per cost centre.
5. Revenue at a category shows its products and, beneath each, its materials.
"""
from __future__ import annotations

import os
import re
import sys
from collections import defaultdict
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

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
FINANCE, SALES = "finance.manager@caldera", "sales.director@caldera"


def block(html: str) -> tuple[list[str], dict, dict]:
    """(the selections shown, what each shows selected, what is carried hidden)."""
    form = re.search(r'<form class="context".*?</form>', html, re.S)
    if not form:
        return [], {}, {}
    f = form.group(0)
    shown = re.findall(r'<label><span>(.*?)</span><select name="(\w+)"', f)
    sel = {k: (re.search(rf'<select name="{k}">.*?<option value="([^"]*)" selected', f, re.S) or [None, None])[1] for _, k in shown}
    return [k for _, k in shown], sel, dict(re.findall(r'type="hidden" name="(\w+)" value="([^"]*)"', f))


def main() -> None:
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    with app.test_request_context():
        V = M.reads.default_version()
    session.become(FINANCE)

    # 1 · the block: what the screen applies, and what it carries
    keys, _, _ = block(c.get("/schedule").data.decode())
    assert keys == ["version", "fy", "entity", "cc"], keys
    keys, _, carried = block(c.get("/demand?cc=CC_SALES&entity=CF").data.decode())
    assert keys == ["version", "customer", "material"] and carried.get("cc") == "CC_SALES" and carried.get("entity") == "CF", (keys, carried)
    keys, _, _ = block(c.get("/costs/mapping").data.decode())
    assert keys == [], keys
    link = re.search(r'<nav class="areas"><a href="[^"]*"[^>]*>[^<]*</a><a href="([^"]*)"', c.get("/demand?cc=CC_SALES").data.decode())
    assert link and "cc=CC_SALES" in link.group(1), "a link from the demand plan does not carry the cost centre"
    _, sel, _ = block(c.get("/schedule?" + link.group(1).replace("&amp;", "&").split("?", 1)[1]).data.decode())
    assert sel.get("cc") == "CC_SALES", sel
    print("block           the schedule shows version, year, entity, cost centre; the demand plan version, customer, material, carrying the "
          "cost centre unseen, and the schedule opens on it from there; the mapping review shows none")

    # 2 · one cost centre reached: landed in, nothing else offered
    session.become(SALES)
    html = c.get("/schedule").data.decode()
    _, sel, _ = block(html)
    opts = re.findall(r'<option value="([^"]*)"', re.search(r'<select name="cc">.*?</select>', html, re.S).group(0))
    assert sel.get("cc") == "CC_SALES" and opts == ["CC_SALES"], (sel, opts)
    print(f"landed          {SALES} opens on CC_SALES, the one cost centre offered")
    session.become(FINANCE)

    # 3 · a node is its total by account, read only; a cost centre its own lines, typed
    html = c.get(f"/schedule?version={V}&cc=OPS").data.decode()
    assert 'name="m|' not in html and "read only" in html
    rows = re.findall(r'<td class="sticky"><span>(\d{4}) [^<]*</span> <span class="small muted">(\d+) cost centres?</span></td>(.*?)</tr>', html, re.S)
    beneath = {r["c"] for r in q("""select descendant_code c from dims.dim_organisation_hierarchy where ancestor_code = 'OPS'""")}
    want = defaultdict(float)
    ps = [r["period"] for r in q("select distinct period from plan.opex_schedule where version_id = ? order by 1", V)]
    for r in q("select account_code, sum(amount) a from plan.opex_schedule where version_id = ? and period = ? and cost_centre_code in (select descendant_code from dims.dim_organisation_hierarchy where ancestor_code = 'OPS') group by 1", V, ps[0]):
        want[r["account_code"]] = r["a"]
    assert rows and len(rows) == len(want), (len(rows), len(want))
    # the first plan column after the actual ones is the first plan period
    head = re.search(r"<thead>.*?</thead>", html, re.S).group(0)
    cols = re.findall(r'<th class="n( closed| tot)?"', head.split(">Rate</th>", 1)[1])      # the period columns, after the rate
    first_plan = next(i for i, k in enumerate(cols) if not k)
    for acct, n, tds in rows:
        cells = re.findall(r'<td class="n[^"]*">([^<]*)</td>', tds)
        shown = float(cells[first_plan].replace(",", "") or 0)
        assert abs(shown - want[acct]) <= 1, (acct, shown, want[acct])
    html = c.get(f"/schedule?version={V}&cc=CC_E_MAINT").data.decode()
    lines = set(re.findall(r'name="m\|([^|"]+)\|', html))
    assert lines and all(l.split("~")[1] == "CC_E_MAINT" for l in lines), lines
    print(f"schedule        at OPS {len(rows)} accounts, each the sum of the {len(beneath) - 1} cost centres beneath to the dollar, nothing to type; "
          f"at CC_E_MAINT {len(lines)} lines to type, all its own")

    # 4 · headcount at a node: one table
    html = c.get(f"/headcount/role?version={V}&cc=OPS").data.decode()
    assert html.count("<h2>") - html.count("The agreements") == 1, html.count("<h2>")
    html = c.get(f"/headcount/role?version={V}&cc=CC_E_TOM").data.decode()
    assert "<h2>Echuca tomato hall" in html and "<h2>Loxton production" not in html
    print("headcount       one table at OPS, the cost centre beside each position; at the tomato hall only its own")

    # 5 · Revenue at a category: its products, and each product's materials beneath it
    cat = q("select category_code c from dims.dim_material group by 1 order by 1 limit 1")[0]["c"]
    html = c.get(f"/revenue?version={V}&material={cat}").data.decode()
    products = {r["p"] for r in q("select distinct product_code p from dims.dim_material where category_code = ?", cat)}
    shown = set(re.findall(r'<tbody id="fin-r-([^"]+)"', html))
    mats = shown - products - {cat}
    assert products & shown and mats and 'padding-left:1.4rem' in html, (len(shown), len(products))
    print(f"revenue         {cat}: {len(products & shown)} products, each followed by its materials ({len(mats)} rows beneath them)")


if __name__ == "__main__":
    main()
