"""A schedule month locked with the page's script off — the grid posted as a plain form, as a browser sends it.

    uv run python -m tests.schedule_plain_lock        # from build/, with the warehouse built; nothing saved

The page is read as a browser reads it (every input of the grid's form, a box sent only when ticked) and posted back
without the script:
1. Every lock box the page draws is named beside it, so the form can say a box is unticked.
2. Posted as it stands, nothing changes — a month locked before stays locked, its box posted ticked.
3. A box ticked locks its month; posted again with it unticked, the month follows its driver.
4. A figure and a tick on one month in one post lock it at the figure.
5. A month whose box is not on the form is left alone.
The working copy is dropped at the end; nothing is saved.
"""
from __future__ import annotations

import os
import sys
from html.parser import HTMLParser

from werkzeug.datastructures import MultiDict
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
from face import schedule as S                        # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
FINANCE, PLANT = "finance.manager@caldera", "plant.manager@caldera"


class GridForm(HTMLParser):
    """The inputs of the form with id sch-grid, as a browser would send them: (name, value, kind, checked)."""

    def __init__(self):
        super().__init__()
        self.inside, self.inputs = False, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self.inside = a.get("id") == "sch-grid"
        elif tag == "input" and self.inside and a.get("name"):
            self.inputs.append((a["name"], a.get("value", ""), a.get("type", "text"), "checked" in a))

    def handle_endtag(self, tag):
        if tag == "form":
            self.inside = False


def main() -> None:
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    with app.test_request_context():
        V = M.reads.default_version()
    elec = ("RBF", "CC_L_PROD", "6200")
    lid = S.line_id(elec)

    def states(cc: str = elec[1], who: str = FINANCE) -> dict:
        with app.test_request_context():
            return {k: (x["state"], x["amount"]) for k, x in S.cells_for(who, V)[0].items() if k[1] == cc}

    def page_form(cc: str = elec[1]) -> list[tuple]:
        h = c.get(f"/schedule?version={V}&cc={cc}").data.decode()
        f = GridForm(); f.feed(h)
        return f.inputs

    def post(tick: set | None = None, untick: set | None = None, figures: dict | None = None, drop: set | None = None, cc: str = elec[1]) -> None:
        """The form as the browser sends it: every field, a box only if ticked — with the person's changes."""
        data: list[tuple] = []
        for name, value, kind, checked in page_form(cc):
            if drop and name.split("|", 1)[-1] in drop:
                continue
            if kind == "checkbox":
                key = name.split("|", 1)[1]
                on = (checked or key in (tick or set())) and key not in (untick or set())
                if on:
                    data.append((name, "on"))
            else:
                data.append((name, (figures or {}).get(name, value)))
        r = c.post("/schedule/cell", data=MultiDict(data))                 # no X-Live header: the plain post
        assert r.status_code == 302, r.status_code

    session.become(FINANCE)
    try:
        S.COPIES.drop(FINANCE, ("schedule", V))
        P = [k[3] for k in states() if k[:3] == elec]
        P.sort()
        # 1 · every box named beside it
        inputs = page_form()
        boxes = [n for n, _, k, _ in inputs if k == "checkbox"]
        named = {n for n, _, k, _ in inputs if n.startswith("kh|")}
        assert boxes and {"kh|" + b.split("|", 1)[1] for b in boxes} == named, "a lock box the plain form cannot report unticked"
        print(f"named           {len(boxes)} lock boxes on the page, each named beside it for the plain form")

        # 2 · posted as it stands: nothing changes
        before = states()
        post()
        assert states() == before, "a plain post of the page as it stands changed something"
        # and at a cost centre with a month locked before, by its budget holder: it stays locked
        held = q("select * from plan.opex_schedule where version_id = ? and state = 'locked' order by cost_centre_code limit 1", V)[0]
        who = next(w for w in (FINANCE, PLANT) if roles.may(w, S._verb("amount"), held["cost_centre_code"], dimension="organisation", kind="latest_view"))
        session.become(who)
        b2 = states(held["cost_centre_code"], who)
        assert f'name="kh|{S.line_id((held["entity_code"], held["cost_centre_code"], held["account_code"]))}|{held["period"]}"' in \
            c.get(f"/schedule?version={V}&cc={held['cost_centre_code']}").data.decode(), "the locked month has no box on its page"
        post(cc=held["cost_centre_code"])
        assert states(held["cost_centre_code"], who) == b2 and b2[(held["entity_code"], held["cost_centre_code"], held["account_code"], held["period"])][0] == "locked"
        S.COPIES.drop(who, ("schedule", V))
        session.become(FINANCE)
        print(f"as it stands    posted without the script, nothing moved — at {elec[1]}, and at {held['cost_centre_code']} as {who}, "
              f"where {held['account_code']} {held['period']} stays locked with its box ticked")

        # 3 · tick, then untick
        p = P[2]; key = f"{lid}|{p}"
        post(tick={key})
        x = states()[(*elec, p)]
        assert x[0] == "locked" and abs(x[1] - before[(*elec, p)][1]) < 0.005, x
        post(untick={key})
        y = states()[(*elec, p)]
        assert y[0] == "calculated" and abs(y[1] - before[(*elec, p)][1]) < 0.005, y
        print(f"tick, untick    {elec[2]} at {elec[1]} {p}: ticked → locked at {x[1]:,.0f}; unticked → follows its driver again")

        # 4 · a figure and a tick on one month
        q_ = P[4]; key4 = f"{lid}|{q_}"; fig = round(before[(*elec, q_)][1] + 7_000)
        post(tick={key4}, figures={f"m|{key4}": f"{fig:,}"})
        z = states()[(*elec, q_)]
        assert z[0] == "locked" and abs(z[1] - fig) < 0.005, z
        print(f"figure + tick   {q_}: typed {fig:,} and ticked in one post → locked at {z[1]:,.0f}")

        # 5 · a month whose box is not on the form is left alone: post without its named box and its tick
        post(drop={key4})
        assert states()[(*elec, q_)][0] == "locked", "a month not on the form was unlocked"
        others = {k: v for k, v in states().items() if k[3] not in (p, q_) or k[:3] != elec}
        assert all(others[k] == before[k] for k in others), "a month the person did not touch moved"
        print("left alone      a month not on the form stays locked; no other month moved")
    finally:
        S.COPIES.drop(FINANCE, ("schedule", V)); S.COPIES.drop(PLANT, ("schedule", V))
        print("cleaned up: the working copy dropped; nothing was saved")


if __name__ == "__main__":
    main()
