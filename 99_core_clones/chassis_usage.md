# chassis — usage

The method-neutral part of a build's face, as a wheel. A build imports it; it supplies nothing the build's method would
recognise — no checks, no vocabulary, no models.

## Install

The wheel sits beside this file and is declared in `pyproject.toml`:

```toml
dependencies = ["chassis", ...]

[tool.uv.sources]
chassis = { path = "99_core_clones/chassis-0.5.1-py3-none-any.whl" }
```

`uv sync` installs it. A new wheel version: replace the file, bump the path, `uv lock && uv sync`.

## Inputs

Configure once, before any page is served or any landing is written:

```python
import chassis
chassis.configure(root=ROOT, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing",
                  run_commands=[["uv", "run", "python", "-m", "ingest.pipeline"],
                                ["uv", "run", "sqlmesh", "plan", "prod", "--restate-model", "*", "--auto-apply", "--no-prompts"]])
```

## What it gives

| Module | Use |
|---|---|
| `chassis.ui.Shell` | `Shell(brand, strapline, home, processes, who="select"|"label")` — the product as a register of `Process` → `Area` → `Section(key, label, endpoint, args, verbs)`; `.page(body, title=, active=, who=, held=, flash=, principals=)` shows the person only the sections whose verbs they hold; `.reach(held)` is the same filter for a home page; `/static/face.css` is served by the app factory |
| `chassis.session.Session` | who the face acts as, what it last said (`say` / `flash`), the last receipt, the run log; `default_holder(verb, actions_held)` picks the default principal |
| `chassis.warehouse` | `q(sql, *params)`, `one`, `exists(relation)`; `Busy` when the file is held by a run or not yet built |
| `chassis.roles.WarehouseRoles(q)` | `principals()`, `may(who, action, scope=None, as_at=None)`, `actions_held(who)`, `layers_enterable(who)` over `dims.effective_entitlements` |
| `chassis.roles.FileRoles(reference_dir, scope_ancestors)` | the same questions answered from the register files, for a face that must judge before any run |
| `chassis.landing.LogLanding(group, table, columns)` | `place(rows, who)` — one act, one CSV under `<landing>/<group>/<table>/`, never edited; `files()`, `pending()`, `rows()` |
| `chassis.landing.SetLanding(folder)` | `place(src)`, `withdraw(name)`, `present(name)` — the file set is the state |
| `chassis.receipts` | `judge(checks)`, `write(kind, who, subject, checks, placed)`, `act(kind, who, subject, ok, says)`, `recent(n)` — a check is `{"check", "ok", "says"[, "flag"]}`; a flagged check is told, not refused |
| `chassis.run.Runner` | `Runner().run()` — the configured commands in order, stop at the first failure, the log returned; `health(q, surface)` reads a run-health surface if the build has one |
| `chassis.app` | `create_app(shell, session, roles, blueprints)` — registers the acting-as endpoint when the shell selects; `serve(app, port, watch)` with `--no-reload` honoured |
| `chassis.ingest` | `rows`, `columns`, `log_resource(master, placed, name, numeric, integer)`, `set_resource([(path, face)], ...)` — dlt resources over the two landing kinds (`chassis[ingest]` extra) |

## Run

```bash
uv run python -m face                 # Bash
```
```powershell
uv run python -m face                 # PowerShell
```

## After a change to the chassis

Rebuild the wheel in the core repository through its gate, copy it here, bump the path in `pyproject.toml`, lock and
sync. Both builds consume the same wheel; a change one build needs is made in the chassis and reaches the other.
