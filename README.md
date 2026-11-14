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
uv run python -m face --skin         # the same face in a specimen client's colours
```

GitHub Actions runs the same three steps on every push and prints what the room would read.

With the warehouse built, `uv run python -m tests.measure_register` checks that the measure register and the finance
calculation agree (read only), and `uv run python -m tests.finance_working_copy` types into the finance grid through the
app, saves, and checks the plan after the run equals what the grid showed (it removes what it wrote);
`uv run python -m tests.schedule_working_copy` does the same for the opex schedule, and `uv run python -m tests.pay_verb`
checks that individual pay shows only to the holders of its verb (read only); `uv run python -m tests.version_acts` closes
and reopens the latest view through the app, as a holder and a non-holder of the verb (it removes what it wrote); `uv run python -m tests.version_horizon` checks
that every grid takes its actual and plan periods from the version, and that an actual period, a year and a period past
the horizon are refused (nothing saved). `uv run python -m tests.undo_before_save` types, undoes and redoes on Finance's grid and the opex
schedule and checks each step against the plan as saved (nothing saved). `uv run python -m tests.withdrawal_acts` withdraws a Finance figure, a schedule act
and a layer entry through the confirmation page and checks the plan after the run is what the page said (it removes
what it wrote).

Rerunning locally after the inputs change: a model whose logic is unchanged is not re-evaluated inside its interval,
so either restate (`uv run sqlmesh plan prod --restate-model "*" --auto-apply --no-prompts`) or start clean
(`rm -f data/*.duckdb && rm -rf data/.dlt`, then load and plan) — the runner always starts clean.

## Layout

- `pyproject.toml` + `uv.lock` — the environment (uv-managed, lockfile-pinned, nothing global).
- `generate/` — the synthetic client. Caldera is a fruit and vegetable processor of about $300M net sales a year: six
  categories (canned fruit, fruit snack cups, canned tomatoes, baked beans and spaghetti, jams and spreads, pasta sauces
  and passata), 71 products in 21 formats, about 290 materials — retail sizes, multipacks, club and foodservice packs,
  the grocers' own-label packs as variants of the standard material, a handful launching and a handful delisting — with
  a Pareto volume shape (a fifth of the materials carry about four-fifths of the cases) and a long tail ranged at one
  account. Two plants: Echuca, Victoria (tomatoes, sauces, beans and spaghetti, spreads, part of the fruit) and Loxton,
  South Australia (the rest of the fruit and the snack cups); canned fruit is made at both. Three 3PL stocking DCs —
  Melbourne, Sydney and Brisbane — are each replenished from both plants, so any DC can be served from the nearer plant
  or the further one at a dearer lane, and each serves the customers' DCs in its region (Perth from Melbourne); no
  customer is served direct from a plant. One reporting entity for supply and revenue; the cost side has two legal entities.
  `structures.py` is what Caldera makes, sells to, operates and is organised as, built from a product × format ×
  variant recipe;
  `calendar.py` the 4-4-5 trading calendar (fiscal year July–June, every week in exactly one period);
  `costs.py` the cost side — the two legal entities, each ledger's cost centres, the mapping onto the plan's, the chart of
  accounts, the drivers a cost line may declare, and the ledgers' actuals by entity × ledger cost centre × account ×
  period (a random stream of its own, so nothing else moves);
  the opex schedule's acts as seeded (each line's driver; a typed rate and two typed months), and labour's registers —
  each entity's agreement, on-costs, positions by role, people by name;
  `history.py` three years of shipments by material × ship-to × week — each row with what it invoiced, gross at list and net
  sales, because history is revenue and units and price is the derived figure — the price lists, and what each earlier cycle's
  latest view said (the forecast snapshots accuracy is read from); `registers.py` the
  versions, roles, capacity register and planning assumptions; `plan.py` what the people typed — layer entries on
  each version, the promotions calendar (mostly price-led, as ambient grocery is, with display-only gondola ends, a
  Christmas seasonal display, a points offer, a clearance run-out and events funded by catalogue and display fees, retail
  media and the co-op envelope), the neighbour lines declared on events, the terms register (with each major's annual
  co-op envelope); `sender.py` the promotions system that keeps Westbrook's
  and Carters' calendars and sends them in its own codes (its planning accounts, product groups, tactics, fund types,
  status words): the calendar re-issued through its two doors — their events as the export already taken in, with the
  mapping of their codes to ours accepted when the sender was connected, Merritt's typed in the plan — the mechanic,
  funding-type and status lists the mapping lands on, and the next export waiting in `data/generated/sender/` to be
  taken in (new events, one moved, one cancelled, one for an account whose promotions are typed here, and codes the
  mapping has not seen); `forecaster.py` the forecasting system that makes the statistical baseline of the three
  largest accounts and sends it as a run — a header saying what the numbers are and the series by material × account ×
  week, in the same codes as ours — with the disagreements such a system has (a renumbered pack, a product the plan has
  not got, a display shipper, two series dropped) and a next run waiting that left promotions in.
  Deterministic from a seed; output is regenerated
  every run and never committed.
- `ingest/pipeline.py` — dlt: one resource per file into `bronze`, replaced whole on every load. A plan table is fed by
  the generated file and then every file the face has placed under `data/landing/plan/<table>/`, in file order —
  file order is time order; the face is the landing's only writer. The sender's outbox (`data/generated/sender/`) is
  read by the face, never loaded: a file reaches the landing only when someone takes it in.
- `face/` — the planning face, organised around the person. The processes in play are a register (`face/__init__.py`
  `PROCESSES`: integrated business planning, financial planning, the strategic plan, actuals, admin), each with its areas and pages and the verbs
  that make a page relevant; a person sees the processes, areas and pages their roles reach, and their home page is
  what those processes expect of them today — their entries awaiting the cycle, the gap to reference, the versions,
  the files waiting for a run. Above that, **My attention**: every row the last run routed to the person — the
  worklists under `models/worklists/` (entries refused, withdrawals refused, entries unresolved, reasons unknown,
  cells below zero, promotions held, promotions refused, mappings to review), each row carrying `whose`, with `plan.run_health` as the row-per-worklist index the run page
  shows. Nothing on the home page is typed: a row exists because the run produced it. Someone who submits the
  demand plan gets the plan as a whole as their home page, in money — a case means one thing at a material and nothing
  above it: the fiscal year's net sales against last year's invoiced, net sales against the reference on the periods both value, **forecast accuracy** (the plan judged as a forecast: what the
  cycle three periods before said against what shipped, over the last twelve closed periods, 1 − Σ|error| ÷ Σ shipped,
  with bias) and how many units are in; the year **per week** — by period (each period's total over its weeks, the week count in
  the label) or by week, net sales invoiced then planned, with the reference dashed and last year faint, because a 4-4-5
  period total steps every third point by the calendar alone and the trend only reads per week; cases offered only once
  the chart is drilled to a material; the plan by
  category opening to products and materials — the material structure, with accuracy and bias at every node; the
  units with their submission state; versions; the pages their roles reach; and the submission ladder across the
  bottom (inputs in, plans built, units submitted, plan submitted, reference declared) with the one act at its end.
  The **forecast accuracy** page under Demand reads the same judgement at every lag, by unit and by period. **The map** (in the top bar, and from the home page) draws the plan end to end — what
  sends, what the plan holds, what it makes, what is read — from a register beside the menu (`MAP_NODES`, `MAP_FLOWS` in
  `face/__init__.py`): every box opens the page that owns it and says what waits there after the last run, a heavy line
  from the left is a door, a dashed box is named and not yet built. "Acting as" in the top bar opens the sign-in screen: every person, the roles they hold
  and where, one click to act as them. Pages built so far: the demand plan (grouped category → product → standard material as a collapsible tree, opening on the categories with the total beneath, group rows summed and read-only; with **inputs directly into cells**: choose an account and the layer you
  enter as, click a plan cell, type the total you want, give a reason — what is placed is an entry on that layer for the
  difference, at that material, account and period; the cell shows the run's number with the change marked pending until
  the next run; actual cells and other people's layers never open), and **submissions**: demand is planned by unit
  (Westbrook, Carters, Merritt, other independents, Horeca — a level of the customer structure between account and ALL,
  each with its own planner) and led by the head of demand planning; a submission is an act row (submit or
  reopen) on a subject (a layer, a unit's demand, the plan) at a node, never a flag; the run derives every state —
  submitted, rolled up from beneath, ready, open, nothing — and the matrix page shows layers down, units across, the plan
  at the end, with the acts a person may make where they hold the verb. Account-facing layers submit at the account and
  roll to the unit; the planner's own layers submit at the unit; material-scoped layers submit once at the plan. A
  submitted layer is closed at that scope: a cell or entry there is refused until reopened. States roll up, acts do not:
  a holder may submit over open children, on record, and the gap stays visible ("submitted · 2 open beneath") — every period across, closed periods as actuals, then each fiscal
  year's total beside the same periods a year earlier and the reference version — the entries on a
  version (a withdrawal is a later row that names the entry; the entry stays, struck through), a new entry placed as a
  file after its checks (version open, who holds the layer's enter verb, both scopes resolve, window in horizon, the
  reason offered on the layer — flagged, not refused), the revenue bridge, the gap to the reference version by period and by material, launches and exits as the
  innovation layers' entries, **promotions** — one calendar, two doors: each account says where its promotions are
  kept (`promotions_master`: the promotions system for Westbrook and Carters, typed here for every other account); a file
  from the promotions system is taken in by an act (its header and funding lines into the landing, a re-sent event
  replacing the earlier, a cancelled one removed), and every code in it no mapping has named is given a proposed target
  with a confidence and a one-line reason by the shared mapping tool (`99_core_clones/coa_map-*.whl`, a real model call
  when `ANTHROPIC_API_KEY` is set; without it the take-in says the first pass did not run and the codes wait for a
  person). The page shows the calendar with each event's source and, for a sent event, its own codes beside ours, and
  any funding the gross-to-net does not price yet; **what each event does** — gross uplift, the dip after, what it takes
  from (or lends to) the neighbouring ranges it declares, the net incremental in cases and net sales, and its return
  (net incremental net sales less the price reduction and scan funding given on every other case in its window, less its
  lump sums); the **neighbour lines** — a rate on a neighbouring range's baseline in the event's window, declared by the
  event's owner on either door, cases only, never estimated, absent meaning none declared; the **held** events (a code not mapped or not reviewed) with what each
  waits for and the cases and net sales it would bring; the **refused** (the wrong door, with the reason) and the
  cancelled; and, for an account whose promotions are typed here, a **new event** form — account, promo group, window,
  mechanic, price reduction per case, scan funding, fixed fee, retail media, co-op drawdown, status — whose window
  defaults to the account's promotional week and whose uplift and dip default from the mechanic register (one or more
  mechanics in each of seven families; one mechanic per event, a supporting catalogue page or display being a fee on the
  price event) unless overridden with a note, placed after its checks like an entry (an event typed at an account the
  promotions system keeps is refused; a drawdown with no envelope to draw on is refused; a window off the account's
  promotional week is placed and flagged). The **promotions calendar** draws our trading weeks as the grid and each event
  as a bar on its true dates, filterable by account and promo group: a grocer's promotional week runs Wednesday to
  Tuesday, so its bar starts mid-week and straddles two of our weeks, and an event opened shows the split it produces —
  days and cases in each trading week, and the periods it lands in. **Their structure to ours** lays the promotions
  system's structure against the plan's — planning account to account, product group to promo group and its materials,
  tactic to mechanic and family, fund type to the gross-to-net line it prices into, status to calendar — with one event
  read both ways. The **mapping review** lists the codes waiting for a person, lowest confidence
  first: accept, or alter to another of ours with a reason (or map a code nobody proposed); a held event enters on the
  first run after. Held, refused and to-review rows reach trade marketing through My attention. The terms register (terms grouped by account with every attribute, and each co-op envelope as committed, drawn by the events in the calendar, and remaining; **price lists** with the accounts on each, the price before and in force per material and the dated increase events) — read by every planner, amended only by whoever holds the register's maintain verb (Finance): an amendment or a price change is a new row from a date, never an edit of the row in force,
  **withdrawal** — one act on every grid: a save or one figure of it (a layer entry, a Finance figure or save, a schedule
  act or save) is named by a later act with a reason, by its author or a holder of the verb, after a page showing every
  figure that will change, calculated by the run's own arithmetic over the acts that remain; nothing is deleted, and a
  figure the withdrawn one had written over stands again; the **change history** (a tab of Versions) — every act on a
  version in order, who, when, why, and whether it stands, was withdrawn, was overwritten or was refused
  (`plan.change_record`); the **versions** — each open or closed, read from a register of acts: the holder of the freeze verb closes one and reopens
  it with a reason, each with a receipt and in force at once; a closed version takes no entry or change and stays readable;
  a version another is read against is not reopened. The **strategic plan** is its own process: a *five-year plan*
  (FY2027–FY2031) by category × channel — the latest view rolled up where it covers a whole year, grown by Finance's rates by
  category beyond — and the five capacities it declares by year with their tiers: production computed (line hours by plant,
  from the machine register and the routes; first break, or none), working capital as receivables at terms with no limit
  declared, and storage, material and logistics saying they have no data behind them. **Financial planning** is laid out as the chain Finance builds a plan along, one area per step in order —
  *Revenue · Cost of goods · Labour · Opex · Capital · Non-operating · Balance sheet and cash · Statements · Set-up* — a
  step not yet built shown in its place and saying so. **Revenue** is one entry with a tab per measure, *Volume · Price ·
  Revenue*, then *Versions*, with prices and terms and promotions linked from it to where they live under Demand; the
  *Cost of goods* entry under Cost of goods is the same grid's *Cost of goods · Margin* tabs on the same working copy. Each measure tab is the same grid — the material structure down (a
  node and the level beneath it), periods across, one measure per row (cost of goods and margin with the lines they are
  calculated from above them) — read three ways: Finance's plan with the demand plan under every figure, the demand plan,
  and the variance. Finance types volume on its tab and price on its tab, at any node (all, a unit or an account × any
  material node) in open periods, and the grid recalculates on Enter or Tab with no run — totals above, children beneath,
  revenue, the variance and the year — in a working copy that is Finance's alone until saved (hatched as unsaved, the
  same on every tab, kept while they move about, dropped by Discard, lost on a restart; *Undo* takes the last figure out and
  puts the rest again as typed — one a later figure had written over comes back — and *Redo* puts it back, until a save); a volume at a node is written
  down to its children by the demand plan's shape at the moment it is typed, a price moves every price beneath by one
  proportion so the node's calculated price is what was typed, and the last figure typed wins at every level. Save asks
  one reason, writes one file — each figure as typed and where, and the cells it wrote — and carries it into the plan
  with the run scoped to Finance's part. The app and the model call the same function (`calc/finance.py`), which reads
  its rules — how each measure adds up at a total, how a figure typed at a total spreads, who types it — from the
  measure register `plan.ref_grid_measure`; the formulas (revenue = volume × price, cost of goods = volume × standard
  cost, margin = revenue − cost of goods) are written in the function and checked against the register's words by
  `tests/measure_register.py`. Cost of goods and margin are empty and say why: Caldera has no standard cost per case yet.
  A figure holds its value against the demand plan, the variance moves when the demand plan moves, and a figure whose
  demand plan has moved since it was typed is marked. Fed or built is declared per account × material: Export and three
  foodservice cans at Bradfield are built by Finance, with nothing beneath; the rest is fed. *Versions* is net sales by
  fiscal year across its periods, per week — invoiced, the latest view and its reference laid over one another, last year
  faint; read against the reference only on the periods both value, with the gap by period; at the plan or any node of
  either structure, the level below as a split.
  Finance's plan never enters the demand stack or the gross-to-net; **where each number comes from** under financial planning's Set-up (the chain —
  volume, price and terms,
  promotions, delivery, cost of goods, inventory, labour, opex, capital, non-operating, balance sheet — each step filled
  by the model behind it or by a Finance assumption, declared per step; Caldera fills the first three from the model and
  says *not yet filled* for the rest; beneath, fed or built per account × material) and beside it **how each figure is
  calculated** (the measure register: every grid a person types into, each figure's rule in words — how it is set, how it
  adds up at a total, how a figure typed at a total spreads, who types it) and the **assumptions** (the one set every
  plan on a version is valued with — AUD/USD, CPI, the wage and commodity indices, returns and claims — by period, the
  reference version's beneath each, and beside each what reads it; Finance amends one as a value from a period, through the
  landing, in force after the next run, and the plan valued and the opex schedule read it by period), the rungs named but not yet built
  (supply, capacity, inventory, scenarios, management review), and the run — the same two commands the schedule runs, started by
  whoever holds `run.plan`, the log kept; under **Set-up** the **cost centres** — two legal entities, each on its
  own ledger with its own cost centres (Caldera Foods; Riverbend Fruit Co, the Loxton business bought at the start of
  FY2026), read through one set of the plan's own: *Cost centres* (each of ours with the ledger cost centres mapped to it,
  per entity, and the last twelve closed periods' actuals), *Entities and ledgers*, *Actuals* (by our cost centre or each
  ledger's own × account × closed period) and the *Mapping review* — a ledger cost centre no mapping carries is an item on
  the doors' one queue, decided as map to one of ours, open a planning cost centre for it, or leave out; intercompany
  charges between the entities are left out and the pages say so; the **opex schedule** — entity × our cost centre ×
  account × period for the twelve periods after the last closed, closed periods beside it as actuals: each line a driver
  (cases made at a plant, cases shipped, net sales, a flat amount, or last year × the index) and a rate, the rate
  calculated from the last twelve closed periods shown beneath the one in use; each month driver × rate until someone
  types it, a typed month held with the calculated amount beneath it and a mark when that has moved since; typed into a
  working copy that recalculates at once (the same function as the run, `calc/schedule.py`), Save with one reason
  releasing it by a run scoped to the schedule, Discard, Undo and Redo (a step each: a month, a rate, a driver, a confirmed reset), *Recalculate* (calculated months only — it says how many typed
  months it left alone) and *Reset to base* (a confirmation naming the typed months it removes); months typed by the cost
  centre's budget holder, drivers and rates by Commercial finance; its labour lines filled by the **headcount** — *By
  role* in the factory cost centres (positions by classification priced through each entity's agreement, the increase
  from January 2027, a campaign casual pool at a loading; a name beside a position carries nothing) and *By name* in the
  overhead ones (each person's salary, incentive and dates; a named vacancy at a typed figure) — which is individual pay,
  read only by the holders of `read.pay` (Commercial finance, People and culture): without it the tab is not offered and
  the name-based labour is left out of the schedule's and the cost centre pages' figures and totals, with a line saying
  so; and under Admin the **structures as loaded** — read-only: each structure's
  system, its latest load and the one before, what changed between them, the members not yet fit to plan with whom to
  ask, the members held provisionally ahead of the client's master, and the open disagreements by door. The plan does
  not maintain master data; this is what it says about the state of what it was given. Every act writes a receipt under `data/receipts/`. What a page shows is what
  the last run said: an entry placed is in the plan after the next run, and a withdrawal of an entry the warehouse has
  not yet seen is refused, honestly, until it has.
  The navigation is process → area → entry and never deeper: an object with several views is one entry that opens on
  tabs — the demand area's entries are *Demand plan* (plan · entries · new entry), *Submissions*, *Baseline*
  (statistical forecast · forecast accuracy), *Promotions* (events · calendar · mapping review · their structure to
  ours), *Prices and terms* (terms · price lists) and *Revenue bridge*; a person sees the tabs their roles reach.
  Above the menu, the **context**: version, year, customer (all, a unit or an account) and material (all, a category, a
  product or a material), chosen once and held in the page's address, so every link carries it and a link sent opens on
  the same context. A person whose assignments name customers or materials is offered those; a page that does not use a
  selection says so beside it. The demand plan opens its cells when the customer is an account; Revenue,
  its versions chart, submissions (a unit by account) and the promotions calendar read it too.
  **Every door decides the same way.** The promotions system and the forecasting system are taken in by an act whose
  declarations are checked as data; each disagreement between what arrived and the plan's own structures is an item of
  a declared kind (`plan.ref_door_resolution`: per door and kind, the decisions a person may make, what each names of
  ours and the verb it needs); the mapping review and the statistical forecast page list the items the same way, a
  decision is one checked, receipted act in one register for every door (`plan/reg_door_act`), and the latest act per
  item stands for every later arrival. The mapping tool's first pass writes proposals there, never in force until a
  person accepts one. What stays per door is the query that finds its disagreements. A forecasting run arrives once
  and is **taken in account by account**: the **statistical forecast** page opens on the person's own accounts, reads
  each waiting run against our calculation before it is taken in, and the planner whose scope reaches the account takes
  it in for that account (the head of demand for any) — so a run is in force for one account and still waiting for
  another; the run's disagreements are routed to the planners of the accounts they reach and decided once.
  The face's pages and checks are here; its chrome, session, landing writer, receipts, roles, run and warehouse access
  are the **chassis** (`99_core_clones/chassis-*.whl`, a dependency in `pyproject.toml`) — the part of a face that does
  not know which method it carries, shared with the other builds. `99_core_clones/chassis_usage.md` says how it is used.
- `config.yaml` + `models/` — the SQLMesh project:
  - `dims/` the calendar (weeks, periods with relative position), versions, the mechanic, funding-type and promotion
    status registers, each account's promotional week, the four structures as hierarchy
    bridges (material, customer, location, organisation), the bill of materials, routes, lanes, the capacity
    register, the assumptions register, roles and the entitlements derived from them
  - `dims/` also the cost side: the legal entities, each ledger's cost centres, the chart of accounts, the drivers, and
    the cost centre mapping as loaded
  - `history/` the ledgers' actuals (`cost_actual`); shipments at week and period grain with gross and net sales invoiced, price lists, each earlier cycle's latest view at the plan's grain
  - `plan/` the demand plan and its money: the category trend and the history shape fitted from cleansed
    shipments; the layer entries as filed and resolved to the grid; layer 1 computed for the open version and
    entered for the frozen one — the open version's baseline is `baseline_in_force`: our own calculation
    (`baseline_reference`, kept for every account as the reference) for the accounts the plan calculates, the forecasting
    system's run (`forecast_run`, in force per account, and `forecast_series`) for the accounts that take it, spread to ship-tos by our history
    shape, and our calculation again wherever the run does not reach; what people decided where the two structures
    disagree is read from the doors' one act register (`door_act`, the latest act per item; `forecast_resolution` and
    the promotions `promo_mapping` are its two doors' views), and what nobody has decided is the worklist `forecast_queue`; the terms and price lists effective-dated (the latest act per date, each row running to the day before the
    next); the co-op envelopes drawn (`terms_envelope`); the promotions calendar resolved from both doors (`promo_sender_event` through the
    mapping register `promo_mapping` and the funding lines `promo_funding`; `promo_typed_event` with the mechanic's
    default response; `promo_event` the one calendar, each event flagged where it is off its account's promotional week) and its uplift,
    dip and neighbour lines (`promo_neighbour`), day-weighted into the weeks a dated window touches; each event's effect
    and return (`promo_event_effect`); its lump sums — fixed fee, retail media, co-op drawdown — in the long form; the stack (every layer line, keyed by version and source); the unconstrained demand plan
    at storage grain and at the review's grain with each layer beside the total; the list price and terms in force
    by week; every line valued through the gross-to-net (wide, and long with each deduction's attributes); the
    revenue bridge by layer; the gap to the version's reference; the cost side's mapping in force (`cost_centre_map`, the
    register with the ledgers' queue decisions), the plan's cost centres (`planning_cost_centre`) and the actuals read
    through them (`cost_actual`, each row mapped, unmapped or left out); the opex schedule (`opex_schedule`, a Python
    model over `calc/schedule.py`) from its acts (`schedule_edit`) and the labour model (`labour_line` position by position
    and person by person, `labour_cost` by cost centre × account — what the schedule reads); the plan judged as a forecast (`forecast_accuracy`:
    the snapshot `lag` periods before against shipments, at material × account × period, both structures beside)
- `audits/` — the checks every model runs: every member reaches its root, every week in one period, exactly one
  open period, vocabularies, references resolve, one person does not both enter demand and enter the supply
  constraint; an entry is on a known version, resolves to leaves, and was entered by the layer's owner; every
  case has a list price in force; gross less every deduction is net on every line; the long form ties to the wide; an
  event in the calendar came through its account's door; a mapping in force lands on a member of our list; a
  neighbour line names a range of ours and its sign fits its effect.

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
