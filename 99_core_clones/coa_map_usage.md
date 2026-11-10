# coa_map — usage

The first-pass mapping tool, as a wheel. Two entry points: `coa_map.map` maps a chart of accounts to group accounts;
`coa_map.codes` maps any subject's local codes onto a fixed target list. This build uses `coa_map.codes` for the
promotions system's codes — its planning accounts, product groups, tactics, fund types and status words — onto our
accounts, promo groups, mechanics, funding types and statuses.

## Install

The wheel sits beside this file and is declared in `pyproject.toml`:

```toml
dependencies = ["coa-map", ...]

[tool.uv.sources]
coa-map = { path = "99_core_clones/coa_map-0.4.0-py3-none-any.whl" }
```

`uv sync` installs it. A new wheel version: replace the file, bump the path, `uv lock && uv sync`.

The first pass calls the Claude API and needs `ANTHROPIC_API_KEY` in the environment. Without it nothing fails: the
pass says it did not run and the codes wait for a person.

```bash
export ANTHROPIC_API_KEY=...                         # Bash, this session
```
```powershell
$env:ANTHROPIC_API_KEY = "..."                       # PowerShell, this session
```

The model defaults to `claude-opus-5-5`; set `COA_MAP_MODEL` to use another.

## Inputs

For `coa_map.codes`:

| Input | Shape |
|---|---|
| source codes | CSV with columns `code`, `description` — the sender's codes and whatever it says about each |
| target list | CSV with columns `code`, `description` — the list every code must land on (ours) |
| subject | a word: `mechanic`, `funding_type`, `customer`, … |
| guidance | a sentence or a paragraph on how to choose |

As a library (what the face does): `map_codes(sources, targets, guidance, subject)` with lists of
`{"code", "description"}`; it raises `MappingUnavailable` with a plain sentence when the pass cannot run.

## Run

```bash
uv run python -m coa_map.codes --subject mechanic --source tactics.csv --targets mechanics.csv \
    --guidance "Map the sender's tactic to our mechanic." --output proposals.csv
```
```powershell
uv run python -m coa_map.codes --subject mechanic --source tactics.csv --targets mechanics.csv --guidance "Map the sender's tactic to our mechanic." --output proposals.csv
```

In the face it runs by itself: taking a file in on the Promotions page proposes a mapping for every code no mapping row
has named, and the Mapping review page can run it again for codes still not mapped.

## What it generates

One proposal per source code: a target from the list (the response is constrained to the list, so it cannot invent
one), a confidence — high, medium or low — and a one-line rationale. The CLI writes them as
`subject, code, description, target, confidence, rationale`; the face writes them to the mapping register
(`data/landing/plan/reg_promo_mapping/`) as *proposed*, once per code.

## After running

A proposal changes nothing until a person reviews it: on the Mapping review page, accept it, or alter it to another of
ours with a reason. Events that use the code are held until then, and enter the calendar on the next run after.
