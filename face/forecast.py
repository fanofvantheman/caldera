"""The forecasting system's door, as the face sees it: the runs waiting in its outbox, what has been taken in, and the
log of what people decided where its structures and the plan's disagree.

The face is the landing's only writer. A run arrives once and is taken in account by account, by the planner whose scope
reaches the account: each take-in writes the run's header for that account and that account's series to the landing,
stamped with the version and the moment; for each account the latest run taken in is the one the plan reads, so a run
can be in force for one account and still waiting for another.
A run says what its numbers are, and one that does not say they are baseline only — promotions removed — is refused
here: the plan adds promotions itself, and would count every event twice."""
from __future__ import annotations

import csv
import datetime as dt
import pathlib

from chassis.door import Declaration
from chassis.landing import LogLanding

from . import FCST_RUN_COLUMNS, FCST_SERIES_COLUMNS, ROOT
from .doors import FCS as DOOR

SENDER = "FCS"
OUTBOX = ROOT / "data" / "generated" / "sender"           # where the system's export arrives; read here, never loaded
GENERATED = ROOT / "data" / "generated" / "plan"
RUNS = LogLanding("plan", "fcst_run", FCST_RUN_COLUMNS)
SERIES = LogLanding("plan", "fcst_series", FCST_SERIES_COLUMNS)
LANDINGS = [RUNS, SERIES]


def _d(x: str | None) -> bool:
    try:
        dt.date.fromisoformat(x or "")
        return True
    except ValueError:
        return False


def _f(x) -> bool:
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False


# what a run must say about itself to be let in — checked as data at the take-in
DECLARATIONS = [
    Declaration("the run says what it is",
                lambda h, rows: bool(h.get("made_on") and h.get("last_history_week") and _d(h.get("first_week")) and _f(h.get("horizon_weeks")) and h.get("content")),
                lambda h, rows: f"made {h.get('made_on')}, history to {h.get('last_history_week')}, {h.get('horizon_weeks')} weeks from {h.get('first_week')}",
                "the header does not say when it was made, what history it used, how far it reaches or what the numbers are"),
    Declaration("baseline only", lambda h, rows: h.get("content") == "baseline_only",
                "promotions removed — the plan adds them from the calendar",
                lambda h, rows: f"the run says its numbers are {h.get('content') or 'unstated'}: with promotions left in, the plan would count every event twice — ask the forecasting system for the baseline"),
    Declaration("every row whole",
                lambda h, rows: bool(rows) and all(x.get("material_code") and x.get("account_code") and _d(x.get("week_start")) and _f(x.get("cases")) for x in rows),
                "every row names a material, an account and a week and carries cases", "a row is missing its material, account, week or cases"),
]


def _csv(path: pathlib.Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def taken_in() -> dict[tuple[str, str], dict]:
    """Every (run, account) already taken in → its header row: the take-ins loaded with the build, then every one the face made."""
    out = {}
    for r in _csv(GENERATED / "fcst_run.csv") + RUNS.rows():
        out[(r["run_id"], r.get("account_code") or "")] = r
    return out


def sender_runs() -> list[dict]:
    """The runs in the system's outbox, each with its header, its series and, per account it serves, what it sends and
    whether that account has taken it in. The file arrives once; each account takes in its own series."""
    done = taken_in()
    runs = []
    for p in sorted(OUTBOX.glob("*_run.csv")) if OUTBOX.is_dir() else []:
        rid = p.name[: -len("_run.csv")]
        head = _csv(p)
        if head:
            series = _csv(OUTBOX / f"{rid}_series.csv")
            accts: dict[str, dict] = {}
            for s_ in series:
                a = accts.setdefault(s_["account_code"], {"account_code": s_["account_code"], "keys": set(), "cases": 0.0, "materials": set()})
                a["keys"].add(s_["material_code"]); a["materials"].add(s_["material_code"])
                try:
                    a["cases"] += float(s_["cases"])
                except ValueError:
                    pass
            accounts = []
            for code in sorted(accts):
                a = accts[code]; t = done.get((rid, code))
                accounts.append({"account_code": code, "n_series": len(a["keys"]), "cases": a["cases"], "materials": sorted(a["materials"]),
                                 "taken_in_at": t["taken_in_at"] if t else None, "taken_in_by": t.get("taken_in_by") if t else None})
            runs.append({"run_id": rid, "header": head[0], "series": series, "accounts": accounts,
                         "taken_in_at": max((a["taken_in_at"] for a in accounts), default=None) if accounts and all(a["taken_in_at"] for a in accounts) else None,
                         "n_series": len({(s_["material_code"], s_["account_code"]) for s_ in series})})
    return runs


def waiting(accounts: set[str] | None = None) -> list[dict]:
    """Runs with an account still to take them in — of the given accounts, when given."""
    out = []
    for r in sender_runs():
        left = [a for a in r["accounts"] if not a["taken_in_at"] and (accounts is None or a["account_code"] in accounts)]
        if left:
            out.append({**r, "left": left})
    return out


def take_in(run: dict, account: str, version: str, who: str) -> None:
    """One account's series from a run into the landing, with the run's header stamped for that account."""
    at = dt.datetime.now().isoformat(timespec="seconds")
    stamp = {"sender": SENDER, "run_id": run["run_id"], "version_id": version, "taken_in_at": at}
    RUNS.place([{**run["header"], **stamp, "account_code": account, "taken_in_by": who}], who)
    SERIES.place([{**s, **stamp} for s in run["series"] if s["account_code"] == account], who)


def pending() -> list[pathlib.Path]:
    return [p for land in LANDINGS for p in land.pending()]
