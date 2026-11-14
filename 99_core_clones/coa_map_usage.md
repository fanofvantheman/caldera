# coa_map — usage

The first-pass tool, as a wheel. Three entry points: `coa_map.map` maps a chart of accounts to group accounts;
`coa_map.codes` maps any subject's local codes onto a fixed target list; `coa_map.clauses` reads a collective instrument
and proposes its entitlements as rows under a closed list of kinds, each with its clause quoted. This build uses
`coa_map.codes` for the promotions system's codes — its planning accounts, product groups, tactics, fund types and status
words — onto our accounts, promo groups, mechanics, funding types and statuses, and `coa_map.clauses` for an agreement
taken in on *Labour → Headcount → Entitlements*.

## Install

The wheel sits beside this file and is declared in `pyproject.toml`:

```toml
dependencies = ["coa-map", ...]

[tool.uv.sources]
coa-map = { path = "99_core_clones/coa_map-0.5.0-py3-none-any.whl" }
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

For `coa_map.clauses`:

| Input | Shape |
|---|---|
| document | the instrument's text (a `.txt` file for the CLI) |
| kinds | CSV with columns `code`, `description` — the closed list of kinds a row may be placed under |
| classifications | optional CSV with columns `code`, `description` — the classifications a row may name |
| instrument | `enterprise_agreement`, `award` or `statute` — collective instruments only; anything else is refused before anything is sent |
| guidance | optional: a sentence on how the document states its figures |

As a library: `propose_entitlements(text, kinds, classifications, instrument, guidance)` returns `{"rows", "unplaced",
"refused"}`; it raises `NotCollective` for anything but a collective instrument and `MappingUnavailable` when the pass
cannot run. Pass `client=` to use another client (a test passes a stub).

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

```bash
uv run python -m coa_map.clauses --document CFPA-2027.txt --kinds kinds.csv --classifications classes.csv \
    --instrument enterprise_agreement --output proposals.csv
```
```powershell
uv run python -m coa_map.clauses --document CFPA-2027.txt --kinds kinds.csv --classifications classes.csv --instrument enterprise_agreement --output proposals.csv
```

In the face: taking an agreement in on *Labour → Headcount → Entitlements* (the holder of the agreement register's right)
reads it into proposed rows.

## What it generates

One proposal per source code: a target from the list (the response is constrained to the list, so it cannot invent
one), a confidence — high, medium or low — and a one-line rationale. The CLI writes them as
`subject, code, description, target, confidence, rationale`; the face writes them to the mapping register
(`data/landing/plan/reg_promo_mapping/`) as *proposed*, once per code.

For `coa_map.clauses`: one row per clause that grants an entitlement — kind, classification, the pattern of work it
applies to, value, the date it runs from, the clause reference and the clause quoted, with a confidence and a rationale.
The tool's own code looks for every quotation in the document word for word (runs of whitespace read as one space,
nothing else forgiven): a row whose quotation is not found comes back `refused`, never as a proposal. A clause the model
placed under no kind comes back `unplaced`. The CLI writes them with a `placed` column (row, unplaced or refused); the face
writes them to `data/landing/plan/reg_entitlement_proposal/`, one file per document taken in.

## After running

For `coa_map.clauses`: nothing is read by the labour model until a person decides each row at the agreement door — accept
it, place it under another kind, or leave it out; an unplaced clause is closed as not material or approximated under a
kind with a note. Without an API key the take-in still happens and says the first pass did not run; the document waits
for a person.

For `coa_map.codes`: a proposal changes nothing until a person reviews it: on the Mapping review page, accept it, or alter it to another of
ours with a reason. Events that use the code are held until then, and enter the calendar on the next run after.
