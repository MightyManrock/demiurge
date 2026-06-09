"""Patch the Oros test sandbox: add a resupply directive to the Asha Dunewalker Clan.

The Dunes of Tor is resource-scarce (especially water). This directive sends
the band to Taem's Oasis whenever their hydration or nourishment drops to pressing,
loads up on potable water, and returns home.

Locations:
  Dunes of Tor  (home):   a3e98311-59ef-4972-96ea-5c03e5ef17ee
  Taem's Oasis  (source): ce21c4f7-1a7e-4637-9cb6-a1ce9aab801f
"""
import json
import sqlite3
import uuid

DB_PATH = "scenarios/oros_test_sandbox.db"

FACTION_ID = "51e20a1b-2cb0-48e1-ab39-f18776db0a56"  # Asha Dunewalker Clan
DUNES_ID   = "a3e98311-59ef-4972-96ea-5c03e5ef17ee"
TAEM_ID    = "ce21c4f7-1a7e-4637-9cb6-a1ce9aab801f"

directive = {
    "id": str(uuid.uuid4()),
    "label": "Dunes of Tor Resupply",
    "directive_type": "resupply",
    "target_location_id": TAEM_ID,
    "return_location_id": DUNES_ID,
    "cargo_manifest": {"potable_water": 8.0},
    "issued_at_tick": 0,
    "interval_ticks": 0,
    "last_triggered_tick": 0,
    "required_skill": None,
    "action_weight_modifiers": {},
    "slot_modifier": 0,
    "cargo_resource_type": None,
    "cargo_quantity": 0,
    "target_pop_id": None,
    "territory_pop_ids": [],
    "territory_location_ids": [],
}

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

row = conn.execute(
    "SELECT active_directives FROM factions WHERE id=?", (FACTION_ID,)
).fetchone()
if row is None:
    print(f"ERROR: faction {FACTION_ID} not found")
    raise SystemExit(1)

directives = json.loads(row["active_directives"] or "[]")
directives = [d for d in directives if d.get("directive_type") != "resupply"]
directives.append(directive)

conn.execute(
    "UPDATE factions SET active_directives=? WHERE id=?",
    (json.dumps(directives), FACTION_ID),
)
conn.commit()
conn.close()

print(f"Added resupply directive {directive['id']} to Asha Dunewalker Clan.")
print(f"  source: Taem's Oasis  ({TAEM_ID})")
print(f"  home:   Dunes of Tor  ({DUNES_ID})")
print(f"  cargo:  potable_water x8")
