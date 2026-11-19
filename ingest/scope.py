"""What a run takes in (DEC-20261119-06): its scope is read from the landing, never written a page at a time.

A register is **waiting** when the files in its landing folder are not the files its table holds — a file placed since
the last load, or one removed (each row carries the file it came from). A run loads the registers waiting and evaluates
the models that first read them (`pipeline.READ_BY`) and everything after; several registers waiting is the union of
their scopes. **Everything** — every table loaded, every model evaluated — only when everything changed: the generated
inputs are newer than the warehouse, or there is no warehouse. Nothing waiting is the evaluation alone, which finds a
changed model and what reads it.

    uv run python -m ingest.scope            # say what the next run takes in
    uv run python -m ingest.scope --run      # and run it
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from ingest.pipeline import HISTORY, PLAN, READ_BY

LOAD = ["uv", "run", "python", "-m", "ingest.pipeline"]
EVALUATE = ["uv", "run", "sqlmesh", "plan", "prod", "--auto-apply", "--no-prompts"]
EVERYTHING = [LOAD, ["uv", "run", "sqlmesh", "plan", "prod", "--restate-model", "*", "--auto-apply", "--no-prompts"]]
GROUPS = (("history", HISTORY), ("plan", PLAN))


def _landed(landing: Path, sub: str, name: str) -> set[str]:
    """The files of a register's landing folder that carry a row — a file with a header alone puts nothing in the table."""
    folder = landing / sub / name
    out = set()
    for f in sorted(folder.glob("*.csv")) if folder.is_dir() else []:
        with f.open(encoding="utf-8") as fh:
            if fh.readline() and fh.readline().strip():
                out.add(f.name)
    return out


def held(query) -> dict[str, set[str]]:
    """The files each table holds, by the file each row came from — `query(sql)` returns rows as tuples or dicts (the
    face passes its own connection's)."""
    def first(r):
        return next(iter(r.values())) if isinstance(r, dict) else r[0]
    tables = {first(r) for r in query("select table_name from information_schema.tables where table_schema = 'bronze'")}
    return {name: {first(r) for r in query(f'select distinct source_file from bronze."{name}"') if first(r)}
            for _, group in GROUPS for name in group if name in READ_BY and name in tables}


def _held(db: Path) -> dict[str, set[str]] | None:
    """What the tables hold, read from the warehouse file; None when there is none."""
    if not db.exists():
        return None
    import duckdb
    con = duckdb.connect(str(db), read_only=True)
    try:
        return held(lambda sql: con.execute(sql).fetchall())
    finally:
        con.close()


def regenerated(root: Path, db: Path) -> bool:
    """The generated inputs written since the warehouse was: everything changed."""
    if not db.exists():
        return True
    built = db.stat().st_mtime
    return any(f.stat().st_mtime > built for f in (root / "data" / "generated").rglob("*.csv"))


def waiting(root: Path, holds: dict[str, set[str]] | None = None, files: bool = False) -> list:
    """The registers whose landing is not what their table holds — or, with `files`, the files placed and not yet taken in."""
    db, landing = root / "data" / "caldera.duckdb", root / "data" / "landing"
    holds = _held(db) if holds is None else holds
    out = []
    for sub, group in GROUPS:
        for name in group:
            if name not in READ_BY:
                continue
            masters = {f"{name}.csv"}                      # the generated register's own rows
            there, taken = _landed(landing, sub, name), (holds or {}).get(name, set()) - masters
            if files:
                out += [landing / sub / name / f for f in sorted(there - taken)]
            elif holds is None or name not in holds or there != taken:
                out.append(name)
    return out


def commands(root: Path, holds: dict[str, set[str]] | None = None) -> list[list[str]]:
    """The run that takes in what is waiting: everything when everything changed; else the registers waiting loaded and
    the models that read them evaluated, with everything after them; else the evaluation alone."""
    db = root / "data" / "caldera.duckdb"
    if regenerated(root, db):
        return EVERYTHING
    regs = waiting(root, holds)
    if not regs:
        return [EVALUATE]
    models = list(dict.fromkeys(m for r in regs for m in READ_BY[r]))
    return [LOAD + ["--only", *regs], EVALUATE[:4] + [x for m in models for x in ("--restate-model", f"{m}+")] + EVALUATE[4:]]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", action="store_true", help="run it")
    ap.add_argument("--everything", action="store_true", help="the whole run, whatever is waiting")
    a = ap.parse_args()
    root = Path.cwd()
    cmds = EVERYTHING if a.everything else commands(root)
    for c in cmds:
        print(" ".join(c[2:]))
    if not a.run:
        return 0
    for c in cmds:
        r = subprocess.run(c, cwd=root)
        if r.returncode:
            return r.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
