#!/usr/bin/env python3
"""Add a patrol faction directive to Asha Dunewalker Clan.

Scoped to the three pops currently at Dunes of Tor (including Asha Keln's pop),
patrolling the Dunes of Tor location. The five Taem's Oasis pops are unaffected.
"""
import json
import sqlite3
import sys
from uuid import uuid4

DB = sys.argv[1] if len(sys.argv) > 1 else "scenarios/oros_test_sandbox.db"

ASHA_CLAN_ID   = "51e20a1b-2cb0-48e1-ab39-f18776db0a56"
DUNES_LOC_ID   = "a3e98311-59ef-4972-96ea-5c03e5ef17ee"
DUNES_POP_IDS  = [
    "06a075d5-7997-48f2-a4a3-9af14e80a7b6",
    "d845ff7a-1946-424a-8b35-4ef9cc7df816",
    "5e141b9f-0ae4-4e84-a2d2-3c8e378a9cef",  # Asha Keln's pop
]

directive = {
    "id": str(uuid4()),
    "label": "Patrol Dunes of Tor",
    "directive_type": "patrol",
    "target_location_id": None,
    "issued_at_tick": 0,
    "required_skill": None,
    "action_weight_modifiers": {},
    "slot_modifier": 0,
    "interval_ticks": 0,
    "last_triggered_tick": 0,
    "cargo_resource_type": None,
    "cargo_quantity": 0,
    "target_pop_id": None,
    "territory_pop_ids": DUNES_POP_IDS,
    "territory_location_ids": [DUNES_LOC_ID],
}

con = sqlite3.connect(DB)
row = con.execute(
    "SELECT active_directives FROM factions WHERE id = ?", (ASHA_CLAN_ID,)
).fetchone()
if row is None:
    print(f"ERROR: faction {ASHA_CLAN_ID} not found")
    sys.exit(1)

existing = json.loads(row[0] or "[]")
existing.append(directive)
con.execute(
    "UPDATE factions SET active_directives = ? WHERE id = ?",
    (json.dumps(existing), ASHA_CLAN_ID),
)
con.commit()
con.close()
print(f"Done — directive '{directive['label']}' ({directive['id']}) added to Asha Dunewalker Clan.")
print(f"  territory_location_ids: {[DUNES_LOC_ID]}")
print(f"  territory_pop_ids: {DUNES_POP_IDS}")
