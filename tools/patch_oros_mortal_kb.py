#!/usr/bin/env python3
"""Seed KnowledgeBase ResourceFacts for NotableMortals in oros_test_sandbox.db.

Rules:
  1. Everyone knows Plains of Kir'an + Asvelim Savannah:
       confidence=1.0 if currently there, else 0.75
  2. Asha Dunewalker Clan: Dunes of Tor, Taem's Oasis, Salt Flats at 1.0
  3. The Stonecallers: Qaebdol Cave Village, Ancestor Stones at 1.0
  4. The Hiparunites: Ulum Highlands, Hiparun's Rift at 1.0
"""
import sys, os, sqlite3, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

db_path = "scenarios/oros_test_sandbox.db"

# Active PopLocation IDs by name
LOCS = {
    "plains":    "17b5eeae-011a-47c0-aa4f-8c7cd62c8576",
    "savannah":  "46a5dcd5-698a-4655-b03e-23be0faa6663",
    "qaebdol":   "b187e5a3-d31a-42a0-9f1f-f68bde37e6e5",
    "dunes":     "a3e98311-59ef-4972-96ea-5c03e5ef17ee",
    "stones":    "60cca63f-eb80-415f-a1fe-49575cb63846",
    "oasis":     "ce21c4f7-1a7e-4637-9cb6-a1ce9aab801f",
    "highlands": "59e2edc9-210d-4cec-a181-9a6eaffb1ca8",
    "rift":      "522506d1-b5e4-4109-b38a-b9a63d3ac536",
    "saltflats": "c8a797bd-c293-40b0-8f4f-c0fec24e81db",
}

FACTION_ASHA       = "51e20a1b-2cb0-48e1-ab39-f18776db0a56"
FACTION_STONECALL  = "ca73ff78-3fff-4e30-85ac-cf573e9dd46e"
FACTION_HIPARUN    = "416be3b9-a3e5-44a5-b8ac-10e03ba95438"

FACTION_LOCS = {
    FACTION_ASHA:      ["dunes", "oasis", "saltflats"],
    FACTION_STONECALL: ["qaebdol", "stones"],
    FACTION_HIPARUN:   ["highlands", "rift"],
}

con = sqlite3.connect(db_path)
con.row_factory = sqlite3.Row

# Load collectible_resources for all active locations
cr_by_loc: dict[str, list[dict]] = {}
for key, loc_id in LOCS.items():
    row = con.execute(
        "SELECT collectible_resources FROM locations WHERE id = ?", (loc_id,)
    ).fetchone()
    if row and row["collectible_resources"]:
        cr_by_loc[key] = json.loads(row["collectible_resources"])
    else:
        cr_by_loc[key] = []

def resource_facts(loc_key: str, confidence: float) -> list[dict]:
    loc_id = LOCS[loc_key]
    facts = []
    for cr in cr_by_loc[loc_key]:
        facts.append({
            "fact_type": "resource",
            "location_id": loc_id,
            "resource_type": cr["resource_type"],
            "resource_yield": cr["max_yield"],
            "confidence": confidence,
            "learned_at_tick": 0,
        })
    return facts

mortals = con.execute("SELECT * FROM mortals").fetchall()
print(f"Seeding KB for {len(mortals)} mortal(s)...")

for row in mortals:
    mortal_id   = row["id"]
    name        = row["name"]
    current_loc = row["current_location"]
    faction_ids = json.loads(row["faction_ids"] or "[]")

    facts = []

    # Rule 1: universal locations
    for loc_key in ("plains", "savannah"):
        conf = 1.0 if current_loc == LOCS[loc_key] else 0.75
        facts.extend(resource_facts(loc_key, conf))

    # Rules 2-4: faction-specific locations
    for faction_id in faction_ids:
        for loc_key in FACTION_LOCS.get(faction_id, []):
            facts.extend(resource_facts(loc_key, 1.0))

    kb = {"facts": facts}
    cur = con.execute(
        "UPDATE mortals SET knowledge_base = ? WHERE id = ?",
        (json.dumps(kb), mortal_id),
    )
    status = "OK" if cur.rowcount == 1 else f"WARNING: {cur.rowcount} rows"
    print(f"  {name} ({mortal_id[:8]}): {status}, {len(facts)} ResourceFact(s)")

con.commit()
con.close()
print("\nDone.")
