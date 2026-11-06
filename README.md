# Caldera

A planning demo for a prepared-foods manufacturer: drivers in, plan out, every number
traceable to the inputs that made it. Open-native stack, runs on a laptop.

This repository is generated from a private source and is read-only here.

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
