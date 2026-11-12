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
from chassis.ui import Area, Process, Section, Shell
from chassis.warehouse import q

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

# ---- the processes in play: a register, not a menu ----
PROCESSES = [
    Process("ibp", "Integrated planning", says="Demand through supply to the one set of numbers the business runs on.", areas=[
        Area("demand", "Demand", [
            Section("demand", "Demand plan", "plan.demand", verbs=READ),
            Section("entries", "Entries", "plan.entries", verbs=READ),
            Section("submissions", "Submissions", "plan.submissions", verbs=READ),
            Section("accuracy", "Forecast accuracy", "plan.accuracy", verbs=READ),
            Section("forecast", "Statistical forecast", "plan.forecast", verbs=["layer.1.enter", "read.drill"]),
            Section("new", "New entry", "plan.entry_new", verbs=ENTER),
            Section("events", "Promotions", "plan.events", verbs=["register.promo_calendar.maintain", "layer.6.enter", "read.drill"]),
            Section("calendar", "Promotions calendar", "plan.calendar", verbs=["register.promo_calendar.maintain", "layer.6.enter", "read.drill", "read.plan"]),
            Section("mapping", "Mapping review", "plan.mapping", verbs=["mapping.accept", "mapping.alter"]),
            Section("structure", "Their structure to ours", "plan.mapping_structure", verbs=["mapping.accept", "mapping.alter", "register.promo_calendar.maintain", "read.drill"]),
            # the rate registers: every planner reads them; only Finance (the holders of the maintain verbs) amends them
            Section("terms", "Terms", "plan.terms", verbs=["register.terms.maintain", "register.price_list.maintain", "read.drill", "read.plan"]),
            Section("pricelists", "Price lists", "plan.price_lists", verbs=["register.price_list.maintain", "read.drill", "read.plan"]),
            Section("money", "Revenue bridge", "plan.money", verbs=["read.drill", "read.proof", "register.terms.maintain"]),
        ]),
        Area("supply", "Supply", [
            Section("supply", "Supply plan", RUNG, {"slug": "supply"}, verbs=["delta.supply.enter", "register.supply_plan.maintain", "policy.production.accept", "read.proof"]),
            Section("capacity", "Capacity", RUNG, {"slug": "capacity"}, verbs=["register.capacity.machine.maintain", "register.capacity.labour.maintain", "register.capacity.storage.maintain", "register.capacity.logistics.maintain", "schedule.line.enter", "headcount.enter"]),
            Section("inventory", "Inventory", RUNG, {"slug": "inventory"}, verbs=["register.service_level.maintain", "register.sourcing.maintain", "delta.supply.enter", "read.proof"]),
        ]),
        Area("innovation", "Innovation", [
            Section("launches", "Launches", "plan.launches", verbs=["layer.7.enter", "structure.material.maintain", "read.drill"]),
            Section("exits", "Exits", "plan.exits", verbs=["layer.8.enter", "structure.material.maintain", "read.drill"]),
        ]),
        Area("reconciliation", "Reconciliation", [
            Section("gap", "Gap to reference", "plan.gap", verbs=["review.reconciliation.close", "delta.allocation.enter", "shaping.enter", "version.name", "decision.accept", "read.proof"]),
            Section("scenarios", "Scenarios", RUNG, {"slug": "scenarios"}, verbs=["scenario.create", "scenario.promote", "decision.accept"]),
        ]),
        Area("management", "Management", [
            Section("versions", "Versions", "plan.versions", verbs=["version.name", "version.freeze", "version.declare_reference", "decision.accept", "decision.record", "read.proof"]),
            Section("review", "Management review", RUNG, {"slug": "review"}, verbs=["review.mbr.close", "decision.accept", "decision.record", "read.proof"]),
        ]),
    ]),
    Process("finplan", "Financial planning", says="The plan valued: standard cost, the P&L by cause, the balance sheet rolled from opening actuals, cash.", areas=[
        Area("standard", "Standard cost", [
            Section("standard", "Standard by plant", RUNG, {"slug": "standard"}, verbs=["standard.derive", "standard.declare", "register.cost_input.maintain", "read.proof"]),
            Section("landed", "Landed cost", RUNG, {"slug": "landed"}, verbs=["register.supplier_price_list.maintain", "register.freight_contract.maintain", "register.hedge_book.maintain", "register.customs.maintain"]),
        ]),
        Area("statements", "Planned statements", [
            Section("revenue", "Revenue forecast", "plan.revenue", verbs=["register.assumptions.maintain", "read.proof"]),
            Section("pnl", "P&L plan", RUNG, {"slug": "pnl"}, verbs=["register.assumptions.maintain", "register.timing_policy.maintain", "read.proof"]),
            Section("balance", "Balance sheet plan", RUNG, {"slug": "balance"}, verbs=["register.timing_policy.maintain", "read.proof"]),
            Section("capex", "Capital", RUNG, {"slug": "capex"}, verbs=["capex.project.enter", "capex.approve"]),
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
    ]),
]

# a specimen of a client's colours: the face takes them on its named objects only (wordmark, bar, selection, edges, chart
# series) and keeps every state mark, verdict and total in the scheme's own tones; without --skin the face is unskinned
SPECIMEN_SKIN = {"primary": "#a8321e", "secondary": "#5b7a2e", "bar": "#2a221d"}
SHELL = Shell(brand="Caldera", strapline="integrated planning", home="plan.home", who="select", processes=PROCESSES,
              skin=SPECIMEN_SKIN if "--skin" in sys.argv[1:] else None)

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
PRICE_LIST_COLUMNS = ["price_list", "material_code", "currency", "price_per_case", "valid_from", "valid_to", "event"]
MAPPING_COLUMNS = ["mapping_id", "sender", "subject", "local_code", "local_description", "target_code", "origin", "review_state", "confidence",
                   "rationale", "acted_by", "acted_at", "reason"]
# the forecasting system's door — a run's header and its series as taken in, and the log of what people decided where
# its structures and ours disagree; the generator writes the same columns
FCST_RUN_COLUMNS = ["sender", "run_id", "version_id", "taken_in_at", "taken_in_by", "made_on", "last_history_week", "first_week", "horizon_weeks",
                    "grain", "content", "history_basis", "method_note"]
FCST_SERIES_COLUMNS = ["sender", "run_id", "version_id", "taken_in_at", "material_code", "material_description", "sender_hierarchy", "account_code",
                       "week_start", "cases"]
FCST_RESOLUTION_COLUMNS = ["resolution_id", "sender", "kind", "item_code", "account_code", "resolution", "target_code", "reason", "acted_by", "acted_at"]
