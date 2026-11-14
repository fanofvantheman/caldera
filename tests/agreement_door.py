"""The agreement door — a copy of an agreement in, its entitlements proposed under the kinds, each accepted or altered —
checked through the routes, with the model replaced by a stub (no model is called).

    uv run python -m tests.agreement_door            # from build/, with the warehouse built; takes three scoped runs

The first-pass tool: a quotation not in the document word for word is refused by its code, whatever the model said; a
clause under no kind comes back unplaced; anything but a collective instrument is refused before the model is asked;
with no key and no client it says it did not run. Through the door: refused for a person without the verb and for an
individual's contract; taken in with no key, nothing fails — the document waits, not read; taken in with the stub, the
rows wait for a decision, the refused row is shown and never offered, and the labour model reads none of them. Then a
row is accepted, one placed under another kind, the unplaced clause approximated under a kind with a note, and one left
out: after the run the register holds exactly the three taken, each with its clause, the labour model has the new
agreement's rates beside the current one, and the labour figures have not moved. Everything it writes is removed and the
run taken again.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

BUILD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BUILD))
if os.environ.get("FACE_ROOT"):
    sys.path.insert(0, os.environ["FACE_ROOT"])

import chassis                                        # noqa: E402
from chassis import app as chassis_app                # noqa: E402
from chassis.warehouse import q                       # noqa: E402
from coa_map import clauses                           # noqa: E402
from coa_map.codes import MappingUnavailable          # noqa: E402

from face import SHELL, roles, session                # noqa: E402
from face import __main__ as M                        # noqa: E402
from face import agreements as A                      # noqa: E402
from face import doors                                # noqa: E402
from generate import documents as D                   # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")
HOLDER, OTHER = "finance.manager@caldera", "gm@caldera"     # finance holds the People role at Caldera


class Stub:
    """Stands where the Anthropic client stands: `messages.stream(...)` as a context manager whose final message is the
    JSON the response schema asks for. Counts its calls, so a refusal before sending can be proved."""

    def __init__(self, items: list[dict]):
        self.items, self.calls = items, 0
        self.messages = self

    def stream(self, **kw):
        self.calls += 1
        assert kw["output_config"]["format"]["type"] == "json_schema" and "none" in kw["output_config"]["format"]["schema"]["properties"]["clauses"]["items"]["properties"]["kind"]["enum"]
        return _Stream(SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps({"clauses": self.items}))]))


class _Stream:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.msg


def what_a_model_would_say(text: str) -> list[dict]:
    """The rows a reader of the renegotiated agreement would propose, quoting it — and one paraphrase, which must be refused."""
    def item(kind, quote, ref, value=0.0, cls="", applies="", from_date="", conf="high"):
        assert kind == "BAD" or clauses.quotation_found(quote, text), quote
        return {"kind": "loading" if kind == "BAD" else kind, "classification": cls, "applies_to": applies, "value": value, "from_date": from_date,
                "clause_ref": ref, "quote": quote, "confidence": conf, "rationale": "the clause states it"}
    names = {c: n for c, n, _ in D.CLASSIFICATIONS}
    out = [item("base_rate", f"{names[c]}: ${r:.2f} per ordinary hour.", f"Schedule A, item {i}", r, c, from_date=D.COMMENCES)
           for i, (c, r) in enumerate(D.NEW_RATES.items(), start=1)]
    out += [item("dated_increase", "Rates in Schedule A increase by 3.0% from the first full pay period commencing on or after 1 July 2028.", "cl. 12.2", 0.03, from_date="2028-07-01"),
            item("loading", "A casual employee is paid the ordinary hourly rate for their classification plus a casual loading of 25%.", "cl. 10.3", 0.25, applies="casual"),
            item("loading", "An employee working an afternoon shift is paid a loading of 15% of the ordinary hourly rate for each hour of that shift.", "cl. 11.1", 0.15, applies="afternoon shift"),
            item("allowance", "is paid a meal allowance of $18.50.", "cl. 14.1", 18.5, applies="meal"),
            item("one_off", "Each employee covered by this agreement on the day it is approved is paid a one-off payment of $750.", "cl. 15", 750.0, conf="medium"),
            item("none", "is entitled to 14 weeks' paid parental leave at the ordinary hourly rate.", "cl. 20", 14.0, conf="medium"),
            item("BAD", "Night shift workers get thirty percent extra.", "cl. 11.2", 0.30, applies="night shift", conf="low")]
    return out


def landing_files() -> set:
    return set((BUILD / "data" / "landing").rglob("*"))


def main() -> None:
    app = chassis_app.create_app(SHELL, session, roles, blueprints=[M.plan])
    c = app.test_client()
    doc = A.DOCUMENTS / D.NAME
    assert doc.exists(), f"{doc} — generate first"
    text = doc.read_text(encoding="utf-8")
    kinds = [{"code": k, "description": k} for k in ("base_rate", "loading", "allowance", "leave_accrual", "on_cost", "dated_increase", "one_off")]
    saved_env = {k: os.environ.pop(k) for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN") if k in os.environ}

    # the tool, on its own
    stub = Stub(what_a_model_would_say(text))
    out = clauses.propose_entitlements(text, kinds, [], "enterprise_agreement", client=stub)
    assert len(out["rows"]) == 12 and len(out["unplaced"]) == 1 and len(out["refused"]) == 1, {k: len(v) for k, v in out.items()}
    assert out["refused"][0]["clause_ref"] == "cl. 11.2" and "word for word" in out["refused"][0]["refused_because"]
    calls = stub.calls
    try:
        clauses.propose_entitlements(text, kinds, [], "contract_of_employment", client=stub)
        raise AssertionError("an individual's contract was read")
    except clauses.NotCollective:
        assert stub.calls == calls, "refused before anything was sent"
    try:
        clauses.propose_entitlements(text, kinds, [], "award")
        raise AssertionError("ran with no key and no client")
    except MappingUnavailable as e:
        assert "no API key" in str(e)
    print(f"the tool        12 rows, 1 clause under no kind, 1 refused (its quotation is not in the document); a contract refused before sending; no key: did not run")

    landing_before, receipts_before = landing_files(), set(chassis.CONFIG.receipts.glob("*.json"))
    labour_before = q("select round(sum(amount), 2) a from plan.labour_cost")[0]["a"]
    agreements_before = q("select count(*) n from dims.reg_agreement")[0]["n"]
    ran = False

    def take_in(who=HOLDER, kind="enterprise_agreement"):
        session.become(who)
        c.post("/labour/entitlements/take-in", data={"document": D.NAME, "instrument": D.INSTRUMENT, "instrument_name": D.INSTRUMENT_NAME,
                                                     "entity_code": D.ENTITY, "instrument_kind": kind})
        return session.last

    def decide(item, resolution, target="", reason=""):
        session.become(HOLDER)
        c.post("/door/EBA/decide", data={"kind": next(i["kind"] for i in doors.queue("EBA") if i["item_code"] == item), "item_code": item,
                                         "scope_code": "ALL", "resolution": resolution, "target_code": target, "reason": reason, "next": "/labour/entitlements"})
        return session.last

    try:
        assert not take_in(OTHER)["placed"]
        assert not take_in(kind="contract_of_employment")["placed"] and any("not a collective instrument" in x["says"] for x in session.last["checks"] if not x["ok"])
        page = c.get("/labour/entitlements").data.decode()
        assert D.INSTRUMENT_NAME.upper() in page and 'action="/labour/entitlements/take-in"' in page
        print(f"refused         by {OTHER}, and for an individual's contract; nothing placed")

        A.client = None
        r = take_in()
        ran = True
        assert r["placed"] and any(x.get("flag") and "did not run" in x["says"] for x in r["checks"]), r["checks"]
        w = A.waiting_documents()
        assert w and w[0]["name"] == D.NAME and w[0]["not_read"], w
        assert not q("select 1 from dims.reg_entitlement where instrument = ?", D.INSTRUMENT)
        print(f"no key          taken in, not read: '{w[0]['not_read']}' — nothing failed, the document waits for a person")

        A.client = Stub(what_a_model_would_say(text))
        r = take_in()
        assert r["placed"], r["checks"]
        first = next(x["says"] for x in r["checks"] if x["check"] == "the first pass")
        assert not A.waiting_documents()
        items = doors.queue("EBA")
        assert len(items) == 13 and sum(1 for i in items if i["kind"] == "unplaced") == 1, len(items)
        assert not q("select 1 from dims.reg_entitlement where instrument = ?", D.INSTRUMENT) and q("select count(*) n from dims.reg_agreement")[0]["n"] == agreements_before
        page = c.get("/labour/entitlements").data.decode()
        assert "Refused at the door" in page and "thirty percent" in page and "Decide" in page
        print(f"proposed        {first}; 13 wait at the door, the refused row shown and not offered, the labour model reads none")

        by_ref = {i["description"].split(" — ")[0]: i["item_code"] for i in items}
        assert decide(by_ref["Schedule A, item 1"], "accept")["placed"]
        assert decide(by_ref["cl. 14.1"], "alter", "one_off", "paid once per occasion; priced as a one-off in the period")["placed"]
        assert decide(by_ref["cl. 20"], "approximate", "leave_accrual", "parental leave as a leave accrual: 14 weeks on the eligible")["placed"]
        assert decide(by_ref["cl. 15"], "leave_out", "", "not material to the roster's cost")["placed"]
        assert not decide(by_ref["cl. 10.3"], "alter", "bonus", "not a kind")["placed"]
        with app.test_request_context():
            log = M.Runner(A.RUN).run()
        assert "✗" not in log, log[-800:]
        taken = q("select entitlement_id, kind, clause_ref, clause from dims.reg_entitlement where instrument = ? order by clause_ref", D.INSTRUMENT)
        assert [(t["clause_ref"], t["kind"]) for t in taken] == [("Schedule A, item 1", "base_rate"), ("cl. 14.1", "one_off"), ("cl. 20", "leave_accrual")], taken
        assert all(t["clause"] and clauses.quotation_found(t["clause"], text) for t in taken)
        rate = q("select hourly_rate, valid_from_period from dims.reg_agreement where agreement = ? and classification = 'PO1'", D.INSTRUMENT)
        assert rate and rate[0]["hourly_rate"] == D.NEW_RATES["PO1"], rate
        assert q("select round(sum(amount), 2) a from plan.labour_cost")[0]["a"] == labour_before
        left = len(doors.queue("EBA"))
        assert left == 9, left
        print(f"decided         one accepted, one under another kind, the unplaced clause approximated with a note, one left out, an alter to no kind refused; "
              f"the register holds those three with their clauses; the labour model has {D.INSTRUMENT}'s PO1 at ${rate[0]['hourly_rate']:.2f} from {rate[0]['valid_from_period']} "
              f"beside the current agreement; the labour figures unchanged; {left} still wait")
    finally:
        A.client = None
        os.environ.update(saved_env)
        session.become(HOLDER)
        for f in sorted(landing_files() - landing_before, reverse=True):
            f.rmdir() if f.is_dir() else f.unlink()
        for f in set(chassis.CONFIG.receipts.glob("*.json")) - receipts_before:
            f.unlink()
        if ran:
            with app.test_request_context():
                log = M.Runner(A.RUN).run()
            assert "✗" not in log, log[-800:]
            assert not q("select 1 from dims.reg_entitlement where instrument = ?", D.INSTRUMENT)
        print("cleaned up: the take-ins, decisions and receipts removed, the run taken again — the register as it was, the document waiting")


if __name__ == "__main__":
    main()
