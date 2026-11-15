"""Prices and terms, one page listed in two processes — read only, through the routes.

    uv run python -m tests.shared_page        # from build/, with the warehouse built; writes nothing

1. Opened from Financial planning, the page is Demand's own page and the menu stays in Financial planning: its process is
   the one marked, its entry is *Prices and terms* with no word of where it lives, and every tab, form and link to a page
   Financial planning lists carries where the person came from.
2. Opened from Demand, the same page marks Demand.
3. Who may amend is the right, not the menu: Finance is offered the amendment from either process; a demand planner
   from neither.
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
FINANCE, PLANNER = "finance.manager@caldera", "planner.westbrook@caldera"


def marked(html: str) -> tuple[str, list[str]]:
    """(the process marked in the top bar, the entries marked in the sidebar)."""
    top = re.search(r'<nav class="areas">.*?</nav>', html, re.S).group(0)
    proc = re.search(r'class="active">([^<]+)</a>', top)
    side = re.findall(r'<a href="[^"]*" class="active">([^<]+)</a>', html.split("</header>", 1)[1].split("</aside>", 1)[0])
    return (proc.group(1) if proc else ""), side


def main() -> None:
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    session.become(FINANCE)
    rev = c.get("/revenue").data.decode()
    href = re.search(r'<a href="(/terms[^"]*)"[^>]*>Prices and terms</a>', rev)
    assert href and "via=finplan" in href.group(1), "Revenue's area does not list Prices and terms carrying where it was opened from"
    assert "Prices and terms · in Demand" not in rev.split("</aside>")[0], "the menu still says where the page lives"
    html = c.get(href.group(1).replace("&amp;", "&")).data.decode()
    proc, side = marked(html)
    assert proc == "Financial planning" and side == ["Prices and terms"], (proc, side)
    tabs = re.findall(r'<nav class="tabs">(.*?)</nav>', html, re.S)[0]
    assert all("via=finplan" in h for h in re.findall(r'href="([^"]+)"', tabs)), tabs
    forms = re.findall(r'<form[^>]*action="(/terms/amend[^"]*)"', html)
    assert forms and all("via=finplan" in a for a in forms), forms
    before = set(chassis.CONFIG.receipts.glob("*.json"))
    r = c.post(forms[0], data={})                                   # refused (nothing filled): where does it send the person back to?
    for f in set(chassis.CONFIG.receipts.glob("*.json")) - before:
        f.unlink()
    assert r.status_code == 302 and "via=finplan" in r.headers["Location"], r.headers.get("Location")
    pl = c.get("/price_lists?via=finplan").data.decode()
    assert marked(pl)[0] == "Financial planning" and re.findall(r'action="(/price_lists/change[^"]*)"', pl), "price lists"
    print(f"from Revenue    the same page, Financial planning marked, its entry 'Prices and terms'; {len(forms)} amendment forms and the tabs keep where it was opened from")

    html = c.get("/terms").data.decode()
    proc, side = marked(html)
    assert proc == "Integrated business planning" and side == ["Prices and terms"], (proc, side)
    assert "via=" not in re.findall(r'<nav class="tabs">(.*?)</nav>', html, re.S)[0]
    print("from Demand     the same page, Integrated business planning marked")

    # tabs that are views of one page (Revenue's volume, price, revenue) each stay marked when the address says which menu
    for m, label in (("volume", "Volume"), ("price", "Price"), ("revenue", "Revenue")):
        strip = re.findall(r'<nav class="tabs">(.*?)</nav>', c.get(f"/revenue?measure={m}&via=finplan").data.decode(), re.S)[0]
        assert re.findall(r'class="active">([^<]+)', strip) == [label], (m, strip)
    print("one page's tabs each marked on its own tab, opened from Financial planning")

    may_ibp = bool(re.search(r'action="/terms/amend', html))
    session.become(PLANNER)
    p_fin, p_ibp = c.get("/terms?via=finplan").data.decode(), c.get("/terms").data.decode()
    assert may_ibp and not re.search(r'action="/terms/amend', p_fin) and not re.search(r'action="/terms/amend', p_ibp)
    print(f"the right       {FINANCE} is offered the amendment from either process; {PLANNER} from neither")


if __name__ == "__main__":
    main()
