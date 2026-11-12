"""The promotions doors, as the face sees them: the sender's files waiting in its outbox, what has been taken in, the
codes the mapping already holds, and the first pass that proposes a mapping for a code nobody has mapped.

The face is the landing's only writer. Taking a sender file in writes its header and funding lines to the landing in
our layout, stamped with the version, the file and the moment; the codes in it that no mapping row has ever named are
then given to the shared mapping tool (`coa_map.codes`), and what it proposes is written to the mapping register as
proposed — once per code; a code already on the register, in whatever state, is never proposed again. With no API key
the pass says so and the codes wait for a person on the mapping review; nothing fails."""
from __future__ import annotations

import csv
import datetime as dt
import pathlib

from chassis.door import Declaration
from chassis.landing import LogLanding

from . import NEIGHBOUR_COLUMNS, PROMO_EVENT_COLUMNS, ROOT, TPM_EVENT_COLUMNS, TPM_FUNDING_COLUMNS
from . import reads
from .doors import TPM as DOOR

SENDER = "TPM"
OUTBOX = ROOT / "data" / "generated" / "sender"           # where the sender's export arrives; read here, never loaded
GENERATED = ROOT / "data" / "generated" / "plan"
TPM_EVENTS = LogLanding("plan", "tpm_event", TPM_EVENT_COLUMNS)
TPM_FUNDING = LogLanding("plan", "tpm_funding", TPM_FUNDING_COLUMNS)
TYPED = LogLanding("plan", "reg_promo_event", PROMO_EVENT_COLUMNS)
NEIGHBOURS = LogLanding("plan", "reg_promo_neighbour", NEIGHBOUR_COLUMNS)
LANDINGS = [TPM_EVENTS, TPM_FUNDING, TYPED, NEIGHBOURS]          # the mapping's acts are the doors' register (doors.ACTS)
SUBJECTS = ["customer", "material", "mechanic", "funding_type", "status"]
SAY = {"customer": "planning account", "material": "product group", "mechanic": "tactic", "funding_type": "fund type", "status": "status"}

# what the first pass is told about each subject
GUIDANCE = {
    "customer": "The sender's planning account is the customer an event is negotiated with. Map it to our trading account by "
                "name; a banner or a national account of a retailer is that retailer's account.",
    "material": "The sender's product group is the range an event promotes. Map it to our promo group — a set of materials "
                "promoted together — by brand, category and pack size.",
    "mechanic": "The sender's tactic is what the shopper sees. Map it to our mechanic: half price is 50% off the shelf; a "
                "smaller temporary price cut is price_cut; x-for-$y and buy-one-get-one are multi_buy; a catalogue, "
                "catalogue page with no price change is catalogue_feature; a gondola end or off-location display with no price "
                "change is gondola_end; a bonus or on-pack offer is bonus_pack; a Christmas, Easter or other themed display "
                "is seasonal_event; in-store sampling is sampling; loyalty points or a personalised offer is points_offer; a "
                "run-out of a range leaving the shelf is clearance. A price promotion supported by a catalogue or display is "
                "still its price mechanic. Use unclassified only when none fits.",
    "funding_type": "The sender's fund type is what the supplier pays for an event and how. Map it to our funding type by "
                    "what it is charged on: an off-invoice or on-invoice deal per case in the shopper window is "
                    "price_reduction_per_case; a rebate per unit or case sold through the till is scan_per_case; a fee for "
                    "a catalogue, display or placement is fixed_fee; retail media or advertising is media; spend drawn "
                    "from an annual co-op fund or envelope is envelope_drawdown; a deal per case bought in a buy-in window is "
                    "case_deal; a claim per unit after the event is bill_back; free stock is free_goods. Use "
                    "unclassified only when none fits.",
    "status": "The sender's status word for an event. Map it to our status: agreed with the customer, proposed (a "
              "candidate, draft or pending), executed, evaluated, or cancelled.",
}


def _csv(path: pathlib.Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def taken_in() -> dict[str, str]:
    """Every sender file already taken in → when: the export loaded with the build, then every take-in the face made."""
    out = {}
    for r in _csv(GENERATED / "tpm_event.csv") + TPM_EVENTS.rows():
        out.setdefault(r["sender_file"], r["taken_in_at"])
    return out


def sender_files() -> list[dict]:
    """The sender's files in its outbox, each with its events and whether it has been taken in."""
    done = taken_in()
    files = []
    for p in sorted(OUTBOX.glob("*_events.csv")) if OUTBOX.is_dir() else []:
        fid = p.name[: -len("_events.csv")]
        head, fund = _csv(p), _csv(OUTBOX / f"{fid}_funding.csv")
        files.append({"file_id": fid, "events": head, "funding": fund, "taken_in_at": done.get(fid)})
    for fid, at in done.items():
        if not any(f["file_id"] == fid for f in files):
            files.append({"file_id": fid, "events": [], "funding": [], "taken_in_at": at})
    return files


def waiting() -> list[dict]:
    return [f for f in sender_files() if not f["taken_in_at"] and f["events"]]


def known_codes() -> set[tuple[str, str, str]]:
    """Every (sender, subject, local code) the door's act register has ever named, in any state — such a code is never
    proposed again."""
    return {(SENDER, kind, item) for kind, item, _ in DOOR.known()}


def codes_in(events: list[dict], funding: list[dict]) -> dict[str, dict[str, str]]:
    """The distinct local codes a file uses, per subject, with the description the sender gave each."""
    out: dict[str, dict[str, str]] = {s: {} for s in SUBJECTS}
    for e in events:
        out["customer"].setdefault(e["planning_account"], e.get("planning_account_name") or "")
        out["material"].setdefault(e["product_group"], e.get("product_group_name") or "")
        out["mechanic"].setdefault(e["tactic"], e.get("tactic_name") or "")
        out["status"].setdefault(e["status"], e["status"])
    for f in funding:
        out["funding_type"].setdefault(f["fund_type"], f.get("fund_type_name") or "")
    return out


def unmapped(codes: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    known = known_codes()
    return {s: {c: d for c, d in cs.items() if (SENDER, s, c) not in known} for s, cs in codes.items()}


def first_pass(codes: dict[str, dict[str, str]], who: str) -> tuple[int, str, bool]:
    """Propose a target for every code given, subject by subject, and write each proposal to the mapping register as
    proposed. Returns (proposals written, what to say, whether the pass ran)."""
    n_codes = sum(len(c) for c in codes.values())
    if not n_codes:
        return 0, "every code has been proposed or mapped already — nothing new for the first pass", True
    try:
        from coa_map.codes import MappingUnavailable, credentials_present, map_codes
    except ImportError:
        return 0, f"the mapping tool is not installed — the first pass did not run; {n_codes} code{'s' if n_codes > 1 else ''} wait for a person", False
    if not credentials_present():
        return 0, f"no API key in the environment — the first pass did not run; {n_codes} code{'s' if n_codes > 1 else ''} wait for a person on the mapping review", False
    rows, said, ran = [], [], True
    for subject, cs in codes.items():
        if not cs:
            continue
        try:
            got = map_codes([{"code": c, "description": d} for c, d in cs.items()], reads.mapping_targets(subject), GUIDANCE[subject], subject)
        except MappingUnavailable as e:
            said.append(str(e)); ran = False
            break                                       # one cause stops every subject alike
        for g in got:                                   # each proposal is a proposed act on the item, never in force
            rows.append({"kind": subject, "item_code": g["code"], "target_code": g["target"], "confidence": g["confidence"],
                         "rationale": g["rationale"], "item_description": cs[g["code"]]})
    DOOR.propose(rows, who)
    left = n_codes - len(rows)
    msg = f"first pass proposed {len(rows)} mapping{'' if len(rows) == 1 else 's'} for review"
    if left:
        msg += f"; {left} code{'s' if left > 1 else ''} wait for a person" + (f" ({'; '.join(said)})" if said else "")
    return len(rows), msg, ran


# what a file must say about itself to be let in — checked as data at the take-in (the header is the file, the rows its events)
DECLARATIONS = [
    Declaration("every event dated",
                lambda f, evs: bool(evs) and all(e.get("event_id") and _ordered(e.get("shopper_start"), e.get("shopper_end")) for e in evs),
                "every event has an id and an ordered shopper window", "an event has no id or its window is missing or reversed"),
    Declaration("every funding line on an event",
                lambda f, evs: all(x.get("event_id") in {e.get("event_id") for e in evs} and _num(x.get("rate")) for x in f.get("funding", [])),
                "every funding line names an event in the file and carries a rate", "a funding line names no event in the file, or has no rate"),
]


def _ordered(a: str | None, b: str | None) -> bool:
    try:
        return dt.date.fromisoformat(a or "") <= dt.date.fromisoformat(b or "")
    except ValueError:
        return False


def _num(x) -> bool:
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False


def take_in(f: dict, version: str, who: str) -> None:
    """The sender's file into the landing, in our layout, stamped with the version, the file and the moment."""
    at = dt.datetime.now().isoformat(timespec="seconds")
    stamp = {"sender": SENDER, "sender_file": f["file_id"], "version_id": version, "taken_in_at": at}
    TPM_EVENTS.place([{**stamp, "taken_in_by": who, **e} for e in f["events"]], who)
    TPM_FUNDING.place([{**stamp, **x} for x in f["funding"]], who)


def pending() -> list[pathlib.Path]:
    return [p for land in LANDINGS for p in land.pending()]
