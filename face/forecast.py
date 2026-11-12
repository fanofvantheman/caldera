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

from chassis.landing import LogLanding

from . import FCST_RESOLUTION_COLUMNS, FCST_RUN_COLUMNS, FCST_SERIES_COLUMNS, ROOT

SENDER = "FCS"
OUTBOX = ROOT / "data" / "generated" / "sender"           # where the system's export arrives; read here, never loaded
GENERATED = ROOT / "data" / "generated" / "plan"
RUNS = LogLanding("plan", "fcst_run", FCST_RUN_COLUMNS)
SERIES = LogLanding("plan", "fcst_series", FCST_SERIES_COLUMNS)
RESOLUTIONS = LogLanding("plan", "reg_fcst_resolution", FCST_RESOLUTION_COLUMNS)
LANDINGS = [RUNS, SERIES, RESOLUTIONS]

# what a person may decide about each kind of disagreement: (resolution, what the button says, whether it names one of ours)
RESOLVE = {
    "theirs_not_ours": [("same_as", "The same as one of ours", "material"), ("place_under", "Place under a product", "product"), ("leave_out", "Leave out", None)],
    "ours_not_theirs": [("keep_ours", "Keep our calculation", None), ("zero", "Zero on purpose", None)],
}
SAY = {"same_as": "the same as", "place_under": "placed under", "leave_out": "left out", "keep_ours": "our calculation kept", "zero": "zero on purpose"}
KIND_SAY = {"theirs_not_ours": "in the run, not in the plan", "ours_not_theirs": "in the plan, not in the run"}


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


def resolve(kind: str, item: str, account: str, resolution: str, target: str, reason: str, who: str) -> None:
    now = dt.datetime.now()
    RESOLUTIONS.place([{"resolution_id": f"FR-F-{now.strftime('%Y%m%d-%H%M%S-%f')}", "sender": SENDER, "kind": kind, "item_code": item, "account_code": account,
                        "resolution": resolution, "target_code": target, "reason": reason, "acted_by": who, "acted_at": now.isoformat(timespec="seconds")}], who)


def pending() -> list[pathlib.Path]:
    return [p for land in LANDINGS for p in land.pending()]
