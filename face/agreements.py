"""The agreement door, under Labour → Headcount → Entitlements: a copy of a collective instrument in, its entitlements
proposed as rows under the closed list of kinds, each with its clause quoted; a person accepts or alters each; only
accepted rows are read by the labour model.

Taking a document in is an act by the holder of `register.agreement.maintain`: the document is kept as taken in, and the
shared first-pass tool (`coa_map.clauses`, a real model call when `ANTHROPIC_API_KEY` is set) reads it and proposes rows.
The tool's code — not the model — looks for every quoted clause in the document word for word and refuses a row whose
quotation is not there; a clause the model places under no kind comes back unplaced. Collective instruments only — an
enterprise agreement, an award, a statute; an individual's terms are refused before anything is sent. Without a key
nothing fails: the take-in says the first pass did not run, and the document waits for a person.

The proposals are a register of their own (`plan/reg_entitlement_proposal`); the decisions are acts at a fourth door on
the doors' one model (door EBA: a proposed row is accepted, placed under another kind or left out; an unplaced clause is
closed as not material or approximated under a kind, with a note). `dims.reg_entitlement` reads an accepted row from the
proposal and the act. For pricing a roster for a plan — not an interpretation of an agreement for payroll."""
from __future__ import annotations

import datetime as dt
import re

from chassis import receipts
from chassis.landing import LogLanding
from chassis.warehouse import q
from flask import redirect, request, url_for

from . import ROOT
from .words import said

VERB = "register.agreement.maintain"
DOCUMENTS = ROOT / "data" / "generated" / "documents"          # what has arrived and waits, as text
KEPT = ROOT / "data" / "landing" / "documents"                 # each document as it was taken in
COLUMNS = ["proposal_id", "document", "instrument", "instrument_name", "entity_code", "instrument_kind", "placed", "kind",
           "classification", "classification_name", "applies_to", "value", "from_date", "valid_from_period", "clause_ref", "clause",
           "confidence", "rationale", "refused_because", "taken_in_by", "taken_in_at"]
PROPOSALS = LogLanding("plan", "reg_entitlement_proposal", COLUMNS)
INSTRUMENT_KINDS = {"enterprise_agreement": "an enterprise agreement", "award": "an award", "statute": "a statute"}
RUN = [["uv", "run", "python", "-m", "ingest.pipeline", "--only", "reg_entitlement_proposal", "reg_door_act"],
       ["uv", "run", "sqlmesh", "plan", "prod", "--restate-model", "dims.reg_entitlement+", "--restate-model", "plan.door_act+",
        "--restate-model", "plan.worklist_entitlement_queue+", "--auto-apply", "--no-prompts"]]
client = None                                                  # the model client; a test sets a stub, None means the real one

SECTION = """<h2 id="door">Agreements in<span class="count">a copy of an agreement read into rows for a person to accept — the plan reads only what is accepted</span></h2>
{% if waiting_docs %}<table><thead><tr><th>Waiting</th><th>Arrived</th><th></th></tr></thead><tbody>
{% for d in waiting_docs %}<tr><td><b>{{ d.title }}</b><div class="small muted"><code>{{ d.name }}</code>{% if d.not_read %} · taken in, not read: {{ d.not_read }}{% endif %}</div></td><td class="small">{{ d.arrived }}</td>
<td class="acts">{% if may_door %}<form class="inline" method="post" action="{{ url_for('plan.agreement_take_in') }}"><input type="hidden" name="document" value="{{ d.name }}">
<input name="instrument" size="10" value="{{ d.code }}" aria-label="code"> <input name="instrument_name" size="26" value="{{ d.title_case }}" aria-label="name">
<select name="entity_code">{% for e in entities %}<option value="{{ e.entity_code }}">{{ e.entity_code }} · {{ e.entity_name }}</option>{% endfor %}</select>
<select name="instrument_kind">{% for k, v in instrument_kinds.items() %}<option value="{{ k }}">{{ v }}</option>{% endfor %}</select>
<button class="act" onclick="this.textContent='Reading…'">take in</button></form>{% else %}<span class="small muted">taken in by {{ holders|join(', ') or 'nobody yet' }}</span>{% endif %}</td></tr>{% endfor %}</tbody></table>
{% else %}<p class="muted">No agreement is waiting to be taken in.</p>{% endif %}
<p class="hint">Collective instruments only — an enterprise agreement, an award, a statute; an individual's contract is not sent. Every proposed row carries its clause, quoted; a quotation that is not in the document word for word is refused, and a clause that fits none of the kinds is an item to resolve, not forced into one.</p>
<h3>To decide</h3>""" + "{door_queue}" + """
{% if refused_rows %}<h3>Refused at the door<span class="count">quoted words not found in the document — never offered</span></h3>
<table><thead><tr><th>Document</th><th>Clause</th><th>Proposed</th><th>Why refused</th></tr></thead><tbody>
{% for r in refused_rows %}<tr class="off"><td class="small"><code>{{ r.document }}</code></td><td class="small"><b>{{ r.clause_ref }}</b> “{{ r.clause }}”</td><td class="small">{{ r.kind }}</td><td class="small">{{ r.refused_because }}</td></tr>{% endfor %}</tbody></table>{% endif %}
{% if door_decided %}<h3>Decided</h3>""" + "{door_decided}" + """{% endif %}"""


def _title(path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            return line.strip()
    return path.stem


def proposals() -> list[dict]:
    """Every proposal row placed, including those the warehouse has not yet seen."""
    return PROPOSALS.rows()


def waiting_documents() -> list[dict]:
    """Documents that have arrived and have not been read: never taken in, or taken in when the first pass could not run."""
    read = {r["document"] for r in proposals() if r.get("placed") != "not_read"}
    not_read = {r["document"]: r.get("refused_because") for r in proposals() if r.get("placed") == "not_read"}
    out = []
    for p in sorted(DOCUMENTS.glob("*.txt")) if DOCUMENTS.is_dir() else []:
        if p.name in read:
            continue
        t = _title(p)
        out.append({"name": p.name, "title": t, "title_case": t.title().replace("And ", "and "), "code": p.stem,
                    "arrived": dt.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M"), "not_read": not_read.get(p.name)})
    return out


def _period_of(day: str | None) -> str | None:
    if not day or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        return None
    r = q("select period from dims.dim_period where period_start <= ?::DATE and period_end >= ?::DATE", day, day)
    return r[0]["period"] if r else None


def context(who: str, roles) -> dict:
    from . import doors, reads
    return {"waiting_docs": waiting_documents(), "may_door": roles.may(who, VERB), "instrument_kinds": INSTRUMENT_KINDS,
            "entities": q("select entity_code, entity_name from dims.dim_entity order by 1"), "holders": reads.holders(VERB),
            "refused_rows": [r for r in proposals() if r.get("placed") == "refused"],
            **doors.page_context("EBA", who, next_url=url_for("plan.entitlements") + "#door"), "door_decided": doors.decided("EBA")}


def register(bp, who_fn, session, roles, run_plan, scoped: dict) -> None:
    scoped["agreements"] = {"commands": RUN, "pending": PROPOSALS.pending, "what": "agreements",
                            "says": "run completed — the agreement's proposed rows wait for a decision"}

    @bp.post("/labour/entitlements/take-in")
    def agreement_take_in():
        """A collective instrument taken in: checked, kept as taken in, read by the first pass into proposed rows (or not
        read, when the pass cannot run — nothing fails), placed as one file, receipted, released by a scoped run."""
        from coa_map.clauses import INSTRUMENTS, NotCollective, propose_entitlements
        from coa_map.codes import MappingUnavailable
        f = request.form; who = who_fn()
        name = (f.get("document") or "").strip()
        doc = next((d for d in waiting_documents() if d["name"] == name), None)
        kind = f.get("instrument_kind", "")
        code = (f.get("instrument") or "").strip().upper()
        title = (f.get("instrument_name") or "").strip()
        entity = f.get("entity_code", "")
        may = roles.may(who, VERB)
        known_entity = bool(q("select 1 from dims.dim_entity where entity_code = ?", entity))
        taken = {r["instrument"] for r in q("select distinct instrument from dims.reg_entitlement")}
        checks = [
            {"check": "who may take an agreement in", "ok": may, "says": f"{who} holds {said(VERB)}" if may else f"{who} does not hold {said(VERB)}"},
            {"check": "a document waiting", "ok": doc is not None, "says": f"{name} — {doc['title']}" if doc else f"{name or 'nothing'} is not waiting"},
            {"check": "a collective instrument", "ok": kind in INSTRUMENTS,
             "says": INSTRUMENT_KINDS.get(kind, "") or f"{kind or 'this document'} is not a collective instrument — only an enterprise agreement, an award or a statute is read; an individual's terms are not sent"},
            {"check": "a new instrument for an entity", "ok": known_entity and bool(re.fullmatch(r"[A-Z0-9][A-Z0-9-]{1,30}", code)) and code not in taken and bool(title),
             "says": f"{code} · {title} · {entity}" if known_entity and code not in taken and title else
                     (f"{code} is already on the register" if code in taken else f"a code, a name and one of our entities ({entity or 'none'} given)")},
        ]
        rows: list[dict] = []
        if receipts.judge(checks):
            text = (DOCUMENTS / name).read_text(encoding="utf-8")
            kinds = [{"code": k["kind"], "description": f"{k['kind_label']}: {k['what']}"} for k in q("select kind, kind_label, what from dims.ref_entitlement_kind order by ord")]
            classes = [{"code": c["classification"], "description": c["classification_name"]} for c in
                       q("""select distinct classification, classification_name from dims.reg_entitlement
                            where layer = 'agreement' and entity_code = ? and classification is not null order by 1""", entity)]
            cname = {c["code"]: c["description"] for c in classes}
            now = dt.datetime.now(); stamp = now.strftime("%Y%m%d-%H%M%S"); when = now.isoformat(timespec="seconds")
            base = {"document": name, "instrument": code, "instrument_name": title, "entity_code": entity, "instrument_kind": kind,
                    "taken_in_by": who, "taken_in_at": when}
            try:
                out = propose_entitlements(text, kinds, classes, kind, client=client,
                                           guidance="Rates are dollars per ordinary hour; a loading or an increase is a share of the ordinary rate.")
                dates = [r.get("from_date") for r in out["rows"] if _period_of(r.get("from_date"))]
                start = _period_of(min(dates)) if dates else None
                for placed in ("rows", "unplaced", "refused"):
                    for r in out[placed]:
                        rows.append({**base, "proposal_id": f"EP-{code}-{stamp}-{len(rows) + 1:03d}",
                                     "placed": {"rows": "row", "unplaced": "unplaced", "refused": "refused"}[placed],
                                     "kind": r.get("kind", ""), "classification": r.get("classification", ""), "classification_name": cname.get(r.get("classification", ""), ""),
                                     "applies_to": r.get("applies_to", ""), "value": r.get("value"), "from_date": r.get("from_date", ""),
                                     "valid_from_period": _period_of(r.get("from_date")) or start or "", "clause_ref": r.get("clause_ref", ""),
                                     "clause": r.get("quote", ""), "confidence": r.get("confidence", ""), "rationale": r.get("rationale", ""),
                                     "refused_because": r.get("refused_because", "")})
                n = {p: sum(1 for r in rows if r["placed"] == p) for p in ("row", "unplaced", "refused")}
                checks.append({"check": "the first pass", "ok": True,
                               "says": f"{n['row']} rows proposed under the kinds · {n['unplaced']} under no kind, to resolve · {n['refused']} refused: the quotation is not in the document"})
            except (MappingUnavailable, NotCollective) as e:
                rows.append({**base, "proposal_id": f"EP-{code}-{stamp}-000", "placed": "not_read", "refused_because": str(e)})
                checks.append({"check": "the first pass", "ok": False, "flag": True,
                               "says": f"did not run — {e}; the document waits for a person"})
        placed = receipts.judge(checks)
        if placed:
            KEPT.mkdir(parents=True, exist_ok=True)
            (KEPT / f"{rows[0]['taken_in_at'].replace(':', '')}-{name}").write_text((DOCUMENTS / name).read_text(encoding="utf-8"), encoding="utf-8")
            PROPOSALS.place(rows, who)
        session.last = receipts.write("agreement.take_in", who, name or "nothing", checks, placed)
        if not placed:
            session.say("not taken in: " + "; ".join(c["says"] for c in checks if not c["ok"] and not c.get("flag")), False)
            return redirect(url_for("plan.entitlements") + "#door")
        if run_plan(who, "agreements"):
            session.say(f"{name} taken in — " + next(c["says"] for c in checks if c["check"] == "the first pass"), True)
            return redirect(url_for("plan.entitlements") + "#door")
        return redirect(url_for("plan.run"))
