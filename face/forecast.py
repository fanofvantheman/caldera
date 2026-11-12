"""The forecasting system's door, as the face sees it: the runs waiting in its outbox, what has been taken in, and the
log of what people decided where its structures and the plan's disagree.

The face is the landing's only writer. Taking a run in writes its header and its series to the landing, stamped with
the version and the moment; a run replaces the one before it whole, so the latest taken in is the one the plan reads.
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


def taken_in() -> dict[str, str]:
    """Every run already taken in → when: the one loaded with the build, then every take-in the face made."""
    out = {}
    for r in _csv(GENERATED / "fcst_run.csv") + RUNS.rows():
        out[r["run_id"]] = r["taken_in_at"]
    return out


def sender_runs() -> list[dict]:
    """The runs in the system's outbox, each with its header, its series and whether it has been taken in."""
    done = taken_in()
    runs = []
    for p in sorted(OUTBOX.glob("*_run.csv")) if OUTBOX.is_dir() else []:
        rid = p.name[: -len("_run.csv")]
        head = _csv(p)
        if head:
            series = _csv(OUTBOX / f"{rid}_series.csv")
            runs.append({"run_id": rid, "header": head[0], "series": series, "taken_in_at": done.get(rid),
                         "n_series": len({(s["material_code"], s["account_code"]) for s in series})})
    return runs


def waiting() -> list[dict]:
    return [r for r in sender_runs() if not r["taken_in_at"]]


def take_in(run: dict, version: str, who: str) -> None:
    at = dt.datetime.now().isoformat(timespec="seconds")
    stamp = {"sender": SENDER, "run_id": run["run_id"], "version_id": version, "taken_in_at": at}
    RUNS.place([{**run["header"], **stamp, "taken_in_by": who}], who)
    SERIES.place([{**s, **stamp} for s in run["series"]], who)


def pending() -> list[pathlib.Path]:
    return [p for land in LANDINGS for p in land.pending()]
