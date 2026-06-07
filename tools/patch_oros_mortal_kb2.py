#!/usr/bin/env python3
"""Add LocationFacts, PopFacts, and RouteFacts to NotableMortal KBs in oros_test_sandbox.db.

Rules:
  1. Faction members know LocationFacts + PopFacts for their faction's territories at 1.0.
  2. All mortals know LocationFacts for the five common locations at 0.75
     (superseded by 1.0 if already known via faction).
  3. All mortals know RouteFacts for the default travel network and their
     faction's specific route(s). Costs computed via route_fact_cost().

Re-runnable: strips existing LocationFacts, PopFacts, and RouteFacts before
rebuilding so costs are always up to date.
"""
import sys, os, sqlite3, json
from uuid import UUID
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utilities.scenario_loader import load_scenario
from utilities.travel_routing import route_fact_cost

db_path = "scenarios/oros_test_sandbox.db"

FACTION_ASHA      = "51e20a1b-2cb0-48e1-ab39-f18776db0a56"
FACTION_STONECALL = "ca73ff78-3fff-4e30-85ac-cf573e9dd46e"
FACTION_HIPARUN   = "416be3b9-a3e5-44a5-b8ac-10e03ba95438"

L = {
    "plains":    "17b5eeae-011a-47c0-aa4f-8c7cd62c8576",
    "savannah":  "46a5dcd5-698a-4655-b03e-23be0faa6663",
    "qaebdol":   "b187e5a3-d31a-42a0-9f1f-f68bde37e6e5",
    "dunes":     "a3e98311-59ef-4972-96ea-5c03e5ef17ee",
    "stones":    "60cca63f-eb80-415f-a1fe-49575cb63846",
    "oasis":     "ce21c4f7-1a7e-4637-9cb6-a1ce9aab801f",
    "highlands": "59e2edc9-210d-4cec-a181-9a6eaffb1ca8",
    "rift":      "522506d1-b5e4-4109-b38a-b9a63d3ac536",
    # c8a797bd is the active (resource-seeded) Salt Flats node; c66909e4 is the
    # TN-connected waypoint node Asha actually travels to. Use the latter for routes.
    "saltflats": "c66909e4-26d0-4d1b-9e68-a3b0f9aa6abd",
}

FACTION_LOCS = {
    FACTION_ASHA:      ["dunes", "oasis", "saltflats"],
    FACTION_STONECALL: ["qaebdol", "stones"],
    FACTION_HIPARUN:   ["highlands", "rift"],
}

COMMON_LOCS = ["plains", "savannah", "dunes", "qaebdol", "highlands"]

# All directed pairs each mortal knows via the default (open) travel network
DEFAULT_TN_NODES = ["plains", "savannah", "qaebdol", "dunes", "stones", "highlands"]

# Faction-specific route pairs (cost computed dynamically via route_fact_cost)
FACTION_ROUTE_PAIRS = {
    FACTION_ASHA: [
        ("dunes", "oasis"), ("oasis", "dunes"),
        ("dunes", "saltflats"), ("saltflats", "dunes"),
        ("oasis", "saltflats"), ("saltflats", "oasis"),
    ],
    FACTION_STONECALL: [("qaebdol", "stones"), ("stones", "qaebdol")],
    FACTION_HIPARUN:   [("highlands", "rift"), ("rift", "highlands")],
}

def loc_fact(loc_id: str, confidence: float) -> dict:
    return {"fact_type": "location", "location_id": loc_id, "label": "",
            "confidence": confidence, "learned_at_tick": 0, "visit_count": 0}

def pop_fact(pop_id: str) -> dict:
    return {"fact_type": "pop", "pop_id": pop_id, "label": "",
            "interaction_count": 0, "last_interaction_tick": 0}

def make_route_fact(from_id: str, to_id: str, cost: int) -> dict:
    return {"fact_type": "route", "from_id": from_id, "to_id": to_id,
            "vehicle_type": None, "ticks_cost": cost, "confidence": 1.0,
            "learned_at_tick": 0}

# Load the full state so route_fact_cost can resolve distances and networks
state = load_scenario(db_path)

con = sqlite3.connect(db_path)
con.row_factory = sqlite3.Row

faction_pop_ids: dict[str, list[str]] = {}
for faction_id in (FACTION_ASHA, FACTION_STONECALL, FACTION_HIPARUN):
    rows = con.execute(
        "SELECT id FROM pops WHERE faction_ids LIKE ?", (f"%{faction_id}%",)
    ).fetchall()
    faction_pop_ids[faction_id] = [r["id"] for r in rows]

mortals = con.execute("SELECT * FROM mortals").fetchall()
print(f"Updating KB for {len(mortals)} mortal(s)...")

for row in mortals:
    mortal_id   = row["id"]
    name        = row["name"]
    faction_ids = json.loads(row["faction_ids"] or "[]")
    mortal      = state.mortals.get(mortal_id)

    # Keep only ResourceFacts; strip location/pop/route facts for clean rebuild
    existing_raw = row["knowledge_base"]
    all_facts: list[dict] = json.loads(existing_raw)["facts"] if existing_raw else []
    resource_facts = [f for f in all_facts if f["fact_type"] == "resource"]

    new_facts: list[dict] = []
    known_locs: dict[str, float] = {}

    # Rule 1: faction territory at 1.0
    for faction_id in faction_ids:
        for loc_key in FACTION_LOCS.get(faction_id, []):
            loc_id = L[loc_key]
            if known_locs.get(loc_id, 0.0) < 1.0:
                new_facts.append(loc_fact(loc_id, 1.0))
                known_locs[loc_id] = 1.0
        for pop_id in faction_pop_ids.get(faction_id, []):
            new_facts.append(pop_fact(pop_id))

    # Rule 2: common locations at 0.75
    for loc_key in COMMON_LOCS:
        loc_id = L[loc_key]
        if loc_id not in known_locs:
            new_facts.append(loc_fact(loc_id, 0.75))
            known_locs[loc_id] = 0.75

    # Rule 3a: default TN — all directed pairs with accurate costs
    default_ids = [L[k] for k in DEFAULT_TN_NODES]
    for from_id in default_ids:
        for to_id in default_ids:
            if from_id == to_id:
                continue
            cost = route_fact_cost(state, UUID(from_id), UUID(to_id), mortal)
            new_facts.append(make_route_fact(from_id, to_id, cost))

    # Rule 3b: faction-specific routes with accurate privileged costs
    for faction_id in faction_ids:
        for from_key, to_key in FACTION_ROUTE_PAIRS.get(faction_id, []):
            from_id, to_id = L[from_key], L[to_key]
            cost = route_fact_cost(state, UUID(from_id), UUID(to_id), mortal)
            new_facts.append(make_route_fact(from_id, to_id, cost))

    kb = {"facts": resource_facts + new_facts}
    cur = con.execute(
        "UPDATE mortals SET knowledge_base = ? WHERE id = ?",
        (json.dumps(kb), mortal_id),
    )
    status = "OK" if cur.rowcount == 1 else f"WARNING: {cur.rowcount} rows"
    added_loc   = sum(1 for f in new_facts if f["fact_type"] == "location")
    added_pop   = sum(1 for f in new_facts if f["fact_type"] == "pop")
    added_route = sum(1 for f in new_facts if f["fact_type"] == "route")

    # Print computed costs for verification
    route_costs = sorted({f["ticks_cost"] for f in new_facts if f["fact_type"] == "route"})
    print(f"  {name}: {status} (+{added_loc} loc, +{added_pop} pop, +{added_route} route, costs={route_costs})")

con.commit()
con.close()
print("\nDone.")
