"""The warehouse, read only. A connection per question, closed at once, so a run can take the file whenever it needs it.
While a run holds the file, reading says so instead of failing."""
from __future__ import annotations

import pathlib

import duckdb

DB = pathlib.Path("data/caldera.duckdb")


class Busy(Exception):
    pass


def q(sql: str, *params) -> list[dict]:
    if not DB.exists():
        raise Busy("the warehouse has not been built yet — run the pipeline")
    try:
        con = duckdb.connect(str(DB), read_only=True)
    except duckdb.IOException as e:
        raise Busy("a run holds the warehouse; try again in a moment") from e
    try:
        cur = con.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        con.close()


def one(sql: str, *params) -> dict | None:
    rows = q(sql, *params)
    return rows[0] if rows else None


def principals() -> list[str]:
    return [r["principal"] for r in q("select distinct principal from dims.ctl_role_assignment order by 1")]


def may(who: str, action: str) -> bool:
    return one("select 1 as ok from dims.effective_entitlements where principal = ? and action = ? limit 1", who, action) is not None


def layers_enterable(who: str) -> list[int]:
    return [int(r["action"].split(".")[1]) for r in q(
        "select distinct action from dims.effective_entitlements where principal = ? and action similar to 'layer\\.[1-9]\\.enter' order by 1", who)]


def versions() -> list[dict]:
    return q("select * from dims.ctl_version order by case status when 'open' then 0 when 'frozen' then 1 else 2 end, version_id")


def open_version() -> str | None:
    r = one("select version_id from dims.ctl_version where status = 'open' order by named_on desc limit 1")
    return r["version_id"] if r else None
