#!/usr/bin/env python3
"""Add a hold_position faction directive to The Hiparunites targeting Ulum Highlands.

Directive is scoped to the two pops currently at Ulum Highlands via territory_pop_ids,
so the six Hiparun's Rift pops are unaffected.
"""
import json
import sqlite3
import sys
from uuid import uuid4

DB = sys.argv[1] if len(sys.argv) > 1 else "scenarios/oros_test_sandbox.db"

HIPARUNITES_ID  = "416be3b9-a3e5-44a5-b8ac-10e03ba95438"
ULUM_LOC_ID     = "59e2edc9-210d-4cec-a181-9a6eaffb1ca8"
ULUM_POP_IDS    = [
    "6c8a8a55-2bd6-4e78-8c0c-6173d0a06fb0",
    "51026850-c9e3-438e-9358-eab87718b097",
]

directive = {
    "id": str(uuid4()),
    "label": "Hold Ulum Highlands",
    "directive_type": "hold_position",
    "target_location_id": ULUM_LOC_ID,
    "issued_at_tick": 0,
    "required_skill": None,
    "action_weight_modifiers": {},
    "slot_modifier": 0,
    "interval_ticks": 0,
    "last_triggered_tick": 0,
    "cargo_resource_type": None,
    "cargo_quantity": 0,
    "target_pop_id": None,
    "territory_pop_ids": ULUM_POP_IDS,
}

con = sqlite3.connect(DB)
row = con.execute(
    "SELECT active_directives FROM factions WHERE id = ?", (HIPARUNITES_ID,)
).fetchone()
if row is None:
    print(f"ERROR: faction {HIPARUNITES_ID} not found")
    sys.exit(1)

existing = json.loads(row[0] or "[]")
existing.append(directive)
con.execute(
    "UPDATE factions SET active_directives = ? WHERE id = ?",
    (json.dumps(existing), HIPARUNITES_ID),
)
con.commit()
con.close()
print(f"Done — directive '{directive['label']}' ({directive['id']}) added to The Hiparunites.")
print(f"  target_location: {ULUM_LOC_ID}")
print(f"  territory_pop_ids: {ULUM_POP_IDS}")
