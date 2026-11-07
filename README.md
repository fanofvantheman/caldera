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
```

GitHub Actions runs the same three steps on every push and prints what the room would read.

## Layout

- `pyproject.toml` + `uv.lock` — the environment (uv-managed, lockfile-pinned, nothing global).
- `generate/` — the synthetic client. `structures.py` is what Caldera makes, sells to, operates and is organised as;
  `calendar.py` the 4-4-5 trading calendar (fiscal year July–June, every week in exactly one period);
  `history.py` three years of shipments by material × ship-to × week and the price lists; `registers.py` the
  versions, roles, capacity register and planning assumptions. Deterministic from a seed; output is regenerated
  every run and never committed.
- `ingest/pipeline.py` — dlt: one resource per file into `bronze`, replaced whole on every load.
- `config.yaml` + `models/` — the SQLMesh project:
  - `dims/` the calendar (weeks, periods with relative position), versions, the four structures as hierarchy
    bridges (material, customer, location, organisation), the bill of materials, routes, lanes, the capacity
    register, the assumptions register, roles and the entitlements derived from them
  - `history/` shipments at week and period grain, price lists
- `audits/` — the checks every model runs: every member reaches its root, every week in one period, exactly one
  open period, vocabularies, references resolve, one person does not both enter demand and enter the supply
  constraint.

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

Foundation in place: structures, calendar, versions, registers, roles, three years of history, all loaded and
checked. Next: the demand plan as a stack of owned layers on the version, then its financialisation.
