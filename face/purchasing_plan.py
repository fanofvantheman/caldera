"""The purchasing plan held apart from the Plan (DEC-20261120-04): the material planner works the material balance in a
workspace of its own and publishes only the additional receipts it typed; the Plan takes them in through the contract
and proposes the rest again; what comes back is a revision of consumption the planner may take.

Where things are — folders under the build's data, the cheapest form (point 2; any of them can become a store later):

  shared/revisions/consumption/<plan>/<revision>/   what the Plan publishes after a run: the consumption of the key
                                                    materials, with the prices they are bought at — the Plan's figures
                                                    the purchasing plan reads, and nothing else of the Plan's
  workspaces/purchasing/<plan>/pin.json             the revision the purchasing plan reads (its pin)
  workspaces/purchasing/<plan>/receipts.csv         the receipts typed in the workspace — its own, and all it writes
  shared/contract/purchase_receipts/<arrival>.json  each publication as it arrived: from where, made against what,
                                                    what was taken, dropped and found clashing

What the purchasing plan reads (point 3): the pinned revision for consumption and price; the stock on hand and the
contracted receipts as the material master declares them (the ERP's, at the cutoff); master data. Never the Plan's
figures as they stand. The Plan reads nothing of the workspace — only the receipts that arrive through `arrive`, from the
workspace or from a spreadsheet alike, written to the Plan's own register of typed purchases.

The balance on both sides is `calc.purchases`, so nothing is built twice."""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import pathlib

import duckdb
from chassis import CONFIG, receipts
from chassis.landing import LogLanding
from chassis.warehouse import q

from calc import purchases as P

ACT_COLUMNS = ["act_id", "action", "withdraws", "version_id", "input_code", "plant_code", "period", "quantity", "price", "reason", "entered_by", "entered_at"]
ACTS = LogLanding("plan", "reg_purchase_act", ACT_COLUMNS)           # the Plan's register: where an arrival is written
RECEIPT_COLUMNS = ["input_code", "plant_code", "period", "quantity", "price", "reason", "entered_by", "entered_at", "published"]
SHEET_COLUMNS = ["input_code", "plant_code", "period", "quantity", "price", "reason"]   # the contract's shape for receipts

# the Plan's figures a revision carries: each one's query, one parameter, the Plan
REVISION = {
    "plan.material_requirement": "select * from plan.material_requirement where version_id = ? order by input_code, plant_code, period",
    "plan.input_price_in_force": """select * from plan.input_price_in_force where version_id = ? and input_code in (select input_code from dims.ref_key_material)
                                    order by input_code, period""",
    "plan.assumption_in_force": """select version_id, assumption_code, period, value from plan.assumption_in_force where version_id = ?
                                   and assumption_code in (select contract_index from dims.ref_key_material where contract_index is not null)
                                   order by assumption_code, period""",
}


def _data() -> pathlib.Path:
    return CONFIG.db.parent


def _revisions_dir(version: str) -> pathlib.Path:
    return _data() / "shared" / "revisions" / "consumption" / version


def _workspace(version: str) -> pathlib.Path:
    return _data() / "workspaces" / "purchasing" / version


def _arrivals() -> pathlib.Path:
    return _data() / "shared" / "contract" / "purchase_receipts"


def _csv(rows: list[dict]) -> str:
    if not rows:
        return ""
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=list(rows[0]))
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if v is None else v) for k, v in r.items()})
    return out.getvalue()


# ── what comes back: revisions of consumption ───────────────────────────────────────────────────────────────────────────

def revisions(version: str) -> list[dict]:
    """The revisions the Plan has published, oldest first."""
    d = _revisions_dir(version)
    out = [json.loads((x / "revision.json").read_text()) for x in sorted(d.iterdir()) if (x / "revision.json").exists()] if d.is_dir() else []
    return sorted(out, key=lambda r: r["published_at"])


def publish(version: str) -> dict:
    """The Plan publishes its consumption of the key materials, with their prices, as a revision — a new one only when
    the figures differ from the last. Called after a run (the Plan's side)."""
    tables = {t: _csv(q(sql, version)) for t, sql in REVISION.items()}
    digest = hashlib.sha1("".join(tables[t] for t in sorted(tables)).encode()).hexdigest()[:10]
    last = (revisions(version) or [None])[-1]
    if last and last["digest"] == digest:
        return last
    now = dt.datetime.now()
    rev = {"revision": f"{now:%Y%m%d-%H%M%S}-{digest}", "digest": digest, "version": version, "published_at": now.isoformat(timespec="seconds"),
           "rows": {t: max(0, tables[t].count("\n") - 1) for t in tables}}
    d = _revisions_dir(version) / rev["revision"]
    d.mkdir(parents=True, exist_ok=True)
    for t, text in tables.items():
        (d / f"{t}.csv").write_text(text or "version_id\n")
    (d / "revision.json").write_text(json.dumps(rev, indent=1))
    return rev


def publish_open() -> None:
    """After a run: a revision for every open Plan whose consumption moved."""
    for v in q("select version_id from dims.ctl_version where status = 'open' and version_kind <> 'actual'"):
        publish(v["version_id"])


# ── the workspace ──────────────────────────────────────────────────────────────────────────────────────────────────────

def pin(version: str) -> dict | None:
    p = _workspace(version) / "pin.json"
    return json.loads(p.read_text()) if p.exists() else None


def take(version: str, revision: str, who: str) -> dict:
    """The purchasing plan takes a revision: its pin moves to it. Only the planner's act moves it."""
    if revision not in {r["revision"] for r in revisions(version)}:
        raise ValueError(f"no revision {revision} of {version}")
    d = _workspace(version)
    d.mkdir(parents=True, exist_ok=True)
    p = {"consumption": revision, "taken_at": dt.datetime.now().isoformat(timespec="seconds"), "taken_by": who}
    (d / "pin.json").write_text(json.dumps(p, indent=1))
    return p


def state(version: str, who: str) -> dict:
    """The pin and whether it is behind. A workspace with no pin takes the latest revision the first time it is opened
    (publishing one if the Plan has none yet)."""
    revs = revisions(version) or [publish(version)]
    p = pin(version) or take(version, revs[-1]["revision"], who)
    pinned = next((r for r in revs if r["revision"] == p["consumption"]), None)
    return {"pin": p, "pinned": pinned, "latest": revs[-1], "behind": revs[-1]["revision"] != p["consumption"]}


def typed(version: str) -> list[dict]:
    """The receipts typed in the workspace, a cell a row."""
    p = _workspace(version) / "receipts.csv"
    if not p.exists():
        return []
    with p.open(newline="", encoding="utf-8") as f:
        return [{**r, "quantity": float(r["quantity"]) if r["quantity"] else None, "price": float(r["price"]) if r["price"] else None} for r in csv.DictReader(f)]


def _save(version: str, rows: list[dict]) -> None:
    d = _workspace(version)
    d.mkdir(parents=True, exist_ok=True)
    with (d / "receipts.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=RECEIPT_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in RECEIPT_COLUMNS})


def type_cells(version: str, cells: dict, reason: str, who: str) -> None:
    """Cells typed in the workspace: {(input, plant, period): {"quantity": x?, "price": y?}} — a cell typed again is
    replaced, and is unpublished until published."""
    rows = {(r["input_code"], r["plant_code"], r["period"]): r for r in typed(version)}
    now = dt.datetime.now().isoformat(timespec="seconds")
    for (i, pl, per), d in cells.items():
        was = rows.get((i, pl, per)) or {}
        rows[(i, pl, per)] = {"input_code": i, "plant_code": pl, "period": per,
                              "quantity": d.get("quantity") if d.get("quantity") is not None else was.get("quantity"),
                              "price": d.get("price") if d.get("price") is not None else was.get("price"),
                              "reason": reason, "entered_by": who, "entered_at": now, "published": ""}
    _save(version, sorted(rows.values(), key=lambda r: (r["input_code"], r["plant_code"], r["period"])))


def drop(version: str, cell: tuple[str, str, str]) -> None:
    _save(version, [r for r in typed(version) if (r["input_code"], r["plant_code"], r["period"]) != cell])


def balance(version: str, who: str) -> tuple[list[dict], dict]:
    """The workspace's material balance: `calc.purchases` over the pinned revision, the material master and the
    workspace's own typed receipts — and the pin it was made against."""
    st = state(version, who)
    d = _revisions_dir(version) / st["pin"]["consumption"]
    con = duckdb.connect()

    def T(t: str) -> str:
        return f"read_csv_auto('{(d / (t + '.csv')).as_posix()}', header=true, all_varchar=false)" if t in REVISION else t

    def fetch(sql: str) -> list[dict]:
        if "read_csv_auto(" not in sql:
            return q(sql)
        cur = con.execute(sql)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    acts = [{**r, "version_id": version, "act_id": f"workspace:{r['input_code']}:{r['plant_code']}:{r['period']}"} for r in typed(version)]
    try:
        return P.compute_all(fetch, T, version, acts=acts), st
    finally:
        con.close()


# ── the contract: what arrives at the Plan ───────────────────────────────────────────────────────────────────────────

def arrive(version: str, rows: list[dict], source: str, who: str, made_against: str | None = None) -> tuple[list[dict], bool, dict]:
    """Receipts published into the Plan: checked against the contract's shape, a period the Plan no longer plans dropped,
    a cell where the Plan already holds a different typed figure shown as a clash (the arrival stands, latest wins, as
    every act does), and each one written to the Plan's register of typed purchases. `source` is the workspace or a
    spreadsheet; nothing else differs. Returns the receipt's checks, whether anything was placed, and the arrival."""
    from . import reads
    v = reads.version(version) or {}
    plan_periods = set(reads.version_periods(version)["plan"])
    keys = {(k["input_code"], k["plant_code"]) for k in q("select input_code, plant_code from dims.ref_key_material")}
    standing = {(a["input_code"], a["plant_code"], a["period"]): a for a in q("select * from plan.purchase_act where version_id = ?", version)}
    taken, dropped, refused, clashes = [], [], [], []
    for r in rows:
        cell = (str(r.get("input_code") or ""), str(r.get("plant_code") or ""), str(r.get("period") or ""))
        try:
            qty = float(r["quantity"]) if r.get("quantity") not in (None, "") else None
            pr = float(r["price"]) if r.get("price") not in (None, "") else None
        except (TypeError, ValueError):
            refused.append(f"{':'.join(cell)}: not a number"); continue
        if cell[:2] not in keys:
            refused.append(f"{cell[0] or 'nothing'} at {cell[1] or '—'} is not a key material"); continue
        if (qty is None and pr is None) or (qty is not None and qty < 0) or (pr is not None and pr <= 0):
            refused.append(f"{':'.join(cell)}: a quantity not below zero or a price above it"); continue
        if cell[2] not in plan_periods:
            dropped.append(f"{':'.join(cell)}: not a plan period of {version}"); continue
        s = standing.get(cell)
        if s and (s["quantity"] != qty or s["price"] != pr):
            clashes.append(f"{':'.join(cell)}: the Plan held {s['quantity'] if s['quantity'] is not None else '—'} at {s['price'] if s['price'] is not None else '—'} ({s['entered_by']})")
        taken.append({"cell": cell, "quantity": qty, "price": pr, "reason": (r.get("reason") or "").strip()})
    checks = [
        {"check": "the Plan is open", "ok": v.get("status") == "open", "says": f"{version} is {v.get('status', 'unknown')}"},
        {"check": "the form of a receipt", "ok": not refused and bool(taken), "says": "; ".join(refused) if refused else f"{len(taken)} receipt{'s' if len(taken) != 1 else ''} from {source}" if taken else "nothing to publish"},
        {"check": "a reason on each", "ok": all(t["reason"] for t in taken), "says": "each receipt says why" if all(t["reason"] for t in taken) else "a receipt with no reason"},
        {"check": "periods the Plan plans", "ok": True, "flag": bool(dropped), "says": ("dropped: " + "; ".join(dropped)) if dropped else "every period is planned"},
        {"check": "clashes", "ok": True, "flag": bool(clashes), "says": ("the arrival stands: " + "; ".join(clashes)) if clashes else "none"},
    ]
    placed = receipts.judge(checks)
    now = dt.datetime.now()
    arrival = {"arrival": f"{now:%Y%m%d-%H%M%S-%f}", "version": version, "source": source, "made_against": made_against,
               "cutoff": v.get("from_period"), "by": who, "at": now.isoformat(timespec="seconds"), "placed": placed,
               "taken": [{"input_code": t["cell"][0], "plant_code": t["cell"][1], "period": t["cell"][2], "quantity": t["quantity"], "price": t["price"]} for t in taken] if placed else [],
               "dropped": dropped, "refused": refused, "clashes": clashes}
    if placed:
        prefix = "PUB" if source == "the purchasing plan" else "SHT"
        ACTS.place([{"act_id": f"{prefix}-{now:%Y%m%d%H%M%S%f}-{i:03d}", "action": "set", "version_id": version, "input_code": t["cell"][0], "plant_code": t["cell"][1],
                     "period": t["cell"][2], "quantity": t["quantity"], "price": t["price"], "reason": t["reason"], "entered_by": who,
                     "entered_at": now.isoformat(timespec="seconds")} for i, t in enumerate(taken, start=1)], who)
    _arrivals().mkdir(parents=True, exist_ok=True)
    (_arrivals() / f"{arrival['arrival']}.json").write_text(json.dumps(arrival, indent=1))
    return checks, placed, arrival


def publish_workspace(version: str, who: str) -> tuple[list[dict], bool, dict]:
    """The workspace's typed receipts not yet published, sent through the contract; on arrival each is marked with the
    arrival it went in."""
    rows = typed(version)
    todo = [r for r in rows if not r["published"]]
    st = state(version, who)
    checks, placed, arrival = arrive(version, todo, "the purchasing plan", who, made_against=st["pin"]["consumption"])
    if placed:
        sent = {(t["input_code"], t["plant_code"], t["period"]) for t in arrival["taken"]}
        for r in rows:
            if (r["input_code"], r["plant_code"], r["period"]) in sent:
                r["published"] = arrival["arrival"]
        _save(version, rows)
    return checks, placed, arrival


def read_sheet(text: str) -> list[dict]:
    """A spreadsheet of receipts saved as CSV, in the contract's shape (SHEET_COLUMNS)."""
    return [{k: (r.get(k) or "").strip() for k in SHEET_COLUMNS} for r in csv.DictReader(io.StringIO(text))]


def arrivals(version: str, n: int = 5) -> list[dict]:
    d = _arrivals()
    out = [json.loads(p.read_text()) for p in sorted(d.glob("*.json"))] if d.is_dir() else []
    return [a for a in out if a["version"] == version][-n:][::-1]
