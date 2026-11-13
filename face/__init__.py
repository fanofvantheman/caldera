"""The planning face, on the chassis. The chassis is the shell, the session, the landing writer, receipts, roles, the
run and the read-only warehouse; this package is the plan's pages and the plan's checks — what an entry must satisfy
to be placed, which the chassis does not know.

The product is organised around the person, not the process: the processes in play are a register below, each with
its areas and pages and the verbs that make a page relevant; a person sees what their roles reach, and their home
page is what those processes expect of them.

  uv run python -m face            # http://localhost:8010 — reloads on changes under face/; --no-reload for the room
  uv run python -m face --skin     # the same face in the specimen client colours below
"""
from __future__ import annotations

import pathlib
import sys

import chassis
from chassis.roles import WarehouseRoles
from chassis.session import Session, default_holder
from dataclasses import dataclass, field

from chassis.ui import Area, Choice, Process, Section, Shell, Tab
from chassis.warehouse import q

from flask import request

from . import reads

ROOT = pathlib.Path(__file__).resolve().parents[1]
chassis.configure(root=ROOT, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing",
                  run_commands=[["uv", "run", "python", "-m", "ingest.pipeline"],
                                ["uv", "run", "sqlmesh", "plan", "prod", "--restate-model", "*", "--auto-apply", "--no-prompts"]])

roles = WarehouseRoles(q)
session = Session(default=default_holder("layer.1.enter", roles.actions_held))

READ = ["read.plan"]
ENTER = [f"layer.{n}.enter" for n in (1, 2, 4, 6, 7, 8, 9)]
HEALTH = "plan.run_health"      # one row per worklist; every worklist row carries `whose`
RUNG = "plan.rung"
FIN_READ = ["register.assumptions.maintain", "overlay.finance.enter", "read.proof"]
COST_READ = ["register.cost_centre_map.maintain", "register.cost_input.maintain", "schedule.line.enter", "headcount.enter", "read.proof"]
CONTEXT_ALL = ("version", "fy", "customer", "material")          # the context keys a page applies (DEC-20261113-07)

# ---- the processes in play: a register, not a menu ----
PROCESSES = [
    Process("ibp", "Integrated business planning", says="Demand through supply to the one set of numbers the business runs on.", areas=[
        # an object with several views is one entry with tabs; the menu stays process → area → entry
        Area("demand", "Demand", [
            Section("demandplan", "Demand plan", "plan.demand", tabs=[
                Tab("demand", "Plan", "plan.demand", verbs=READ, uses=("version", "customer", "material")),
                Tab("entries", "Entries", "plan.entries", verbs=READ, uses=("version",)),
                Tab("new", "New entry", "plan.entry_new", verbs=ENTER)]),
            Section("submissions", "Submissions", "plan.submissions", verbs=READ, uses=("version", "customer")),
            Section("baseline", "Baseline", "plan.forecast", tabs=[
                Tab("forecast", "Statistical forecast", "plan.forecast", verbs=["layer.1.enter", "read.drill"]),
                Tab("accuracy", "Forecast accuracy", "plan.accuracy", verbs=READ)]),
            Section("promotions", "Promotions", "plan.events", tabs=[
                Tab("events", "Events", "plan.events", verbs=["register.promo_calendar.maintain", "layer.6.enter", "read.drill"]),
                Tab("calendar", "Calendar", "plan.calendar", verbs=["register.promo_calendar.maintain", "layer.6.enter", "read.drill", "read.plan"], uses=("customer",)),
                Tab("mapping", "Mapping review", "plan.mapping", verbs=["mapping.accept", "mapping.alter"]),
                Tab("structure", "Their structure to ours", "plan.mapping_structure", verbs=["mapping.accept", "mapping.alter", "register.promo_calendar.maintain", "read.drill"])]),
            # the rate registers: every planner reads them; only Finance (the holders of the maintain verbs) amends them
            Section("prices", "Prices and terms", "plan.terms", tabs=[
                Tab("terms", "Terms", "plan.terms", verbs=["register.terms.maintain", "register.price_list.maintain", "read.drill", "read.plan"]),
                Tab("pricelists", "Price lists", "plan.price_lists", verbs=["register.price_list.maintain", "read.drill", "read.plan"])]),
            Section("money", "Revenue bridge", "plan.money", verbs=["read.drill", "read.proof", "register.terms.maintain"], uses=("version",)),
        ]),
        Area("supply", "Supply", [
            Section("supply", "Supply plan", RUNG, {"slug": "supply"}, verbs=["delta.supply.enter", "register.supply_plan.maintain", "policy.production.accept", "read.proof"]),
            Section("capacity", "Capacity", RUNG, {"slug": "capacity"}, verbs=["register.capacity.machine.maintain", "register.capacity.labour.maintain", "register.capacity.storage.maintain", "register.capacity.logistics.maintain", "schedule.line.enter", "headcount.enter"]),
            Section("inventory", "Inventory", RUNG, {"slug": "inventory"}, verbs=["register.service_level.maintain", "register.sourcing.maintain", "delta.supply.enter", "read.proof"]),
        ]),
        Area("innovation", "Innovation", [
            Section("launches", "Launches", "plan.launches", verbs=["layer.7.enter", "structure.material.maintain", "read.drill"], uses=("version",)),
            Section("exits", "Exits", "plan.exits", verbs=["layer.8.enter", "structure.material.maintain", "read.drill"], uses=("version",)),
        ]),
        Area("reconciliation", "Reconciliation", [
            Section("gap", "Gap to reference", "plan.gap", verbs=["review.reconciliation.close", "delta.allocation.enter", "shaping.enter", "version.name", "decision.accept", "read.proof"], uses=("version",)),
            Section("scenarios", "Scenarios", RUNG, {"slug": "scenarios"}, verbs=["scenario.create", "scenario.promote", "decision.accept"]),
        ]),
        Area("management", "Management", [
            Section("versions", "Versions", "plan.versions", verbs=["version.name", "version.freeze", "version.declare_reference", "decision.accept", "decision.record", "read.proof"]),
            Section("review", "Management review", RUNG, {"slug": "review"}, verbs=["review.mbr.close", "decision.accept", "decision.record", "read.proof"]),
        ]),
    ]),
    # the chain Finance builds a plan along, one area per step, in order (DEC-20261113-12); a step not yet built is shown
    # in its place and says so; set-up last, because it is read, not worked
    Process("finplan", "Financial planning", says="The plan valued, step by step: revenue, cost of goods, labour, opex, capital, non-operating, the balance sheet and cash, the statements.", areas=[
        Area("revenue", "Revenue", [
            # one tab per measure of the register, each a view of the same working copy, then the versions laid over one another
            Section("revenue", "Revenue", "plan.revenue", uses=CONTEXT_ALL, tabs=[
                Tab("fin_volume", "Volume", "plan.revenue", {"measure": "volume"}, verbs=FIN_READ),
                Tab("fin_price", "Price", "plan.revenue", {"measure": "price"}, verbs=FIN_READ),
                Tab("fin_revenue", "Revenue", "plan.revenue", {"measure": "revenue"}, verbs=FIN_READ),
                Tab("fin_versions", "Versions", "plan.revenue_versions", verbs=FIN_READ)]),
            # steps of the chain whose registers live under Demand, where the planners read them: shown here as links, not moved
            Section("rev_prices", "Prices and terms · in Demand", "plan.terms", verbs=["register.terms.maintain", "register.price_list.maintain", "read.drill", "read.plan"]),
            Section("rev_promotions", "Promotions · in Demand", "plan.events", verbs=["register.promo_calendar.maintain", "layer.6.enter", "read.drill"]),
        ]),
        Area("cogs", "Cost of goods", [
            # the same page and working copy as Revenue's tabs: a volume typed there shows here
            Section("cogs", "Cost of goods", "plan.revenue", {"measure": "cogs"}, uses=CONTEXT_ALL, tabs=[
                Tab("fin_cogs", "Cost of goods", "plan.revenue", {"measure": "cogs"}, verbs=FIN_READ),
                Tab("fin_margin", "Margin", "plan.revenue", {"measure": "margin"}, verbs=FIN_READ)]),
            Section("standard", "Standard by plant", RUNG, {"slug": "standard"}, verbs=["standard.derive", "standard.declare", "register.cost_input.maintain", "read.proof"]),
            Section("landed", "Landed cost", RUNG, {"slug": "landed"}, verbs=["register.supplier_price_list.maintain", "register.freight_contract.maintain", "register.hedge_book.maintain", "register.customs.maintain"]),
        ]),
        # the cost side: the entities' ledgers read through the plan's own cost centres (DEC-20261113-03)
        Area("labour", "Labour", [
            Section("headcount", "Headcount", "plan.headcount_role", uses=("version", "fy"), tabs=[
                Tab("hc_role", "By role", "plan.headcount_role", verbs=COST_READ),
                Tab("hc_name", "By name", "plan.headcount_name", verbs=["read.pay"])]),
        ]),
        Area("opex", "Opex", [
            Section("schedule", "Opex schedule", "plan.schedule", uses=("version", "fy"), tabs=[
                Tab("sch_schedule", "Schedule", "plan.schedule", verbs=COST_READ)]),
        ]),
        Area("capital", "Capital", [
            Section("capex", "Projects and depreciation", RUNG, {"slug": "capex"}, verbs=["capex.project.enter", "capex.approve", *FIN_READ]),
        ]),
        Area("nonop", "Non-operating", [
            Section("nonop", "Interest, tax and other", RUNG, {"slug": "nonop"}, verbs=FIN_READ),
        ]),
        Area("balance", "Balance sheet and cash", [
            Section("balance", "Balance sheet plan", RUNG, {"slug": "balance"}, verbs=["register.timing_policy.maintain", "read.proof"]),
            Section("cash", "Cash", RUNG, {"slug": "cash"}, verbs=["register.timing_policy.maintain", "read.proof"]),
        ]),
        Area("statements", "Statements", [
            Section("pnl", "P&L plan", RUNG, {"slug": "pnl"}, verbs=["register.assumptions.maintain", "register.timing_policy.maintain", "read.proof"]),
        ]),
        Area("setup", "Set-up", [
            Section("slots", "Where each number comes from", "plan.slots", verbs=FIN_READ),
            Section("rules", "How each figure is calculated", "plan.rules", verbs=FIN_READ),
            Section("costcentres", "Cost centres", "plan.cost_centres", tabs=[
                Tab("cc_tree", "Cost centres", "plan.cost_centres", verbs=COST_READ),
                Tab("cc_entities", "Entities and ledgers", "plan.cost_entities", verbs=COST_READ),
                Tab("cc_actuals", "Actuals", "plan.cost_actuals", verbs=COST_READ),
                Tab("cc_mapping", "Mapping review", "plan.cost_mapping", verbs=["register.cost_centre_map.maintain", "read.proof"])]),
            # the one set every plan is valued with — everyone who plans reads it; Finance amends it (DEC-20261113-10)
            Section("assumptions", "Assumptions", "plan.assumptions", uses=("version", "fy"), verbs=sorted(set(READ + FIN_READ + COST_READ))),
        ]),
    ]),
    Process("actuals", "Actuals", says="What happened, closed and proved, for the plan to be read against.", areas=[
        Area("close", "Close", [
            Section("cycle", "Period control", RUNG, {"slug": "cycle"}, verbs=["cycle.open", "cycle.close", "register.calendar.maintain"]),
            Section("proof", "Proof", RUNG, {"slug": "proof"}, verbs=["read.proof"]),
        ]),
    ]),
    Process("admin", "Admin", says="The run, its health, the registers that hold the rest up.", areas=[
        Area("run", "Run", [
            Section("run", "Run and health", "plan.run", verbs=["run.plan", "read.health"]),
        ]),
        # read-only: what the plan was given, from whom and when, and what is not yet fit to plan — maintained elsewhere
        Area("structures", "Structures", [
            Section("structures", "Structures as loaded", "plan.structures", verbs=["read.plan", "read.health", "structure.material.maintain",
                                                                                      "structure.customer.maintain", "structure.location.maintain"]),
        ]),
    ]),
]

# a specimen of a client's colours: the face takes them on its named objects only (wordmark, bar, selection, edges, chart
# series) and keeps every state mark, verdict and total in the scheme's own tones; without --skin the face is unskinned
SPECIMEN_SKIN = {"primary": "#a8321e", "secondary": "#5b7a2e", "bar": "#2a221d"}
# ---- the map: what sends, the plan, what is read — a register beside the process register, drawn on one page ----
@dataclass
class Node:
    key: str
    band: str                       # sends | plan | made | read — left to right
    label: str
    says: str
    endpoint: str | None = None
    args: dict = field(default_factory=dict)
    anchor: str = ""
    surfaces: list[str] = field(default_factory=list)       # worklists whose waiting items are this node's
    built: bool = True


MAP_NODES = [
    Node("erp", "sends", "The ERP", "structures, history, prices, terms", "plan.structures"),
    Node("fcs", "sends", "The forecasting system", "the baseline, run by run", "plan.forecast", anchor="sender"),
    Node("tpm", "sends", "The promotions system", "events for the accounts it keeps", "plan.events", anchor="sender"),
    Node("ledgers", "sends", "The ledgers", "two entities' actuals, their own cost centres", "plan.cost_entities"),
    Node("people", "sends", "People who enter", "planners, marketing, Finance", "plan.entries"),
    Node("structures", "plan", "Structures", "materials, customers, lanes", "plan.structures"),
    Node("baseline", "plan", "Baseline", "ours and the run, by account", "plan.forecast", surfaces=["plan.worklist_forecast_queue"]),
    Node("calendar", "plan", "Promotions calendar", "one calendar, two doors", "plan.events",
         surfaces=["plan.worklist_promo_mapping_review", "plan.worklist_promo_held", "plan.worklist_promo_refused"]),
    Node("layers", "plan", "Layer entries", "adjustments, launches, exits", "plan.entries",
         surfaces=["plan.worklist_entry_refused", "plan.worklist_withdrawal_refused", "plan.worklist_entry_unresolved", "plan.worklist_reason_unknown",
                   "plan.worklist_entry_after_submission"]),
    Node("submissions", "plan", "Submissions", "by unit, then the plan", "plan.submissions", surfaces=["plan.worklist_open_submissions"]),
    Node("versions", "plan", "Versions", "open or closed, the reference", "plan.versions"),
    Node("rates", "plan", "Prices and terms", "lists and terms in force", "plan.terms"),
    Node("assumptions", "plan", "Assumptions", "one set by period; what reads each", "plan.assumptions"),
    Node("costcentres", "plan", "Cost centres", "ours over each entity's own", "plan.cost_centres", surfaces=["plan.worklist_cost_centre_unmapped"]),
    Node("stack", "made", "The demand plan", "every layer, by version", "plan.demand", surfaces=["plan.worklist_stack_negative"]),
    Node("supply", "made", "Supply plan", "stock, lines and purchases", "plan.rung", {"slug": "supply"}, built=False),
    Node("valued", "made", "The plan valued", "through the gross-to-net", "plan.money"),
    Node("schedule", "made", "Opex schedule", "driver × rate, by cost centre", "plan.schedule"),
    Node("labour", "plan", "Headcount", "by role through the agreement; by name", "plan.headcount_role"),
    Node("accuracy", "read", "Forecast accuracy", "the plan judged as a forecast", "plan.accuracy"),
    Node("gap", "read", "Gap to reference", "what the cycle exists to close", "plan.gap"),
    Node("revenue", "read", "Versions in net sales", "the versions over one another", "plan.revenue_versions"),
    Node("finance", "read", "Revenue", "volume × price, fed or built", "plan.revenue"),
    Node("statements", "read", "Statements", "the P&L read across the chain; the balance sheet", "plan.rung", {"slug": "pnl"}, built=False),
]
# (from, to, what flows); a flow from the first band is a door — something made elsewhere taken in
MAP_FLOWS = [
    ("erp", "structures", "loaded"), ("erp", "baseline", "shipments"), ("erp", "rates", "lists, terms"),
    ("fcs", "baseline", "runs"), ("tpm", "calendar", "events in their codes"), ("ledgers", "costcentres", "actuals in their cost centres"), ("people", "schedule", "typed months and rates"),
    ("people", "layers", "entries"), ("people", "calendar", "typed events"), ("people", "submissions", "acts"), ("people", "finance", "Finance's figures"),
    ("structures", "stack", ""), ("baseline", "stack", ""), ("calendar", "stack", ""), ("layers", "stack", ""), ("submissions", "stack", ""),
    ("versions", "stack", ""), ("rates", "valued", ""), ("assumptions", "valued", "FX, returns, claims"), ("assumptions", "schedule", "CPI"),
    ("stack", "valued", ""), ("costcentres", "schedule", ""), ("labour", "schedule", "labour lines"), ("people", "labour", "positions, people"), ("stack", "schedule", "drivers"), ("schedule", "statements", ""), ("stack", "supply", ""), ("stack", "accuracy", ""),
    ("valued", "gap", ""), ("valued", "revenue", ""), ("valued", "finance", "feeds"), ("valued", "statements", ""), ("supply", "statements", ""),
]

# ---- the context: the selections that mean the same on every page, chosen once in the navigation (DEC-20261113-07) ----
# Held in the address and carried on every link; a person's assignments bound what is offered, not what may be read.
def _scope(who: str | None, dimension: str) -> set | None:
    """The nodes of one structure this person's assignments reach — None when they name none there, or name the root."""
    nodes = {r["node"] for r in q("select distinct node from dims.effective_entitlements where principal = ? and scope_dimension = ?", who or "", dimension)}
    return None if not nodes or "ALL" in nodes else nodes


def _bounded(who: str | None, dimension: str, opts: list[dict]) -> str | None:
    return "the nodes your assignments reach" if _scope(who, dimension) is not None else None


def _versions(who, chosen) -> list[dict]:
    """The plan versions — the actuals are not a version a page plans or reads a plan on, so they are not offered."""
    return [{"value": v["version_id"], "label": f"{v['version_id']} · {v['status']}"} for v in reads.versions() if v.get("version_kind") != "actual"]


def _known_customer(code: str) -> bool:
    return bool(q("select 1 ok from dims.dim_customer_hierarchy where descendant_code = ? limit 1", code))


def _known_material(code: str) -> bool:
    return code == "ALL" or reads.material_node(code) or bool(q("select 1 ok from dims.dim_material where material_code = ? limit 1", code))


def _years(who, chosen) -> list[dict]:
    return [{"value": str(y), "label": f"FY{y}"} for y in reads.fiscal_years(chosen["version"])] if chosen.get("version") else []


def _year_default(who, chosen, opts) -> str | None:
    own = str((reads.version(chosen.get("version") or "") or {}).get("fiscal_year") or "")
    return own if any(o["value"] == own for o in opts) else (opts[0]["value"] if opts else None)


def _customers(who, chosen) -> list[dict]:
    """All, the planning units, the accounts — never a ship-to — in tree order."""
    mine = _scope(who, "customer")
    return [{"value": n["code"], "label": n["label"], "depth": n["depth"]} for n in reads.finance_customer_nodes() if mine is None or n["code"] in mine]


def _customer_default(who, chosen, opts) -> str | None:
    """With nothing chosen: the one account, when the nodes a person is offered reach exactly one (a planner whose unit
    is a single account lands where the demand plan's cells open); otherwise the first node offered."""
    mine = _scope(who, "customer")
    if mine:
        accounts = {r["d"] for r in q(f"""select distinct descendant_code d from dims.dim_customer_hierarchy
                                           where descendant_level = 'account' and ancestor_code in ({','.join('?' * len(mine))})""", *sorted(mine))}
        if len(accounts) == 1 and any(o["value"] == next(iter(accounts)) for o in opts):
            return next(iter(accounts))
    return opts[0]["value"] if opts else None


def _materials(who, chosen) -> list[dict]:
    """All, every category and its products, and the materials of the product in play — the one chosen, or the chosen
    material's — so the list stays short and a material is reached through its product."""
    here = request.args.get("material") or "ALL"
    product = here if q("select 1 ok from dims.dim_material where product_code = ? limit 1", here) else \
        next((r["product_code"] for r in q("select product_code from dims.dim_material where material_code = ?", here)), None)
    rows = q("""select category_code, any_value(category_name) category_name, product_code, any_value(product_name) product_name
                from dims.dim_material group by all order by category_code, product_code""")
    out, cat = [{"value": "ALL", "label": "All materials", "depth": 0}], None
    for r in rows:
        if r["category_code"] != cat:
            cat = r["category_code"]; out.append({"value": cat, "label": r["category_name"], "depth": 1})
        out.append({"value": r["product_code"], "label": r["product_name"], "depth": 2})
        if r["product_code"] == product:
            out += [{"value": m, "label": x["label"], "depth": 3} for m, x in reads.material_tree_under(product).items()]
    mine = _scope(who, "material")
    return [o for o in out if mine is None or o["value"] in mine]


CONTEXT = [
    Choice("version", "Version", _versions, default=lambda who, chosen, opts: reads.default_version() or (opts[0]["value"] if opts else None), strict=True),
    Choice("fy", "Year", _years, default=_year_default, strict=True),
    Choice("customer", "Customer", _customers, default=_customer_default, note=lambda who, opts: _bounded(who, "customer", opts), known=_known_customer),
    Choice("material", "Material", _materials, note=lambda who, opts: _bounded(who, "material", opts), known=_known_material),
]

SHELL = Shell(brand="Caldera", strapline="integrated business planning", home="plan.home", who="select", processes=PROCESSES, links=[("Map", "plan.map")],
              context=CONTEXT, skin=SPECIMEN_SKIN if "--skin" in sys.argv[1:] else None)

# the entry file's contract — every column the landing writes; the generator writes the same
SUBMISSION_COLUMNS = ["submission_id", "action", "version_id", "subject", "scope_node", "submitted_by", "submitted_on", "note"]
ENTRY_COLUMNS = ["entry_id", "action", "withdraws", "version_id", "layer_no", "entered_by", "entered_on", "reason_code", "effect_type",
                 "scope_material", "scope_customer", "period_from", "period_to", "value_kind", "value", "spread_rule", "note"]

# the promotions doors' contracts — the sender's export taken in (header and funding lines, in our layout, their codes),
# the events typed in the plan, and the mapping register; the generator writes the same columns
TPM_EVENT_COLUMNS = ["sender", "sender_file", "version_id", "taken_in_at", "taken_in_by", "event_id", "planning_account", "planning_account_name",
                     "product_group", "product_group_name", "tactic", "tactic_name", "shopper_start", "shopper_end", "status", "uplift_pct",
                     "dip_pct", "baseline_version"]
TPM_FUNDING_COLUMNS = ["sender", "sender_file", "version_id", "taken_in_at", "event_id", "line_no", "fund_type", "fund_type_name", "rate_basis", "rate"]
PROMO_EVENT_COLUMNS = ["event_id", "version_id", "account_code", "promo_group_code", "window_start", "window_end", "mechanic", "uplift_pct", "dip_pct",
                       "tpr_per_case", "scan_funding_per_case", "fixed_fee", "media_fee", "envelope_drawdown", "status", "owner", "baseline_version",
                       "note", "entered_on"]
# a neighbour line on an event: the latest row per version × event × neighbour scope is in force; a rate of zero removes it
NEIGHBOUR_COLUMNS = ["neighbour_id", "version_id", "event_id", "scope_material", "effect_type", "rate", "entered_by", "entered_at", "note"]
# Finance's acts on the rate registers: an amendment is a new effective-dated row in the register's own layout, never an
# edit of the row in force; who placed it is the file's name and the receipt
TERMS_COLUMNS = ["account_code", "instrument_code", "instrument_kind", "driver_basis", "rate", "flow_position", "conditionality",
                 "settlement_timing", "scope_material", "valid_from", "valid_to", "note"]
# Finance's figures: one row per figure typed — a customer node at account or above × a material node × a period, volume
# or price, and the demand plan at that node when typed; the figures of one save share its reason; a release names a save
FINANCE_COLUMNS = ["edit_id", "action", "withdraws", "save_id", "version_id", "scope_customer", "scope_material", "period", "measure", "value",
                   "source_at_entry", "reason_code", "entered_by", "entered_on", "note", "typed"]
PRICE_LIST_COLUMNS = ["price_list", "material_code", "currency", "price_per_case", "valid_from", "valid_to", "event"]
# the forecasting system's door — a run's header and its series as taken in, account by account (one header row per
# account that accepted the run); what people decide where its structures and
# ours disagree is an act in the doors' register (chassis door.ACT_COLUMNS), as the promotions mapping is; the generator
# writes the same columns
FCST_RUN_COLUMNS = ["sender", "run_id", "account_code", "version_id", "taken_in_at", "taken_in_by", "made_on", "last_history_week", "first_week", "horizon_weeks",
                    "grain", "content", "history_basis", "method_note"]
FCST_SERIES_COLUMNS = ["sender", "run_id", "version_id", "taken_in_at", "material_code", "material_description", "sender_hierarchy", "account_code",
                       "week_start", "cases"]
