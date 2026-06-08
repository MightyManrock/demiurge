#!/usr/bin/env python3
"""Seed KnowledgeBase facts into PopAgentState for all Pops in oros_test_sandbox.db.

Faction Pops (Stonecallers / Asha Dunewalker Clan / Hiparunites):
  Copy the corresponding mortal's KB facts (all types except DirectiveFact, which
  is regenerated each tick), then add a MortalFact for that mortal.

Band Pops (Kir'an Plains Band / Asvelim Band):
  Per spec:
  - Plains of Kir'an + Asvelim Savannah: LocationFact + ResourceFacts at 1.0,
    PopFacts for all Pops in each band
  - Cross-band: PopFacts for the other band's Pops
  - Qaebdol Cave Village: LocationFact + ResourceFacts + PopFacts for Qaebdol Pops
    — all at 0.5 confidence
  - Dunes of Tor + Ulum Highlands: LocationFact only
  - No MortalFacts (these bands don't know any named mortals)
  - RouteFacts via route_fact_cost() for TN-connected location pairs

Re-runnable: strips and rebuilds knowledge_base inside pop_state JSON blob.
"""
import sys, os, json, sqlite3
from uuid import UUID
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utilities.scenario_loader import load_scenario
from utilities.travel_routing import route_fact_cost

DB_PATH = "scenarios/oros_test_sandbox.db"

# ── IDs ──────────────────────────────────────────────────────────────────────

FACTION_ASHA      = "51e20a1b-2cb0-48e1-ab39-f18776db0a56"
FACTION_STONECALL = "ca73ff78-3fff-4e30-85ac-cf573e9dd46e"
FACTION_HIPARUN   = "416be3b9-a3e5-44a5-b8ac-10e03ba95438"

BAND_KIRAN   = "aa3d3d80-114d-4c28-a31d-5ae8ef97848e"
BAND_ASVELIM = "40766cde-4d37-498b-9a63-202023f89e27"

MORTAL_ASHA  = "f7597f6d-44e3-41f0-bdc4-a58370396b93"
MORTAL_KAEL  = "306f22fc-7fba-411f-81ee-defe83d711d7"
MORTAL_URREN = "5cff7f1d-4603-44a7-a42a-3db2ebb35d77"

L = {
    "plains":    "17b5eeae-011a-47c0-aa4f-8c7cd62c8576",
    "savannah":  "46a5dcd5-698a-4655-b03e-23be0faa6663",
    "qaebdol":   "b187e5a3-d31a-42a0-9f1f-f68bde37e6e5",
    "dunes":     "a3e98311-59ef-4972-96ea-5c03e5ef17ee",
    "stones":    "60cca63f-eb80-415f-a1fe-49575cb63846",
    "oasis":     "ce21c4f7-1a7e-4637-9cb6-a1ce9aab801f",
    "highlands": "59e2edc9-210d-4cec-a181-9a6eaffb1ca8",
    "rift":      "522506d1-b5e4-4109-b38a-b9a63d3ac536",
    "saltflats": "c66909e4-26d0-4d1b-9e68-a3b0f9aa6abd",
}

# Same node set as patch_oros_mortal_kb2.py for RouteFact computation
DEFAULT_TN_NODES = ["plains", "savannah", "qaebdol", "dunes", "stones", "highlands"]

# Resources at each band-relevant location (from DB)
LOC_RESOURCES = {
    L["plains"]:   ["potable_water", "food_fauna", "food_flora"],
    L["savannah"]: ["potable_water", "food_fauna", "food_flora"],
    L["qaebdol"]:  ["potable_water", "food_fauna", "food_flora", "salt_mineral"],
}

# ── Fact constructors ─────────────────────────────────────────────────────────

def loc_fact(loc_id: str, confidence: float = 1.0) -> dict:
    return {"fact_type": "location", "location_id": loc_id, "label": "",
            "confidence": confidence, "learned_at_tick": 0, "visit_count": 0}

def resource_fact(loc_id: str, resource_type: str, confidence: float = 1.0) -> dict:
    return {"fact_type": "resource", "location_id": loc_id,
            "resource_type": resource_type, "resource_yield": 1.0,
            "confidence": confidence, "learned_at_tick": 0}

def pop_fact(pop_id: str, confidence: float = 1.0) -> dict:
    return {"fact_type": "pop", "pop_id": pop_id, "label": "",
            "confidence": confidence, "interaction_count": 0, "last_interaction_tick": 0}

def mortal_fact(mortal_id: str, name: str, faction_ids: list) -> dict:
    return {"fact_type": "mortal", "mortal_id": mortal_id, "name": name,
            "faction_ids": faction_ids, "confidence": 1.0, "learned_at_tick": 0}

def route_fact(from_id: str, to_id: str, cost: int) -> dict:
    return {"fact_type": "route", "from_id": from_id, "to_id": to_id,
            "vehicle_type": None, "ticks_cost": cost, "confidence": 1.0,
            "learned_at_tick": 0}


def build_route_facts(state, node_ids: list[str]) -> list[dict]:
    """Build directed RouteFacts for all pairs among node_ids using route_fact_cost."""
    facts = []
    for from_id in node_ids:
        for to_id in node_ids:
            if from_id == to_id:
                continue
            cost = route_fact_cost(state, UUID(from_id), UUID(to_id))
            facts.append(route_fact(from_id, to_id, cost))
    return facts


# ── Main ─────────────────────────────────────────────────────────────────────

state = load_scenario(DB_PATH)
con = sqlite3.connect(DB_PATH)
con.row_factory = sqlite3.Row

# Build lookups
faction_map = {r["id"]: r["name"] for r in con.execute("SELECT id, name FROM factions")}
band_map    = {r["id"]: r["label"] for r in con.execute("SELECT id, label FROM bands")}

# Pop IDs grouped by faction and band
faction_pop_ids: dict[str, list[str]] = {}
for fid in (FACTION_ASHA, FACTION_STONECALL, FACTION_HIPARUN):
    rows = con.execute("SELECT id FROM pops WHERE faction_ids LIKE ?", (f"%{fid}%",)).fetchall()
    faction_pop_ids[fid] = [r["id"] for r in rows]

band_pop_ids: dict[str, list[str]] = {}
for bid in (BAND_KIRAN, BAND_ASVELIM):
    rows = con.execute("SELECT id FROM pops WHERE band_id = ?", (bid,)).fetchall()
    band_pop_ids[bid] = [r["id"] for r in rows]

qaebdol_pop_ids = [r["id"] for r in con.execute(
    "SELECT id FROM pops WHERE current_location = ?", (L["qaebdol"],)
).fetchall()]

# Mortal KB facts by mortal ID (strip DirectiveFacts)
mortal_kb_facts: dict[str, list[dict]] = {}
for row in con.execute("SELECT id, knowledge_base FROM mortals"):
    raw = row["knowledge_base"]
    all_facts = json.loads(raw)["facts"] if raw else []
    mortal_kb_facts[row["id"]] = [f for f in all_facts if f.get("fact_type") != "directive"]

# Mortal name/faction info
mortal_info = {
    MORTAL_ASHA:  {"name": "Asha Keln",  "faction_ids": [FACTION_ASHA]},
    MORTAL_KAEL:  {"name": "Kael Osh",   "faction_ids": [FACTION_HIPARUN]},
    MORTAL_URREN: {"name": "Urren",      "faction_ids": [FACTION_STONECALL]},
}

# Faction → corresponding mortal
faction_mortal = {
    FACTION_ASHA:      MORTAL_ASHA,
    FACTION_STONECALL: MORTAL_URREN,
    FACTION_HIPARUN:   MORTAL_KAEL,
}

# Pre-build band RouteFacts (nodes the bands know about)
band_known_node_ids = [L[k] for k in ("plains", "savannah", "qaebdol", "dunes", "highlands")]
band_route_facts = build_route_facts(state, band_known_node_ids)

pops = con.execute("SELECT id, name, faction_ids, band_id, pop_state FROM pops").fetchall()
print(f"Seeding KB for {len(pops)} pop(s)...\n")

for row in pops:
    pop_id    = row["id"]
    pop_name  = row["name"] or f"[{pop_id[:8]}]"
    fids      = json.loads(row["faction_ids"] or "[]")
    band_id   = row["band_id"]
    ps_raw    = row["pop_state"]
    pop_state = json.loads(ps_raw) if ps_raw else {}

    new_facts: list[dict] = []

    # ── Faction Pop ──────────────────────────────────────────────────────────
    if fids:
        faction_id = fids[0]
        mortal_id  = faction_mortal.get(faction_id)
        if mortal_id:
            # Copy mortal KB (minus directives)
            new_facts = list(mortal_kb_facts.get(mortal_id, []))
            # Add MortalFact for the faction mortal
            info = mortal_info[mortal_id]
            new_facts.append(mortal_fact(mortal_id, info["name"], info["faction_ids"]))
            tag = f"faction={faction_map.get(faction_id, faction_id[:8])}"
        else:
            tag = f"faction={faction_map.get(faction_id, faction_id[:8])} (no mortal)"

    # ── Band Pop ─────────────────────────────────────────────────────────────
    elif band_id in (BAND_KIRAN, BAND_ASVELIM):
        other_band = BAND_ASVELIM if band_id == BAND_KIRAN else BAND_KIRAN

        # Own band locations at 1.0
        for loc_key in ("plains", "savannah"):
            lid = L[loc_key]
            new_facts.append(loc_fact(lid, 1.0))
            for rt in LOC_RESOURCES[lid]:
                new_facts.append(resource_fact(lid, rt, 1.0))

        # Own band PopFacts
        for pid in band_pop_ids.get(BAND_KIRAN, []):
            new_facts.append(pop_fact(pid, 1.0))
        for pid in band_pop_ids.get(BAND_ASVELIM, []):
            new_facts.append(pop_fact(pid, 1.0))

        # Qaebdol at 0.5
        new_facts.append(loc_fact(L["qaebdol"], 0.5))
        for rt in LOC_RESOURCES[L["qaebdol"]]:
            new_facts.append(resource_fact(L["qaebdol"], rt, 0.5))
        for pid in qaebdol_pop_ids:
            new_facts.append(pop_fact(pid, 0.5))

        # Dunes + Highlands: location only
        new_facts.append(loc_fact(L["dunes"], 1.0))
        new_facts.append(loc_fact(L["highlands"], 1.0))

        # RouteFacts
        new_facts.extend(band_route_facts)

        tag = f"band={band_map.get(band_id, band_id[:8])}"

    else:
        tag = "no faction/band — skipping"
        print(f"  {pop_name}: {tag}")
        continue

    # Write updated pop_state
    pop_state["knowledge_base"] = {"facts": new_facts}
    new_ps_json = json.dumps(pop_state)
    cur = con.execute("UPDATE pops SET pop_state = ? WHERE id = ?", (new_ps_json, pop_id))
    status = "OK" if cur.rowcount == 1 else f"WARNING: {cur.rowcount} rows"

    by_type: dict[str, int] = {}
    for f in new_facts:
        by_type[f["fact_type"]] = by_type.get(f["fact_type"], 0) + 1
    print(f"  {pop_name} [{tag}]: {status} | {by_type}")

con.commit()
con.close()
print("\nDone.")
