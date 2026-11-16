"""Prices and terms apply the customer in the context — read only, through the routes.

    uv run python -m tests.prices_terms_customer        # from build/, with the warehouse built; writes nothing

1. Both tabs offer the customer selection in the context block.
2. All customers: every account's terms and every price list. One account: only its terms and the lists it is on.
   A unit: the accounts beneath it.
3. Terms is one table, the account in the rows; its one amendment form offers only the instruments shown.
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

from face import SHELL, reads, roles, session         # noqa: E402
from face import __main__ as M                        # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
FINANCE = "finance.manager@caldera"


def accounts_in(html: str) -> set[str]:
    return set(re.findall(r'data-account="([^"]+)"', html))


def offered(html: str) -> int:
    form = re.search(r'action="/terms/amend.*?</form>', html, re.S)
    return len(re.findall(r'<option value="[^"|]+\|', form.group(0))) if form else 0


def heads(html: str) -> list[str]:
    return re.findall(r"<h2>([^<]+)<span", html)


def main() -> None:
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    session.become(FINANCE)
    terms_all = c.get("/terms").data.decode()
    lists_all = c.get("/price_lists").data.decode()
    for name, html in (("terms", terms_all), ("price lists", lists_all)):
        assert 'name="customer"' in html.split("</aside>")[0], f"{name}: no customer selection in the context block"
    accounts = sorted({t["account_code"] for t in reads.terms()})
    lists = reads.price_lists()
    assert len(accounts) > 1 and len(lists) > 1
    acct = accounts[0]
    t1 = c.get(f"/terms?customer={acct}").data.decode()
    assert accounts_in(terms_all) == set(accounts), "all customers: every account's terms in the one table"
    assert terms_all.count("<table") - terms_all.count('id="envelopes"') >= 1 and not re.search(r'<h2>[^<]+<span class="count">' + acct, terms_all), "a table per account"
    assert accounts_in(t1) == {acct}, "terms at one account"
    assert len(re.findall(r'action="/terms/amend', t1)) == 1 and 0 < offered(t1) < offered(terms_all), "the one form offers the instruments shown"
    p1 = c.get(f"/price_lists?customer={acct}").data.decode()
    mine = [pl["price_list"] for pl in lists if any(a["account_code"] == acct for a in pl["accounts"])]
    shown = [h for h in heads(p1) if h in {pl["price_list"] for pl in lists}]
    assert shown == mine and len(mine) < len(lists), (shown, mine)
    unit = reads.unit_of_account(acct)
    under = reads.accounts_under(unit)
    tu = c.get(f"/terms?customer={unit}").data.decode()
    assert accounts_in(tu) == under & set(accounts), "terms at a unit"
    print(f"{acct}: its terms only and {len(mine)} of {len(lists)} price lists; unit {unit}: {len(under)} accounts; all customers: {len(accounts)} accounts, {len(lists)} lists")


if __name__ == "__main__":
    main()
