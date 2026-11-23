"""The purchasing plans (DEC-20261121-01, on DEC-20261120-03 and -04): a material planner keeps plans of their own, each
named, each reading copies — never connections — and sends a snapshot of one into an IBP plan, where it stands as the one
read-only copy of purchasing's receipts until the next is sent.

Two kinds of thing, and no status on either: a plan is a working thing, one owner, and changes; a copy is made by a
deliberate act — taken, sent — and never changes. Received, standing and changed are looked up when a page is drawn.

Where things are — folders under the build's data, the cheapest form (DEC-20261120-04 point 2):

  workspaces/purchasing/plans/<plan>/plan.json        the plan: name, owner, when and from what it was made, its actuals
                                                      close and last period, the plants it buys for, what it reads now
  workspaces/purchasing/plans/<plan>/receipts.csv     the receipts typed in it — a quantity and a price together
  workspaces/purchasing/plans/<plan>/copies/<copy>/   each copy it has taken, never changed
  workspaces/purchasing/plans/<plan>/sent.json        its own last snapshot: where it went, when, what it carried
  shared/standing/purchasing/<IBP plan>.json          the one copy standing in an IBP plan, overwritten when replaced;
                                                      a plan started from another begins with the other's copy carried
                                                      across (`carried` names where from), less what it does not plan
  landing/plan/reg_purchase_act/standing-purchasing-<IBP plan>-<moment>.csv
                                                      the same copy in the IBP plan's register of typed purchases; the
                                                      previous file is removed when it is replaced, and on an IBP plan
                                                      with one, plan.purchase_act takes that copy's receipts and nothing
                                                      else of the register

  shared/published/purchasing/<IBP plan>.json         purchasing's receipts as last published in an IBP plan — the copy the
                                                      stages after supply use (DEC-20261123-01 points 12–13): made when
                                                      supply's second sign-off is given, or carried across when the plan
                                                      was started; a send never moves it
  landing/plan/reg_purchase_act/published-purchasing-<IBP plan>-<moment>.csv
                                                      the same copy in the register, read by plan.purchase_published and
                                                      never by plan.purchase_act; the previous file removed

A send is refused while supply is signed off in the IBP plan it is sent to: the first sign-off locks the stage.

What a plan reads: a consumption copy per plant — the plant's material requirement in one IBP plan, with the prices in
force of the key materials and the contract indices there; and a copy of the structures — the key material master (its
stock on hand and contracted receipts are the record at the plan's close), the materials' campaign windows, the calendar.
The balance is `calc.purchases` over those copies and the plan's own receipts, plant by plant, so nothing is built twice."""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import pathlib
import re

import duckdb
from chassis import CONFIG, receipts
from chassis.landing import LogLanding
from chassis.warehouse import q

from calc import purchases as P

ACT_COLUMNS = ["act_id", "action", "withdraws", "version_id", "input_code", "plant_code", "period", "quantity", "price", "reason", "entered_by", "entered_at"]
ACTS = LogLanding("plan", "reg_purchase_act", ACT_COLUMNS)           # the IBP plan's register of typed purchases
RECEIPT_COLUMNS = ["input_code", "plant_code", "period", "quantity", "price", "reason", "entered_by", "entered_at"]
SHEET_COLUMNS = ["input_code", "plant_code", "period", "quantity", "price", "reason"]   # a receipt, as sent
SUBMITTER = "purchasing"                                             # one submitter, buying for all its plants

# what a consumption copy holds, taken from an IBP plan: each table's query, parameters (the IBP plan, the plant)
CONSUMPTION = {
    "plan.material_requirement": ("select version_id, input_code, plant_code, period, quantity from plan.material_requirement "
                                  "where version_id = ? and plant_code = ? order by input_code, period", True),
    "plan.input_price_in_force": ("select version_id, input_code, period, price from plan.input_price_in_force where version_id = ? "
                                  "and input_code in (select input_code from dims.ref_key_material) order by input_code, period", False),
    "plan.assumption_in_force": ("select version_id, assumption_code, period, value from plan.assumption_in_force where version_id = ? "
                                 "and assumption_code in (select contract_index from dims.ref_key_material where contract_index is not null) "
                                 "order by assumption_code, period", False),
}
# what the structures copy holds — master data, the same whichever IBP plan a plant's consumption comes from
STRUCTURES = {
    "dims.ref_key_material": "select * from dims.ref_key_material order by input_code, plant_code",
    "dims.dim_input_material": "select material_code, material_name, material_type, base_uom, campaign_window, is_perishable from dims.dim_input_material order by material_code",
    "dims.dim_period": "select period, fiscal_year, fiscal_period from dims.dim_period order by period",
}
COLUMNS = {"plan.material_requirement": ["version_id", "input_code", "plant_code", "period", "quantity"],
           "plan.input_price_in_force": ["version_id", "input_code", "period", "price"],
           "plan.assumption_in_force": ["version_id", "assumption_code", "period", "value"]}


def _data() -> pathlib.Path:
    return CONFIG.db.parent


def _plans_dir() -> pathlib.Path:
    return _data() / "workspaces" / "purchasing" / "plans"


def _standing_dir() -> pathlib.Path:
    return _data() / "shared" / "standing" / SUBMITTER


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _write_csv(path: pathlib.Path, rows: list[dict], columns: list[str] | None = None) -> None:
    cols = columns or (list(rows[0]) if rows else ["empty"])
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in cols})


def _read_csv(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _num(x) -> float | None:
    return float(x) if x not in (None, "") else None


# ── plans ────────────────────────────────────────────────────────────────────────────────────────────────────────────────

def plans(who: str | None) -> list[dict]:
    """The plans this person keeps, the newest first."""
    d = _plans_dir()
    out = [json.loads((x / "plan.json").read_text()) for x in d.iterdir() if (x / "plan.json").exists()] if d.is_dir() else []
    return sorted([p for p in out if p["owner"] == who], key=lambda p: p["made_at"], reverse=True)


def plan(pid: str | None) -> dict | None:
    p = _plans_dir() / (pid or "-") / "plan.json"
    return json.loads(p.read_text()) if pid and re.fullmatch(r"[A-Za-z0-9-]+", pid) and p.exists() else None


def _save_plan(p: dict) -> None:
    d = _plans_dir() / p["id"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "plan.json").write_text(json.dumps(p, indent=1))


def key_plants() -> list[str]:
    return [r["plant_code"] for r in q("select distinct plant_code from dims.ref_key_material order by plant_code")]


def sources(close: str | None = None) -> list[dict]:
    """The IBP plans a copy may be taken from unasked — every Plan but the actuals, at the close given (or any)."""
    from . import reads
    return [v for v in reads.versions() if v.get("version_kind") != "actual" and v.get("from_period") and v.get("plan_through")
            and (close is None or v["from_period"] == close)]


SEED = "ibp"                                                         # start_from: seeded from the IBP plan the consumption is taken from


def typed_since(version: str) -> list[dict]:
    """What was typed in the IBP plan since the copy standing there was placed (DEC-20261121-03 (a)): it applies over the
    copy. Read from the run, so a change typed since the last run shows after it."""
    s = standing(version)
    if not s:
        return []
    return [{**r, "reason": r.get("reason") or ""} for r in
            q("select act_id, input_code, plant_code, period, quantity, price, reason, entered_by, entered_at from plan.purchase_act "
              "where version_id = ? and act_id not like 'STD-%' and entered_at > ? order by 2, 3, 4", version, s["at"])]


def stands(version: str) -> list[dict]:
    """Purchasing's receipts as they stand in an IBP plan: the copy standing there with what was typed there since over
    it, or with none, what is typed on it."""
    s = standing(version)
    if s:
        cells = {_cell(r): r for r in s.get("receipts", [])}
        cells.update({_cell(r): r for r in typed_since(version)})
        return [cells[k] for k in sorted(cells)]
    return [{**r, "reason": r.get("reason") or ""} for r in
            q("select input_code, plant_code, period, quantity, price, reason from plan.purchase_act where version_id = ? order by 1, 2, 3", version)]


def plan_versions(versions: list[dict]) -> dict[str, dict]:
    """An IBP plan and a version are two keys (DEC-20261123-01 points 1–4), read here from the one code the build keeps for
    their intersection: the code without a what-if's letter is the plan; no letter is version 0, called Plan — the plan's
    number — and a letter is version 1, 2, … in order, labelled with what was said when it was made."""
    why = {r["version_id"]: r["reason"] for r in q("select version_id, reason from plan.version_act where act = 'name'")}
    out = {}
    for v in versions:
        m = re.fullmatch(r"(.+)-([A-Z])", v["version_id"])
        out[v["version_id"]] = {"plan": m.group(1) if m else v["version_id"], "n": ord(m.group(2)) - 64 if m else 0,
                                "label": (why.get(v["version_id"]) or "a copy") if m else "Plan"}
    return out


def make(who: str, name: str, source: str, plants: list[str], start_from: str | None) -> dict:
    """A new plan: its close and last period are the IBP plan its consumption is first taken from; a copy of that
    consumption for each plant and a copy of the structures are taken now; from another plan, its typed receipts and
    nothing else are copied; seeded (`SEED`), its typed receipts are purchasing's receipts standing in that IBP plan,
    whoever sent or typed them (DEC-20261121-03 point 4) — a copy, like every other."""
    from . import reads
    v = reads.version(source)
    if not v or v.get("version_kind") == "actual" or not v.get("from_period"):
        raise ValueError(f"no IBP plan {source} to take consumption from")
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    p = {"id": f"{stamp}-{re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:32] or 'plan'}", "name": name, "owner": who, "made_at": _now(),
         "made_from": None, "actuals_to": v["from_period"], "through": v["plan_through"], "plants": plants, "reads": {"consumption": {}, "structures": None}}
    _save_plan(p)
    if start_from == SEED:
        p["made_from"] = f"what stands in {reads.plan_codes().get(source, (source, source))[1]}"
        _save_receipts(p["id"], [{**r, "reason": r.get("reason") or "", "entered_by": who, "entered_at": _now()}
                                 for r in stands(source) if r["plant_code"] in plants and p["actuals_to"] < r["period"] <= p["through"]])
    elif start_from:
        src = plan(start_from)
        if src and src["owner"] == who:
            p["made_from"] = src["name"]
            rows = [r for r in typed(src["id"]) if r["plant_code"] in plants and p["actuals_to"] < r["period"] <= p["through"]]
            _save_receipts(p["id"], rows)
    take_structures(p, who)
    for pl in plants:
        take_consumption(p, pl, source, who)
    _save_plan(p)
    return p


def _new_copy(p: dict, what: str, who: str, **meta) -> tuple[dict, pathlib.Path]:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    c = {"copy": f"{stamp}-{what}", "input": what, "taken_at": _now(), "taken_by": who, **meta}
    d = _plans_dir() / p["id"] / "copies" / c["copy"]
    d.mkdir(parents=True, exist_ok=True)
    return c, d


def take_structures(p: dict, who: str) -> dict:
    c, d = _new_copy(p, "structures", who, how="master data")
    for t, sql in STRUCTURES.items():
        _write_csv(d / f"{t}.csv", q(sql))
    (d / "copy.json").write_text(json.dumps(c, indent=1))
    p["reads"]["structures"] = c["copy"]
    return c


def take_consumption(p: dict, plant: str, source: str, who: str) -> dict:
    """A copy of one plant's consumption from an IBP plan — refused at another actuals close (a later close is a new plan)."""
    from . import reads
    v = reads.version(source)
    if not v or v.get("version_kind") == "actual":
        raise ValueError(f"no IBP plan {source}")
    if v.get("from_period") != p["actuals_to"]:
        raise ValueError(f"{reads.plan_codes().get(source, (source, source))[1]} has actuals to {v.get('from_period')}; this plan has actuals to {p['actuals_to']} — a plan at another close is a new plan")
    if plant not in p["plants"]:
        raise ValueError(f"this plan does not buy for {plant}")
    c, d = _new_copy(p, "consumption", who, plant=plant, source=source, how="endorsed")
    for t, (sql, by_plant) in CONSUMPTION.items():
        _write_csv(d / f"{t}.csv", q(sql, source, plant) if by_plant else q(sql, source), COLUMNS[t])
    (d / "copy.json").write_text(json.dumps(c, indent=1))
    p["reads"]["consumption"][plant] = c["copy"]
    return c


def copy_meta(p: dict, cid: str | None) -> dict | None:
    f = _plans_dir() / p["id"] / "copies" / (cid or "-") / "copy.json"
    return json.loads(f.read_text()) if cid and f.exists() else None


def reads_of(p: dict) -> dict:
    """What the plan reads now: each plant's consumption copy (None: not received) and the structures copy."""
    return {"consumption": {pl: copy_meta(p, p["reads"]["consumption"].get(pl)) for pl in p["plants"]},
            "structures": copy_meta(p, p["reads"]["structures"])}


def change(pid: str, plant: str, source: str, who: str) -> dict:
    p = plan(pid)
    if not p or p["owner"] != who:
        raise ValueError("not a plan of yours")
    c = take_consumption(p, plant, source, who)
    _save_plan(p)
    return c


def refresh(pid: str, who: str) -> list[dict]:
    """A new copy from each IBP plan the plan reads, and of the structures. Nothing is previewed."""
    p = plan(pid)
    if not p or p["owner"] != who:
        raise ValueError("not a plan of yours")
    out = [take_structures(p, who)]
    for pl, c in reads_of(p)["consumption"].items():
        if c and c.get("source") and c.get("how") != "by request":     # a copy shared on request changes only by asking again
            out.append(take_consumption(p, pl, c["source"], who))
    _save_plan(p)
    return out


# ── receipts typed in a plan ─────────────────────────────────────────────────────────────────────────────────────────────

def typed(pid: str) -> list[dict]:
    return [{**r, "quantity": _num(r["quantity"]), "price": _num(r["price"])} for r in _read_csv(_plans_dir() / pid / "receipts.csv")]


def _save_receipts(pid: str, rows: list[dict]) -> None:
    (_plans_dir() / pid).mkdir(parents=True, exist_ok=True)
    _write_csv(_plans_dir() / pid / "receipts.csv", sorted(rows, key=lambda r: (r["input_code"], r["plant_code"], r["period"])), RECEIPT_COLUMNS)


def merged(pid: str, cells: dict) -> dict:
    """Cells as they would stand once typed: {(input, plant, period): {"quantity", "price"}} — what is typed over what the
    cell already held in the plan."""
    have = {(r["input_code"], r["plant_code"], r["period"]): r for r in typed(pid)}
    return {k: {"quantity": d.get("quantity") if d.get("quantity") is not None else (have.get(k) or {}).get("quantity"),
                "price": d.get("price") if d.get("price") is not None else (have.get(k) or {}).get("price")} for k, d in cells.items()}


def type_cells(pid: str, cells: dict, reason, who: str) -> None:
    """Cells typed in the plan; each must come out with a quantity and a price (`merged`) — the caller refuses otherwise.
    `reason` is the notes written in cells, {cell: note} (or one note for all of them); a cell given none keeps the one it has."""
    notes = reason if isinstance(reason, dict) else {k: reason for k in cells if reason}
    rows = {(r["input_code"], r["plant_code"], r["period"]): r for r in typed(pid)}
    for (i, pl, per), d in merged(pid, cells).items():
        if d["quantity"] is None or d["price"] is None:
            raise ValueError(f"{i} at {pl} in {per}: a receipt is a quantity and a price together")
        rows[(i, pl, per)] = {"input_code": i, "plant_code": pl, "period": per, "quantity": d["quantity"], "price": d["price"],
                              "reason": notes[(i, pl, per)] if (i, pl, per) in notes else (rows.get((i, pl, per)) or {}).get("reason") or "",
                              "entered_by": who, "entered_at": _now()}
    _save_receipts(pid, list(rows.values()))


def drop(pid: str, cell: tuple[str, str, str]) -> None:
    _save_receipts(pid, [r for r in typed(pid) if (r["input_code"], r["plant_code"], r["period"]) != cell])


def periods(p: dict) -> dict:
    """The plan's periods as a grid reads them (the shape of `reads.version_periods`): every one after its close, through
    its last, from its copy of the calendar."""
    st = p["reads"]["structures"]
    cal = _read_csv(_plans_dir() / p["id"] / "copies" / (st or "-") / "dims.dim_period.csv")
    ps = [{"period": r["period"], "fiscal_year": int(r["fiscal_year"]), "fiscal_period": int(r["fiscal_period"]), "actual": False}
          for r in cal if p["actuals_to"] < r["period"] <= p["through"]]
    return {"fy": ps[0]["fiscal_year"] if ps else None, "from": p["actuals_to"], "through": p["through"], "periods": ps, "actual": [],
            "plan": [x["period"] for x in ps], "horizon": len(ps), "quarters": 0, "quarter_cols": [], "quarter_of": {}}


def structures(p: dict, table: str) -> list[dict]:
    return _read_csv(_plans_dir() / p["id"] / "copies" / (p["reads"]["structures"] or "-") / f"{table}.csv")


def balance(p: dict) -> list[dict]:
    """The plan's material balance, plant by plant: `calc.purchases` over the plant's consumption copy, the structures copy
    and the plan's own receipts. A plant with no consumption copy has no rows (not received)."""
    base = _plans_dir() / p["id"] / "copies"
    st = base / (p["reads"]["structures"] or "-")
    acts = typed(p["id"])
    out: list[dict] = []
    con = duckdb.connect()
    try:
        def fetch(sql: str) -> list[dict]:
            cur = con.execute(sql)
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

        def lit(s: str) -> str:
            return "'" + str(s).replace("'", "''") + "'"

        def csvf(d: pathlib.Path, t: str) -> str:
            return f"read_csv_auto({lit((d / (t + '.csv')).as_posix())}, header=true)"

        for pl, cid in p["reads"]["consumption"].items():
            meta = copy_meta(p, cid)
            if not meta or pl not in p["plants"]:
                continue
            src, cd = meta["source"], base / cid

            def T(t: str, pl=pl, src=src, cd=cd) -> str:
                if t == "dims.ctl_version":
                    return f"(select {lit(src)} version_id, 'purchasing' version_kind, {lit(p['actuals_to'])} from_period, {lit(p['through'])} plan_through)"
                if t == "dims.ref_key_material":
                    return f"(select * from {csvf(st, t)} where plant_code = {lit(pl)})"
                if t in STRUCTURES:
                    return csvf(st, t)
                return csvf(cd, t)
            ty = [{**a, "version_id": src, "act_id": f"plan:{a['input_code']}:{a['plant_code']}:{a['period']}"} for a in acts if a["plant_code"] == pl]
            out += [r for r in P.compute_all(fetch, T, src, acts=ty) if r["plant_code"] == pl]
    finally:
        con.close()
    return out


# ── what stands in each IBP plan ─────────────────────────────────────────────────────────────────────────────────────────

def standing(version: str) -> dict | None:
    f = _standing_dir() / f"{version}.json"
    return json.loads(f.read_text()) if f.exists() else None


def standing_all() -> dict[str, dict]:
    d = _standing_dir()
    return {f.stem: json.loads(f.read_text()) for f in sorted(d.glob("*.json"))} if d.is_dir() else {}


def sent(pid: str) -> dict | None:
    f = _plans_dir() / pid / "sent.json"
    return json.loads(f.read_text()) if f.exists() else None


def _cell(r: dict) -> tuple:
    return (r["input_code"], r["plant_code"], r["period"])


def changed(pid: str) -> list[dict]:
    """The plan's receipts new or different since its last snapshot (every one, if it was never sent)."""
    last = {_cell(r): (r["quantity"], r["price"]) for r in (sent(pid) or {}).get("receipts", [])}
    return [r for r in typed(pid) if last.get(_cell(r)) != (r["quantity"], r["price"])]


def send(version: str, rows: list[dict], source: str, who: str, p: dict | None = None, note: str = "") -> tuple[list[dict], bool, dict]:
    """A snapshot into an IBP plan: checked, and if it holds, it replaces whatever stood there for purchasing — a receipt
    standing there and absent from it is gone, and nothing of the copy it replaces is kept. `source` is a plan's name or
    "a spreadsheet". Returns the checks, whether it was placed, and the copy now standing (or what was refused)."""
    from . import reads
    v = reads.version(version) or {}
    plan_periods = set(reads.version_periods(version)["plan"]) if v else set()
    keys = {(k["input_code"], k["plant_code"]) for k in q("select input_code, plant_code from dims.ref_key_material")}
    taken, dropped, refused = [], [], []
    for r in rows:
        cell = (str(r.get("input_code") or "").strip(), str(r.get("plant_code") or "").strip(), str(r.get("period") or "").strip())
        where = f"{cell[0] or '—'} at {cell[1] or '—'} in {cell[2] or '—'}"
        try:
            qty, pr = _num(r.get("quantity")), _num(r.get("price"))
        except (TypeError, ValueError):
            refused.append(f"{where}: not a number"); continue
        if cell[:2] not in keys:
            refused.append(f"{where}: not a key material at that plant"); continue
        if qty is None or pr is None:
            refused.append(f"{where}: a quantity and a price together"); continue
        if qty < 0 or pr <= 0:
            refused.append(f"{where}: a quantity not below zero and a price above it"); continue
        if cell[2] not in plan_periods:
            dropped.append(where); continue
        taken.append({"input_code": cell[0], "plant_code": cell[1], "period": cell[2], "quantity": qty, "price": pr, "reason": str(r.get("reason") or "").strip()})
    was = standing(version)
    gone = sorted({x["plant_code"] for x in (was or {}).get("receipts", [])} - {t["plant_code"] for t in taken})
    name = reads.plan_codes().get(version, (version, version))[1]
    lock = stage_lock(version)
    since = typed_since(version) if v else []
    checks = [
        {"check": "the IBP plan is open", "ok": v.get("status") == "open" and v.get("version_kind") != "actual",
         "says": f"{name} is open" if v.get("status") == "open" else f"{name} is {v.get('status', 'unknown')} — what stands in it is no longer replaced"},
        {"check": "supply is open there", "ok": not lock, "says": lock or f"{STAGE_NAME} is open in {name}"},
        {"check": "a quantity and a price together", "ok": not refused, "says": "; ".join(refused) if refused else f"{len(taken)} receipt{'s' if len(taken) != 1 else ''} from {source}"},
        {"check": "periods the IBP plan plans", "ok": True, "flag": bool(dropped), "says": ("left out: " + "; ".join(dropped)) if dropped else "every period is planned there"},
        {"check": "what it replaces", "ok": True, "flag": bool(gone),
         "says": ((f"replaces {was['source']}, carried across from {reads.plan_codes().get(was['carried']['from'], (was['carried']['from'],) * 2)[1]}"
                   if was.get("carried") else f"replaces {was['source']} of {was['at'].replace('T', ' ')[:16]}") if was else "nothing stood there")
                 + (f"; nothing now stands for {', '.join(gone)}" if gone else "")},
        {"check": "changes typed in the IBP plan", "ok": True, "flag": bool(since),
         "says": (f"replaces {len(since)} change{'s' if len(since) != 1 else ''} typed in {name} since the last copy: "
                  + "; ".join(f"{r['input_code']} at {r['plant_code']} in {r['period']} by {r['entered_by']}" for r in since[:6])
                  + (f" and {len(since) - 6} more" if len(since) > 6 else "")) if since else "nothing typed there since the last copy"},
    ]
    placed = receipts.judge(checks)
    now = dt.datetime.now()
    copy = {"version": version, "submitter": SUBMITTER, "plan": p["id"] if p else None, "source": source, "note": note, "owner": p["owner"] if p else None,
            "by": who, "at": now.isoformat(timespec="seconds"), "receipts": taken, "dropped": dropped,
            "made_against": ({"actuals_to": p["actuals_to"], "copies": [c for c in reads_of(p)["consumption"].values() if c]} if p else None),
            "replaced": {"source": was["source"], "at": was["at"], "carried_from": (was.get("carried") or {}).get("from")} if was else None}
    if placed:
        if not published(version):          # the stages after supply keep what stood until supply is published (point 13)
            publish(version, who, "as it stood before the first send")
        _place_standing(version, copy, who, now.strftime("%Y%m%d-%H%M%S-%f"))
        if p:
            (_plans_dir() / p["id"] / "sent.json").write_text(json.dumps({"version": version, "at": copy["at"], "receipts": taken}, indent=1))
    return checks, placed, copy


def _place_standing(version: str, copy: dict, who: str, stamp: str) -> None:
    """The copy written as the one standing in an IBP plan: its file of the register of typed purchases (the previous one
    removed, a marker row so an empty copy still stands) and its record under shared/standing."""
    for old in ACTS.folder.glob(f"standing-{SUBMITTER}-{version}-*.csv") if ACTS.folder.is_dir() else []:
        old.unlink()
    ACTS.folder.mkdir(parents=True, exist_ok=True)
    marker = {"act_id": f"STD-{stamp}-000", "action": "stand", "version_id": version, "reason": copy["source"], "entered_by": who, "entered_at": copy["at"]}
    _write_csv(ACTS.folder / f"standing-{SUBMITTER}-{version}-{stamp}.csv",
               [marker] + [{"act_id": f"STD-{stamp}-{i:03d}", "action": "set", "version_id": version, **t, "entered_by": who, "entered_at": copy["at"]}
                           for i, t in enumerate(copy["receipts"], start=1)], ACT_COLUMNS)
    _standing_dir().mkdir(parents=True, exist_ok=True)
    (_standing_dir() / f"{version}.json").write_text(json.dumps(copy, indent=1))


# ── supply's sign-offs: what a lock refuses, what publication moves ──────────────────────────────────────────────────────

STAGE, STAGE_NAME = "materials", "Supply"            # the stage purchasing feeds, as the list of plans declares it (stage_code)
KIND = "purchasing"                                  # this module's plan kind in the list of plans (dims.ref_plan_kind)
FIELD = {"quantity": "quantity", "price": "price", "note": "reason"}     # a field the list names → the column a receipt holds it in


def kind() -> dict:
    """This plan kind's row in the list of plans (DEC-20261124-05): its name, the stage it feeds, the right that owns it,
    by copy or by request — with the build's own values where the list is not yet built."""
    r = q("select * from dims.ref_plan_kind where plan_kind = ?", KIND)
    return r[0] if r else {"plan_kind": KIND, "plan_kind_name": "Purchasing plan", "stage": STAGE, "owner_verb": "register.supply_plan.maintain", "taken_by": "copy", "submitter": SUBMITTER}


def figures_of(k: str = KIND) -> list[dict]:
    """The key figures the kind owns and reads, in the list's order."""
    return q("select * from dims.ref_plan_figure where plan_kind = ? order by ord", k)


def stage_code() -> str:
    return kind().get("stage") or STAGE


def sheet_columns() -> list[str]:
    """What a send carries and a seed takes back: the cell, and the fields of the figure the kind owns."""
    owned = next((f for f in figures_of() if f["relation"] == "owns"), None)
    fields = [FIELD.get(x.strip(), x.strip()) for x in (owned or {}).get("fields", "").split(",") if x.strip()] if owned else []
    return ["input_code", "plant_code", "period"] + (fields or SHEET_COLUMNS[3:])


def stage(version: str) -> dict:
    """The state of the stage purchasing feeds, on an IBP plan: open, handed over (signed off once — locked) or published."""
    return (q("select * from plan.stage_state where version_id = ? and stage = ?", version, stage_code()) or [{}])[0]


def stage_lock(version: str) -> str | None:
    """Why nothing more is taken from purchasing on this IBP plan, or None: its stage is signed off."""
    st = stage(version)
    if st.get("state") in ("handed over", "published"):
        by = f" by {st['last_by']}, {str(st.get('last_at') or '')[:16].replace('T', ' ')}" if st.get("last_by") else ""
        return f"{STAGE_NAME} is {'published' if st['state'] == 'published' else 'signed off'} there{by} — it takes no more until it is reopened"
    return None


def _published_dir() -> pathlib.Path:
    return _data() / "shared" / "published" / SUBMITTER


def published(version: str) -> dict | None:
    f = _published_dir() / f"{version}.json"
    return json.loads(f.read_text()) if f.exists() else None


def published_all() -> dict[str, dict]:
    d = _published_dir()
    return {f.stem: json.loads(f.read_text()) for f in sorted(d.glob("*.json"))} if d.is_dir() else {}


def publish(version: str, who: str, says: str = "", rows: list[dict] | None = None, origin: dict | None = None) -> dict:
    """Purchasing's receipts as they stand in an IBP plan (or the rows given) made the copy the stages after supply use —
    the previous one replaced, none kept. The copy says what it was a copy of."""
    s = standing(version)
    taken = [{k: r.get(k) for k in sheet_columns()} for r in (stands(version) if rows is None else rows)]
    now = dt.datetime.now(); stamp = now.strftime("%Y%m%d-%H%M%S-%f"); at = now.isoformat(timespec="seconds")
    copy = {"version": version, "submitter": SUBMITTER, "by": who, "at": at, "says": says, "receipts": taken,
            "of": origin or ({"source": s["source"], "at": s["at"], "by": s["by"], "carried_from": (s.get("carried") or {}).get("from")} if s else None)}
    for old in ACTS.folder.glob(f"published-{SUBMITTER}-{version}-*.csv") if ACTS.folder.is_dir() else []:
        old.unlink()
    ACTS.folder.mkdir(parents=True, exist_ok=True)
    marker = {"act_id": f"PUB-{stamp}-000", "action": "publish", "version_id": version, "reason": says, "entered_by": who, "entered_at": at}
    _write_csv(ACTS.folder / f"published-{SUBMITTER}-{version}-{stamp}.csv",
               [marker] + [{"act_id": f"PUB-{stamp}-{i:03d}", "action": "set", "version_id": version, **t, "entered_by": who, "entered_at": at}
                           for i, t in enumerate(taken, start=1)], ACT_COLUMNS)
    _published_dir().mkdir(parents=True, exist_ok=True)
    (_published_dir() / f"{version}.json").write_text(json.dumps(copy, indent=1))
    return copy


def unpublished(version: str) -> int:
    """How many of purchasing's receipts standing in an IBP plan are new or different from what was last published there
    (every one, with nothing published) — plus those published and no longer standing."""
    pub = {_cell(r): (_num(r["quantity"]), _num(r["price"])) for r in (published(version) or {}).get("receipts", [])}
    now = {_cell(r): (_num(r["quantity"]), _num(r["price"])) for r in stands(version)}
    return sum(1 for k, x in now.items() if pub.get(k) != x) + sum(1 for k in pub if k not in now)


def carried(base: str, actuals_to: str, plan_periods: list[str]) -> dict | None:
    """What starting a plan from `base` carries of purchasing (DEC-20261121-02 (a)): the copy standing there, as it stands,
    less each receipt for a period the new plan does not plan — left behind and named: at or before its close, now the
    record; after its last period, past where it runs. None when nothing stands in the base."""
    was = standing(base)
    if not was:
        return None
    ps = set(plan_periods)
    held = [{k: r.get(k) for k in SHEET_COLUMNS} for r in stands(base)]     # the copy and what was typed there since (DEC-20261123-01 point 5)
    keep = [r for r in held if r["period"] in ps]
    left = [{**r, "why": "now the record" if r["period"] <= actuals_to else "past where this plan runs"}
            for r in held if r["period"] not in ps]
    return {"from": base, "was": was, "receipts": keep, "left_behind": left}


def carry(base: str, new: str, actuals_to: str, plan_periods: list[str], who: str) -> dict | None:
    """The copy standing for purchasing in `base` carried into the new plan `new` as its own standing copy — read-only like
    any other, replaced by the first send to the new plan. Where it came from is kept on it (`carried`); nothing else
    marks it."""
    c = carried(base, actuals_to, plan_periods)
    if not c:
        return None
    was = c["was"]
    origin = was.get("carried") or {}                   # carried again: it still came from whoever first sent it
    now = dt.datetime.now()
    copy = {"version": new, "submitter": SUBMITTER, "plan": None, "source": was["source"], "owner": was.get("owner"),
            "by": who, "at": now.isoformat(timespec="seconds"), "receipts": c["receipts"], "dropped": [],
            "made_against": was.get("made_against"), "replaced": None,
            "carried": {"from": base, "source": was["source"], "by": origin.get("by") or was.get("by"), "at": origin.get("at") or was.get("at"),
                        "plan": origin.get("plan") or was.get("plan"), "owner": was.get("owner"),
                        "left_behind": [{k: r[k] for k in ("input_code", "plant_code", "period", "quantity", "price", "why")} for r in c["left_behind"]]}}
    _place_standing(new, copy, who, now.strftime("%Y%m%d-%H%M%S-%f"))
    # a plan is whole from its first moment: what was carried is what the stages after supply use until supply is published
    publish(new, who, f"carried across from {base}", rows=c["receipts"],
            origin={"source": was["source"], "at": copy["at"], "by": who, "carried_from": base})
    return copy


def clear(pid: str, rows: set[tuple[str, str]]) -> int:
    """Every receipt typed in the plan for the rows given — a material at a plant — taken out in one act, so each of those
    cells is empty again (DEC-20261121-02 (d)). Returns how many."""
    have = typed(pid)
    keep = [r for r in have if (r["input_code"], r["plant_code"]) not in rows]
    _save_receipts(pid, keep)
    return len(have) - len(keep)


def read_sheet(text: str) -> list[dict]:
    """A spreadsheet of receipts saved as CSV, in the shape a receipt is sent (SHEET_COLUMNS)."""
    return [{k: (r.get(k) or "").strip() for k in sheet_columns()} for r in csv.DictReader(io.StringIO(text))]


# ── by request (DEC-20261121-01 point 5, DEC-20261123-01): anything later than or different from an IBP plan's version 0 ──
#
#   shared/requests/<request>/request.json     the ask — which plan, which plant's consumption, of whom, the message — and
#                                              the answer once given: one copy shared, or declined with a word
#   shared/requests/<request>/copy/            the copy shared, taken when the answer was given and never changed
#
# Asked of the holders of the right of the stage the figure is read from (the list of plans: consumption from production).
# The planner takes the shared copy into the plan, or leaves it; one answer is one copy — for a later one, ask again.

def _requests_dir() -> pathlib.Path:
    return _data() / "shared" / "requests"


def asked_of(figure: str = "consumption") -> dict:
    """The stage a figure is read from and the right whose holders are asked for it."""
    f = next((x for x in figures_of() if x["key_figure"] == figure), None)
    st = (f or {}).get("read_from") or "production"
    r = q("select stage, stage_name, verb from dims.ref_stage where stage = ?", st)
    return r[0] if r else {"stage": st, "stage_name": st.title(), "verb": "delta.supply.enter"}


def request(rid: str | None) -> dict | None:
    f = _requests_dir() / (rid or "-") / "request.json"
    return json.loads(f.read_text()) if rid and re.fullmatch(r"[A-Za-z0-9-]+", rid) and f.exists() else None


def requests_all() -> list[dict]:
    d = _requests_dir()
    out = [json.loads((x / "request.json").read_text()) for x in d.iterdir() if (x / "request.json").exists()] if d.is_dir() else []
    return sorted(out, key=lambda r: r["asked_at"], reverse=True)


def ask(p: dict, plant: str, who: str, message: str) -> dict:
    if plant not in p["plants"]:
        raise ValueError(f"this plan does not buy for {plant}")
    st = asked_of("consumption")
    rid = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    r = {"id": rid, "plan": p["id"], "plan_name": p["name"], "by": who, "figure": "consumption", "plant": plant, "actuals_to": p["actuals_to"],
         "stage": st["stage"], "stage_name": st["stage_name"], "verb": st["verb"], "message": message, "asked_at": _now(), "answer": None}
    (_requests_dir() / rid).mkdir(parents=True, exist_ok=True)
    (_requests_dir() / rid / "request.json").write_text(json.dumps(r, indent=1))
    return r


def answer(rid: str, who: str, source: str | None, says: str) -> dict:
    """The one asked answers: shares one copy of the plant's consumption from an IBP plan and version at the plan's close,
    taken now — or, with no source, declines. Answered once."""
    from . import reads
    r = request(rid)
    if not r:
        raise ValueError("no such request")
    if r.get("answer"):
        raise ValueError("answered already — a later copy is asked for again")
    if source:
        v = reads.version(source)
        if not v or v.get("version_kind") == "actual" or v.get("from_period") != r["actuals_to"]:
            raise ValueError(f"a copy at actuals to {r['actuals_to']} — the plan's close")
        d = _requests_dir() / rid / "copy"
        d.mkdir(parents=True, exist_ok=True)
        for t, (sql, by_plant) in CONSUMPTION.items():
            _write_csv(d / f"{t}.csv", q(sql, source, r["plant"]) if by_plant else q(sql, source), COLUMNS[t])
    r["answer"] = {"by": who, "at": _now(), "shared": source, "says": says}
    (_requests_dir() / rid / "request.json").write_text(json.dumps(r, indent=1))
    return r


def take_shared(pid: str, rid: str, who: str) -> dict:
    """The copy shared in answer to a request taken into the plan, as its plant's consumption — read as by request."""
    p, r = plan(pid), request(rid)
    if not p or p["owner"] != who or not r or r["plan"] != pid:
        raise ValueError("not a request of this plan of yours")
    if not (r.get("answer") or {}).get("shared"):
        raise ValueError("nothing was shared in answer")
    c, d = _new_copy(p, "consumption", who, plant=r["plant"], source=r["answer"]["shared"], how="by request", request=rid,
                     shared_by=r["answer"]["by"], shared_at=r["answer"]["at"])
    for t in CONSUMPTION:
        (d / f"{t}.csv").write_bytes((_requests_dir() / rid / "copy" / f"{t}.csv").read_bytes())
    (d / "copy.json").write_text(json.dumps(c, indent=1))
    p["reads"]["consumption"][r["plant"]] = c["copy"]
    _save_plan(p)
    return c
