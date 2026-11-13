# chassis — usage

The method-neutral part of a build's face, as a wheel. A build imports it; it supplies nothing the build's method would
recognise — no checks, no vocabulary, no models.

## Install

The wheel sits beside this file and is declared in `pyproject.toml`:

```toml
dependencies = ["chassis", ...]

[tool.uv.sources]
chassis = { path = "99_core_clones/chassis-0.9.1-py3-none-any.whl" }
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
| `chassis.ui.Shell` | `Shell(brand, strapline, home, processes, who="select"|"label")` — the product as a register of `Process` → `Area` → `Section(key, label, endpoint, args, verbs)`; `.page(body, title=, active=, who=, held=, flash=, principals=)` shows the person only the sections whose verbs they hold; `.reach(held)` is the same filter for a home page; `/static/face.css` is served by the app factory; the top bar carries the person's colour scheme (`Shell(schemes=[(key, label), …])`, default paper · night · slate · contrast), kept per person in a cookie and applied as `<html data-scheme>` over the stylesheet's tokens — a build's own markup that reads only `var(--…)` follows; a client's colours as `Shell(skin={"primary": "#hex", "secondary": …, "bar": …})` land on the stylesheet's object tokens only (`--brand`, `--bar`/`--on-bar`, `--side`, `--accent`/`--on-accent`, `--edge`, `--series-1…4`), derived by rule per scheme, a colour short of contrast falling back to its default — markup draws a chart series or a selected control through those tokens, a state or verdict through the tonal ones |
| `chassis.ui.Tab` | an object with several views is one entry with tabs, never a third menu level: `Section(key, label, endpoint, tabs=[Tab(key, label, endpoint, args, verbs), …])`; a tab shows on its verbs, the entry when any tab does and opens on the first the person sees (`section.href(held)`); a page passes its tab's key as `active` and the shell draws the tabs under its title. `Shell(links=[(label, endpoint)])` offers pages to everyone in the top bar after the processes |
| `chassis.door` | one resolution model for every door: `ACT_COLUMNS` (the one act register — a decision or a proposal per row, latest per door × kind × item × scope in force), `QUEUE_COLUMNS` (what a door's queue surface carries per undecided item; `reaches` names the nodes whose holders may decide), `RESOLUTION_COLUMNS` (the reference table: per door × kind, each resolution's label, what it names of ours, whether it takes the proposal or needs a reason, its verb); `kinds_from(rows)`; `Declaration(check, holds, ok, no)` and `declared(decls, header, rows)` for a take-in's checks; `Door(key, label, acts, kinds, master)` with `.offer(items, who, may)`, `.decide(who=, kind=, item_code=, scope_code=, resolution=, target=, reason=, waiting=, ours=, may=)` (checks, one act, the receipt), `.propose(rows, who)`, `.latest()`, `.known()`; page components `door.QUEUE` and `door.DECIDED` read `door_items`, `door_kinds`, `door_ours`, `door_action`, `door_next`, `door_decided`. The comparison that finds the disagreements stays the build's query |
| `chassis.working` | typing into a view without a run: `Copies()` keeps a build's working copy per person and per view in the face's memory — `.open(who, key, make)` (made on the first edit), `.get`, `.drop` (discard, or after a save), `.held(who)`, `.lock(who)`; lost on restart by design. The edit endpoint renders the view's parts as `{element id: html}` before and after one edit and returns `reply(before, after, always=())` — only the parts that changed; `is_live()` tells a post from the script from a plain form post. On the page, `script()` loads `static/live.js`: a container `<div data-live-post="/edit" data-live-context='{json}'>` around inputs `<input name=... data-live='{json}'>` — Enter, Tab or leaving a changed input posts context + data-live + `{"value"}` as JSON (header `X-Live: 1`), one post at a time, and swaps each returned element by id; the cursor stays in its cell. Keep the container itself outside the swapped parts |
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
