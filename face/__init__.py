"""The planning face, on the chassis. The chassis is the shell, the session, the landing writer, receipts, roles, the
run and the read-only warehouse; this package is the plan's pages and the plan's checks — what an entry must satisfy
to be placed, which the chassis does not know.

  uv run python -m face            # http://localhost:8010 — reloads on changes under face/; --no-reload for the room
"""
from __future__ import annotations

import pathlib

import chassis
from chassis.roles import WarehouseRoles
from chassis.session import Session, default_holder
from chassis.ui import Shell
from chassis.warehouse import q

ROOT = pathlib.Path(__file__).resolve().parents[1]
chassis.configure(root=ROOT, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing",
                  run_commands=[["uv", "run", "python", "-m", "ingest.pipeline"],
                                ["uv", "run", "sqlmesh", "plan", "prod", "--restate-model", "*", "--auto-apply", "--no-prompts"]])

roles = WarehouseRoles(q)
session = Session(default=default_holder("layer.1.enter", roles.actions_held))

SHELL = Shell(brand="Caldera", strapline="integrated planning", home="plan.demand", who="select", nav=[
    # the areas are the process; the components of each sit beneath it
    ("demand", "Demand", [("demand", "Demand plan", "plan.demand", {}), ("entries", "Entries", "plan.entries", {}),
                          ("new", "New entry", "plan.entry_new", {}), ("events", "Promotions", "plan.events", {}),
                          ("terms", "Terms", "plan.terms", {}), ("money", "Revenue bridge", "plan.money", {})]),
    ("supply", "Supply", [("supply", "Supply plan", "plan.rung", {"slug": "supply"}), ("capacity", "Capacity", "plan.rung", {"slug": "capacity"}),
                          ("inventory", "Inventory", "plan.rung", {"slug": "inventory"})]),
    ("innovation", "Innovation", [("launches", "Launches", "plan.launches", {}), ("exits", "Exits", "plan.exits", {})]),
    ("reconciliation", "Reconciliation", [("gap", "Gap to reference", "plan.gap", {}), ("scenarios", "Scenarios", "plan.rung", {"slug": "scenarios"})]),
    ("management", "Management", [("versions", "Versions", "plan.versions", {}), ("review", "Management review", "plan.rung", {"slug": "review"})]),
    ("admin", "Admin", [("run", "Run and health", "plan.run", {})]),
])

# the entry file's contract — every column the landing writes; the generator writes the same
ENTRY_COLUMNS = ["entry_id", "action", "withdraws", "version_id", "layer_no", "entered_by", "entered_on", "reason_code", "effect_type",
                 "scope_material", "scope_customer", "period_from", "period_to", "value_kind", "value", "spread_rule", "note"]
