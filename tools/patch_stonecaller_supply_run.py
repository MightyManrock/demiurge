#!/usr/bin/env python3
"""Add a supply_run directive to The Stonecallers faction.

The merchant (trader:merchant) Pop at Qaebdo Cave Village carries
potable_water, food_fauna, and food_flora to the clergy Pop at
The Ancestor Stones.
"""
import json
import sqlite3
import sys
from uuid import uuid4

DB = sys.argv[1] if len(sys.argv) > 1 else "scenarios/oros_test_sandbox.db"

STONECALLERS_ID   = "ca73ff78-3fff-4e30-85ac-cf573e9dd46e"
QAEBDO_LOC_ID     = "b187e5a3-d31a-42a0-9f1f-f68bde37e6e5"   # source (load here)
MERCHANT_POP_ID   = "b80de66d-e373-42d6-88be-c3cc254b23a4"   # carrier
CLERGY_POP_ID     = "03ebb5b6-3bf7-4050-9eca-b0e808f3634e"   # destination pop

directive = {
    "id": str(uuid4()),
    "label": "Supply Run to Ancestor Stones",
    "directive_type": "supply_run",
    "target_location_id": QAEBDO_LOC_ID,
    "issued_at_tick": 0,
    "required_skill": None,
    "action_weight_modifiers": {},
    "slot_modifier": 0,
    "interval_ticks": 0,
    "last_triggered_tick": 0,
    "cargo_resource_type": None,
    "cargo_quantity": 0,
    "cargo_manifest": {
        "potable_water": 2.0,
        "food_fauna":    1.0,
        "food_flora":    1.0,
    },
    "target_pop_id": CLERGY_POP_ID,
    "territory_pop_ids": [MERCHANT_POP_ID],
    "territory_location_ids": [],
}

con = sqlite3.connect(DB)
row = con.execute(
    "SELECT active_directives FROM factions WHERE id = ?", (STONECALLERS_ID,)
).fetchone()
if row is None:
    print(f"ERROR: faction {STONECALLERS_ID} not found")
    sys.exit(1)

existing = json.loads(row[0] or "[]")
existing.append(directive)
con.execute(
    "UPDATE factions SET active_directives = ? WHERE id = ?",
    (json.dumps(existing), STONECALLERS_ID),
)
con.commit()
con.close()
print(f"Done — directive '{directive['label']}' ({directive['id']}) added to The Stonecallers.")
print(f"  carrier pop:      {MERCHANT_POP_ID}  (merchant at Qaebdo)")
print(f"  destination pop:  {CLERGY_POP_ID}  (clergy at Ancestor Stones)")
print(f"  cargo manifest:   {directive['cargo_manifest']}")
