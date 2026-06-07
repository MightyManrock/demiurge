#!/usr/bin/env python3
"""Add LocationFacts, PopFacts, and RouteFacts to NotableMortal KBs in oros_test_sandbox.db.

Rules:
  1. Faction members know LocationFacts + PopFacts for their faction's territories at 1.0.
  2. All mortals know LocationFacts for the five common locations at 0.75
     (superseded by 1.0 if already known via faction).
  3. All mortals know RouteFacts for the default travel network (ticks_cost=1)
     and their faction's specific route(s) at 1.0.
"""
import sys, os, sqlite3, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

db_path = "scenarios/oros_test_sandbox.db"

FACTION_ASHA      = "51e20a1b-2cb0-48e1-ab39-f18776db0a56"
FACTION_STONECALL = "ca73ff78-3fff-4e30-85ac-cf573e9dd46e"
FACTION_HIPARUN   = "416be3b9-a3e5-44a5-b8ac-10e03ba95438"

# Active PopLocation IDs
L = {
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

# Locations each faction "owns" (knows at 1.0)
FACTION_LOCS = {
    FACTION_ASHA:      ["dunes", "oasis", "saltflats"],
    FACTION_STONECALL: ["qaebdol", "stones"],
    FACTION_HIPARUN:   ["highlands", "rift"],
}

# Locations all mortals know at 0.75 (superseded by faction 1.0)
COMMON_LOCS = ["plains", "savannah", "dunes", "qaebdol", "highlands"]

# Default TN nodes (free travel, ticks_cost=1)
DEFAULT_TN_NODES = ["plains", "savannah", "qaebdol", "dunes", "stones", "highlands"]

# Faction-specific TN edges: (from_key, to_key, ticks_cost)
FACTION_ROUTES = {
    FACTION_ASHA: [
        ("dunes",    "oasis",    1),
        ("oasis",    "dunes",    1),
        ("dunes",    "saltflats", 3),
        ("saltflats", "dunes",   3),
        ("oasis",    "saltflats", 3),
        ("saltflats", "oasis",   3),
    ],
    FACTION_STONECALL: [
        ("qaebdol", "stones", 1),
        ("stones",  "qaebdol", 1),
    ],
    FACTION_HIPARUN: [
        ("highlands", "rift", 2),
        ("rift",      "highlands", 2),
    ],
}

def loc_fact(loc_id: str, confidence: float) -> dict:
    return {
        "fact_type": "location",
        "location_id": loc_id,
        "label": "",
        "confidence": confidence,
        "learned_at_tick": 0,
        "visit_count": 0,
    }

def pop_fact(pop_id: str) -> dict:
    return {
        "fact_type": "pop",
        "pop_id": pop_id,
        "label": "",
        "interaction_count": 0,
        "last_interaction_tick": 0,
    }

def route_fact(from_id: str, to_id: str, ticks_cost: int) -> dict:
    return {
        "fact_type": "route",
        "from_id": from_id,
        "to_id": to_id,
        "vehicle_type": None,
        "ticks_cost": ticks_cost,
        "confidence": 1.0,
        "learned_at_tick": 0,
    }

con = sqlite3.connect(db_path)
con.row_factory = sqlite3.Row

# Pre-load pop IDs per faction
faction_pop_ids: dict[str, list[str]] = {}
for faction_id in (FACTION_ASHA, FACTION_STONECALL, FACTION_HIPARUN):
    rows = con.execute(
        "SELECT id FROM pops WHERE faction_ids LIKE ?", (f"%{faction_id}%",)
    ).fetchall()
    faction_pop_ids[faction_id] = [r["id"] for r in rows]

mortals = con.execute("SELECT * FROM mortals").fetchall()
print(f"Updating KB for {len(mortals)} mortal(s)...")

for row in mortals:
    mortal_id  = row["id"]
    name       = row["name"]
    faction_ids = json.loads(row["faction_ids"] or "[]")

    # Load existing KB (has ResourceFacts from previous patch)
    existing_raw = row["knowledge_base"]
    facts: list[dict] = json.loads(existing_raw)["facts"] if existing_raw else []

    # Track which location IDs already have a LocationFact so we respect superseding
    known_locs: dict[str, float] = {}
    for f in facts:
        if f["fact_type"] == "location":
            known_locs[f["location_id"]] = f["confidence"]

    new_facts: list[dict] = []

    # --- Rule 1: faction territory LocationFacts + PopFacts at 1.0 ---
    for faction_id in faction_ids:
        for loc_key in FACTION_LOCS.get(faction_id, []):
            loc_id = L[loc_key]
            if known_locs.get(loc_id, 0.0) < 1.0:
                new_facts.append(loc_fact(loc_id, 1.0))
                known_locs[loc_id] = 1.0
        for pop_id in faction_pop_ids.get(faction_id, []):
            new_facts.append(pop_fact(pop_id))

    # --- Rule 2: common LocationFacts at 0.75 (unless already at higher confidence) ---
    for loc_key in COMMON_LOCS:
        loc_id = L[loc_key]
        if loc_id not in known_locs:
            new_facts.append(loc_fact(loc_id, 0.75))
            known_locs[loc_id] = 0.75

    # --- Rule 3a: default TN RouteFacts (all ordered pairs, ticks_cost=1) ---
    default_ids = [L[k] for k in DEFAULT_TN_NODES]
    for i, from_id in enumerate(default_ids):
        for to_id in default_ids:
            if from_id != to_id:
                new_facts.append(route_fact(from_id, to_id, 1))

    # --- Rule 3b: faction-specific RouteFacts ---
    for faction_id in faction_ids:
        for from_key, to_key, cost in FACTION_ROUTES.get(faction_id, []):
            new_facts.append(route_fact(L[from_key], L[to_key], cost))

    facts.extend(new_facts)
    kb = {"facts": facts}

    cur = con.execute(
        "UPDATE mortals SET knowledge_base = ? WHERE id = ?",
        (json.dumps(kb), mortal_id),
    )
    status = "OK" if cur.rowcount == 1 else f"WARNING: {cur.rowcount} rows"
    added_loc  = sum(1 for f in new_facts if f["fact_type"] == "location")
    added_pop  = sum(1 for f in new_facts if f["fact_type"] == "pop")
    added_route = sum(1 for f in new_facts if f["fact_type"] == "route")
    print(f"  {name}: {status} (+{added_loc} loc, +{added_pop} pop, +{added_route} route)")

con.commit()
con.close()
print("\nDone.")
