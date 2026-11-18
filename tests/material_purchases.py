"""The material purchase plan and the costing that reads it — through the warehouse and the routes; the acts it places are
removed again.

    uv run python -m tests.material_purchases        # from build/, with the warehouse built

1. Requirement is the production requirement at the plant × the bill × usage, for the key materials only.
2. The stock walks: opening + purchases − consumption = closing, carried to the next period; consumption at the period's
   weighted average; the run's figures are the shared function's, made again here.
3. Purchases follow the source: a campaign buys only in its window; a contract within its term at its price (× its index);
   spot and past a contract's term at the price in force.
4. The costing takes the average as given: a key input's planned price is the stock's average cost in the period, any
   other input's the price in force; usage and efficiency at 100 leave the bill and the hours as they are.
5. The pages: Material purchases under Supply (and its form only to the holder of the supply plan's right), Material stock
   under Cost of goods read only; a typed price placed as one act and refused without the right (the file removed).
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
from chassis.warehouse import q                       # noqa: E402

from calc import purchases as P                       # noqa: E402
from face import SHELL, roles, session                # noqa: E402
from face import __main__ as M                        # noqa: E402
from face import purchases as FP                      # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
LV = "LV-2027P04"
BUYER, FINANCE = "supply.planner@caldera", "finance.manager@caldera"


def close(a, b, tol=1e-6) -> bool:
    return (a is None and b is None) or (a is not None and b is not None and abs(a - b) <= tol * max(1.0, abs(b)))


def main() -> None:
    keys = q("select k.*, i.campaign_window from dims.ref_key_material k join dims.dim_input_material i on i.material_code = k.input_code")
    assert keys
    # 1 · requirement
    k0 = next(k for k in keys if k["input_code"] == "TOMATO")
    # cases made are the inventory plan's production requirement at the plant (DEC-20261117-02 point 6), no longer cases sold
    want = q("""select p.period, sum(p.quantity * b.quantity_per_case) w from plan.production_requirement p
                join dims.ref_bom b on b.parent_material = p.material_code and b.plant_code = p.plant_code
                where p.version_id = ? and b.component_material = ? and p.plant_code = ? group by 1""", LV, k0["input_code"], k0["plant_code"])
    got = {r["period"]: r["quantity"] for r in q("select * from plan.material_requirement where version_id = ? and input_code = ? and plant_code = ?", LV, k0["input_code"], k0["plant_code"])}
    assert want and all(close(got.get(r["period"]), r["w"]) for r in want if r["period"] in got) and got
    assert {r["input_code"] for r in q("select distinct input_code from plan.material_requirement")} == {k["input_code"] for k in keys}
    print(f"requirement     {k0['input_code']} at {k0['plant_code']}: cases to make × the bill × usage in every period; only the {len({k['input_code'] for k in keys})} key materials")

    # 2 · the stock walks, and is the shared function's
    rows = q("select * from plan.material_stock order by version_id, input_code, plant_code, period")
    by: dict = {}
    for r in rows:
        by.setdefault((r["version_id"], r["input_code"], r["plant_code"]), []).append(r)
    for rs in by.values():
        for a, b in zip(rs, rs[1:]):
            assert close(a["closing_quantity"], b["opening_quantity"]) and close(a["closing_value"], b["opening_value"])
        for r in rs:
            assert close(r["closing_quantity"], r["opening_quantity"] + r["purchase_quantity"] - r["consumption_quantity"])
            if r["opening_quantity"] + r["purchase_quantity"] > 0:
                assert close(r["average_cost"], (r["opening_value"] + r["purchase_value"]) / (r["opening_quantity"] + r["purchase_quantity"]))
            assert close(r["consumption_value"], r["consumption_quantity"] * r["average_cost"])
    again = P.compute_all(lambda sql: q(sql), lambda t: t, LV)
    lv = {(r["input_code"], r["plant_code"], r["period"]): r for r in rows if r["version_id"] == LV}
    assert len(again) == len(lv) and all(close(lv[(r["input_code"], r["plant_code"], r["period"])]["average_cost"], r["average_cost"]) for r in again)
    print(f"stock           {len(by)} material × plant × plan walks: opening + purchases − consumption = closing, carried; consumption at the average; made again by the shared function")

    # 3 · purchases follow the source
    prices = {(r["version_id"], r["input_code"], r["period"]): r["price"] for r in q("select * from plan.input_price_in_force")}
    idx = {(r["version_id"], r["assumption_code"], r["period"]): r["value"] for r in q("select version_id, assumption_code, period, value from plan.assumption_in_force")}
    fp = {r["period"]: r["fiscal_period"] for r in q("select period, fiscal_period from dims.dim_period")}
    for k in keys:
        rs = by[(LV, k["input_code"], k["plant_code"])]
        if k["source"] == "campaign":
            window = P.window_periods(k["campaign_window"], fp)
            assert all(r["purchase_quantity"] == 0 or r["period"] in window or r["quantity_typed"] for r in rs), k["input_code"]
        for r in rs:
            if r["price_typed"] or not r["purchase_quantity"]:
                continue
            if r["source"] == "contract":
                want = float(k["contract_price"]) * float(idx.get((LV, k["contract_index"], r["period"]), 100.0) if k["contract_index"] else 100.0) / 100.0
            else:
                want = prices[(LV, k["input_code"], r["period"])]
            assert close(r["purchase_price"], want), (k["input_code"], r["period"], r["purchase_price"], want)
    past = [r for r in by[(LV, "BEANS_DRY", "ECH")] if r["period"] > "2027P12"]
    assert past and all(r["source"] == "spot" for r in past), "a contract past its term buys spot"
    print("sources         campaigns buy only in their window; contracts at their price (× index) within term, spot after; spot at the price in force")

    # 4 · the costing takes the average
    pmi = q("""select i.*, s.consumption_value / nullif(s.consumption_quantity, 0) avg_c, s.average_cost from plan.planned_material_input i
               left join plan.material_stock s on s.version_id = i.version_id and s.input_code = i.input_code and s.plant_code = i.plant_code and s.period = i.period
               where i.version_id = ?""", LV)
    keyset = {(k["input_code"], k["plant_code"]) for k in keys}
    n_key = 0
    for r in pmi:
        if (r["input_code"], r["plant_code"]) in keyset:
            n_key += 1
            assert close(r["price"], r["avg_c"] if r["avg_c"] is not None else r["average_cost"]), r
        else:
            assert close(r["price"], prices[(LV, r["input_code"], r["period"])]), r
    bom = {(r["parent_material"], r["plant_code"], r["component_material"]): r["q"] for r in q("select parent_material, plant_code, component_material, sum(quantity_per_case) q from dims.ref_bom group by all")}
    assert all(close(r["quantity"], bom[(r["material_code"], r["plant_code"], r["input_code"])]) for r in pmi[:2000]), "usage at 100 leaves the bill as it is"
    lab = q("""select l.crew_hours, r.rate_cases_per_hour, c.crew from plan.planned_labour l join dims.ref_route r on r.material_code = l.material_code and r.is_primary
               left join dims.ref_line_crew c on c.line_code = r.line_code where l.version_id = ? limit 500""", LV)
    assert all(close(x["crew_hours"], x["crew"] / x["rate_cases_per_hour"]) for x in lab if x["crew"]), "efficiency at 100 leaves the hours as they are"
    print(f"costing         {n_key} key-material cells priced at the stock's average cost, the rest at the price in force; usage and efficiency at 100 change nothing")

    # 5 · the pages and an act
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    session.become(BUYER)
    html = c.get(f"/supply/purchases?version={LV}").data.decode()
    assert "Average cost" in html and "campaign intake" in html and 'action="/supply/purchases/type' in html
    session.become(FINANCE)
    fin = c.get(f"/costs/material_stock?version={LV}").data.decode()
    assert "read only" in fin and 'action="/supply/purchases/type' not in fin and "Average cost" in fin
    before = set(FP.ACTS.files())
    c.post("/supply/purchases/type", data={"key": "CUP_120|LOX", "period": "2027P08", "price": "0.07", "reason": "test"})
    assert set(FP.ACTS.files()) == before, "Finance's entry right planned a purchase"
    session.become(BUYER)
    c.post("/supply/purchases/type", data={"key": "CUP_120|LOX", "period": "2027P08", "price": "0.07", "reason": "a quote"})
    new = set(FP.ACTS.files()) - before
    try:
        assert len(new) == 1 and re.search(r"set,,LV-2027P04,CUP_120,LOX,2027P08,,0\.07,a quote,supply\.planner@caldera", next(iter(new)).read_text())
    finally:
        for p in new:
            p.unlink()
    print("pages           Material purchases with its form to the buyer; Material stock read only under Cost of goods; a typed price refused to Finance, placed by the buyer (removed again)")


if __name__ == "__main__":
    main()
