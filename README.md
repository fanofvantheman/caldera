# Caldera

A planning demo for a prepared-foods manufacturer: drivers in, plan out, every number
traceable to the inputs that made it. Open-native stack, runs on a laptop.

This repository is generated from a private source and is read-only here.

## Run it

```bash
uv sync
uv run python -m generate            # the synthetic client, from its recipe, under data/generated/
uv run python -m ingest.pipeline     # load the landing into bronze (DuckDB file at data/caldera.duckdb)
uv run sqlmesh plan prod --auto-apply --no-prompts   # every model, every check
uv run python -m face                # the planning face → http://localhost:8010 (--no-reload for the room)
```

GitHub Actions runs the same three steps on every push and prints what the room would read.

Rerunning locally after the inputs change: a model whose logic is unchanged is not re-evaluated inside its interval,
so either restate (`uv run sqlmesh plan prod --restate-model "*" --auto-apply --no-prompts`) or start clean
(`rm -f data/*.duckdb && rm -rf data/.dlt`, then load and plan) — the runner always starts clean.

## Layout

- `pyproject.toml` + `uv.lock` — the environment (uv-managed, lockfile-pinned, nothing global).
- `generate/` — the synthetic client. `structures.py` is what Caldera makes, sells to, operates and is organised as;
  `calendar.py` the 4-4-5 trading calendar (fiscal year July–June, every week in exactly one period);
  `history.py` three years of shipments by material × ship-to × week and the price lists; `registers.py` the
  versions, roles, capacity register and planning assumptions; `plan.py` what the people typed — layer entries on
  each version, the promotions calendar, the terms register. Deterministic from a seed; output is regenerated
  every run and never committed.
- `ingest/pipeline.py` — dlt: one resource per file into `bronze`, replaced whole on every load. A plan table is fed by
  the generated file and then every file the face has placed under `data/landing/plan/<table>/`, in file order —
  file order is time order; the face is the landing's only writer.
- `face/` — the planning face: the demand plan by material and period with the layers beneath, the entries on a
  version (a withdrawal is a later row that names the entry; the entry stays, struck through), a new entry placed as a
  file after its checks (version open, who holds the layer's enter verb, both scopes resolve, window in horizon, the
  reason offered on the layer — flagged, not refused), the revenue bridge and the gap to the reference version, the
  promotions and terms registers, the versions, and the run — the same two commands the schedule runs, started by
  whoever holds `run.plan`, the log kept. Every act writes a receipt under `data/receipts/`. What a page shows is what
  the last run said: an entry placed is in the plan after the next run, and a withdrawal of an entry the warehouse has
  not yet seen is refused, honestly, until it has.
  The face's pages and checks are here; its chrome, session, landing writer, receipts, roles, run and warehouse access
  are the **chassis** (`99_core_clones/chassis-*.whl`, a dependency in `pyproject.toml`) — the part of a face that does
  not know which method it carries, shared with the other builds. `99_core_clones/chassis_usage.md` says how it is used.
- `config.yaml` + `models/` — the SQLMesh project:
  - `dims/` the calendar (weeks, periods with relative position), versions, the four structures as hierarchy
    bridges (material, customer, location, organisation), the bill of materials, routes, lanes, the capacity
    register, the assumptions register, roles and the entitlements derived from them
  - `history/` shipments at week and period grain, price lists
  - `plan/` the demand plan and its money: the category trend and the history shape fitted from cleansed
    shipments; the layer entries as filed and resolved to the grid; layer 1 computed for the open version and
    entered for the frozen one; the promotions calendar's uplift and dip lines, day-weighted into the weeks a
    dated window touches; the stack (every layer line, keyed by version and source); the unconstrained demand plan
    at storage grain and at the review's grain with each layer beside the total; the list price and terms in force
    by week; every line valued through the gross-to-net (wide, and long with each deduction's attributes); the
    revenue bridge by layer; the gap to the version's reference
- `audits/` — the checks every model runs: every member reaches its root, every week in one period, exactly one
  open period, vocabularies, references resolve, one person does not both enter demand and enter the supply
  constraint; an entry is on a known version, resolves to leaves, and was entered by the layer's owner; every
  case has a list price in force; gross less every deduction is net on every line; the long form ties to the wide.

## Stack

The same open-native stack as the consolidation demo, extended in one place.

- **DuckDB** — the warehouse, a single file. Runs on a laptop; the same file runs on a GitHub runner.
- **dlt** — loads the landing: every plan entry, driver register and actuals file, read whole on every run.
- **SQLMesh** — the calculation layer. SQL models by default (layer sums, spread rules, gross-to-net,
  financialisation at standard, the 4-4-5 calendar); Python models only where the arithmetic is
  iterative and SQL would be opaque (network flow, safety stock, capacity load).
- **GitHub Actions** — the trigger: load, then calculate, on a schedule or on demand.
- **SOPS + age** — secrets as encrypted files in the repository.
- **Rill** — the reading layer: the commercial P&L, the bridge to standard, scenario against base,
  plan against actuals. Metrics as code, reading the DuckDB file.
- **The face** — a small web app, the landing's only writer: upload a sheet to a door, or enter an
  override or a scenario delta directly. Every number traces back to a file in the landing.
- **The assistant** — answers from the warehouse, creates a scenario, enters a line, reruns, explains the movement.

**Inputs are files, versions are data.** Each plan version, layer and scenario is a set of rows in
the landing, written only by the face. A version is a key on every fact, computed once; nothing
relies on database snapshots or environments to hold a scenario.

**One build, more than one engine.** After the first model runs end to end, a second SQLMesh gateway
runs the same models against a second engine (hosted DuckDB, Postgres, or a client's platform) with
a configuration change and the same numbers out. Range is shown by moving one build, not by
building twice.

## Where the build is

Foundation in place: structures, calendar, versions, registers, roles, three years of history. The demand plan as
a stack of owned layers on the version — baseline, adjustment, distribution, promotions, innovation, exit — summed to
unconstrained demand and valued through the gross-to-net at the list and terms in force, with the bridge by layer
and the gap to the business plan. Next: the supply side — the constrained sales plan as its own stack of deltas,
the capacity analysis over the registers — then the standard and the variances.
