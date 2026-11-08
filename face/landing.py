"""The landing's only writer. An act is a file: one CSV, one or more rows, named by the moment and the actor, placed under
data/landing/plan/<table>/. Files are never edited or removed; a withdrawal is a later row that names the entry it
withdraws. File order is time order, and the next load reads them all after the generated file."""
from __future__ import annotations

import csv
import datetime as dt
import pathlib
import re

LANDING = pathlib.Path("data/landing")
ENTRY_COLUMNS = ["entry_id", "action", "withdraws", "version_id", "layer_no", "entered_by", "entered_on", "reason_code", "effect_type",
                 "scope_material", "scope_customer", "period_from", "period_to", "value_kind", "value", "spread_rule", "note"]


def _stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def _place(table: str, rows: list[dict], who: str) -> pathlib.Path:
    folder = LANDING / "plan" / table
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{_stamp()}-{re.sub(r'[^a-z0-9]+', '-', who.lower())}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=ENTRY_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in ENTRY_COLUMNS})
    return path


def enter(entry: dict, who: str) -> str:
    entry_id = f"LE-F-{_stamp()}"
    row = {"entry_id": entry_id, "action": "enter", "withdraws": "", "entered_by": who, "entered_on": dt.date.today().isoformat(), **entry}
    _place("layer_entry", [row], who)
    return entry_id


def withdraw(entry_id: str, version_id: str, layer_no: int, who: str, note: str = "") -> None:
    row = {"entry_id": f"LW-F-{_stamp()}", "action": "withdraw", "withdraws": entry_id, "version_id": version_id, "layer_no": layer_no,
           "entered_by": who, "entered_on": dt.date.today().isoformat(), "reason_code": "", "effect_type": "primary", "scope_material": "",
           "scope_customer": "", "period_from": "", "period_to": "", "value_kind": "cases", "value": 0, "spread_rule": "baseline_shape", "note": note}
    _place("layer_entry", [row], who)


def pending() -> list[pathlib.Path]:
    """Files placed since the warehouse was last built."""
    db = pathlib.Path("data/caldera.duckdb")
    built = db.stat().st_mtime if db.exists() else 0
    return sorted(p for p in (LANDING / "plan").rglob("*.csv") if p.stat().st_mtime > built)
