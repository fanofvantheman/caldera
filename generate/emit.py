"""Write the synthetic client as files the landing reads. Output under data/generated/ (gitignored):

  reference/*.csv   structures, registers, calendar, versions, roles
  history/*.csv     shipments by material × ship-to × week; price lists
  plan/*.csv        layer entries on a version, the promotions calendar, the terms register
  manifest.json     seed and counts
"""

from __future__ import annotations

import csv
import json
import shutil
from dataclasses import asdict
from pathlib import Path


def _write(path: Path, rows: list[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return 0
    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if v is None else v) for k, v in r.items()})
    return len(rows)


def emit_all(out: Path, tables: dict[str, list[dict]], history: dict[str, list[dict]], plan: dict[str, list[dict]], seed: int) -> dict:
    if out.exists():
        shutil.rmtree(out)
    counts: dict[str, int] = {}
    for name, rows in tables.items():
        counts[name] = _write(out / "reference" / f"{name}.csv", rows)
    for name, rows in history.items():
        counts[name] = _write(out / "history" / f"{name}.csv", rows)
    for name, rows in plan.items():
        counts[name] = _write(out / "plan" / f"{name}.csv", rows)
    manifest = {"seed": seed, "counts": counts}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def dataclass_rows(items) -> list[dict]:
    return [asdict(i) for i in items]
