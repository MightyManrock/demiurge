#!/usr/bin/env python3
"""Patch oros_test_sandbox.db with CollectibleResource data.

Resources are applied only to the "active" PopLocation per named area
(the node where Pops actually live, per current_location on each Pop).
Travel-network waypoint nodes are left empty.

For The Salt Flats (no Pops at start), resources go on the first node.

Omitted: cultivated sources (unimplemented), seasonal variation (deferred).
Salt has no biochem_tags for now (preservative mechanics are deferred).
"""
import sqlite3
import json

db_path = "scenarios/oros_test_sandbox.db"

# (location_id, display_name, resources_list)
PATCHES = [
    ("17b5eeae-011a-47c0-aa4f-8c7cd62c8576", "Plains of Kir'an", [
        {"resource_type": "potable_water", "max_yield": 3.5, "yield_renew_rate": 0.20,
         "action_types": ["collect"], "biochem_tags": ["solvent:water"]},
        {"resource_type": "food_fauna",    "max_yield": 4.0, "yield_renew_rate": 0.20,
         "action_types": ["hunt"],    "biochem_tags": ["basis:carbon"]},
        {"resource_type": "food_flora",    "max_yield": 4.0, "yield_renew_rate": 0.20,
         "action_types": ["forage"],  "biochem_tags": ["basis:carbon"]},
    ]),
    ("46a5dcd5-698a-4655-b03e-23be0faa6663", "Asvelim Savannah", [
        {"resource_type": "potable_water", "max_yield": 3.5, "yield_renew_rate": 0.20,
         "action_types": ["collect"], "biochem_tags": ["solvent:water"]},
        {"resource_type": "food_fauna",    "max_yield": 6.0, "yield_renew_rate": 0.20,
         "action_types": ["hunt"],    "biochem_tags": ["basis:carbon"]},
        {"resource_type": "food_flora",    "max_yield": 6.0, "yield_renew_rate": 0.20,
         "action_types": ["forage"],  "biochem_tags": ["basis:carbon"]},
    ]),
    ("b187e5a3-d31a-42a0-9f1f-f68bde37e6e5", "Qaebdol Cave Village", [
        {"resource_type": "potable_water", "max_yield": 6.0, "yield_renew_rate": 0.30,
         "action_types": ["collect"], "biochem_tags": ["solvent:water"]},
        {"resource_type": "food_fauna",    "max_yield": 2.0, "yield_renew_rate": 0.20,
         "action_types": ["hunt"],    "biochem_tags": ["basis:carbon"]},
        {"resource_type": "food_flora",    "max_yield": 2.0, "yield_renew_rate": 0.20,
         "action_types": ["forage"],  "biochem_tags": ["basis:carbon"]},
        {"resource_type": "salt_mineral",  "max_yield": 0.5, "yield_renew_rate": 0.05,
         "action_types": ["collect"], "biochem_tags": []},
    ]),
    ("a3e98311-59ef-4972-96ea-5c03e5ef17ee", "Dunes of Tor", [
        {"resource_type": "potable_water", "max_yield": 1.5, "yield_renew_rate": 0.15,
         "action_types": ["collect"], "biochem_tags": ["solvent:water"]},
        {"resource_type": "food_fauna",    "max_yield": 2.0, "yield_renew_rate": 0.20,
         "action_types": ["hunt"],    "biochem_tags": ["basis:carbon"]},
        {"resource_type": "food_flora",    "max_yield": 1.0, "yield_renew_rate": 0.15,
         "action_types": ["forage"],  "biochem_tags": ["basis:carbon"]},
        {"resource_type": "salt_mineral",  "max_yield": 2.0, "yield_renew_rate": 0.20,
         "action_types": ["collect"], "biochem_tags": []},
    ]),
    ("60cca63f-eb80-415f-a1fe-49575cb63846", "The Ancestor Stones", [
        {"resource_type": "food_flora",    "max_yield": 0.8, "yield_renew_rate": 0.10,
         "action_types": ["forage"],  "biochem_tags": ["basis:carbon"]},
    ]),
    ("ce21c4f7-1a7e-4637-9cb6-a1ce9aab801f", "Taem's Oasis", [
        {"resource_type": "potable_water", "max_yield": 8.0, "yield_renew_rate": 0.30,
         "action_types": ["collect"], "biochem_tags": ["solvent:water"]},
        {"resource_type": "food_fauna",    "max_yield": 4.0, "yield_renew_rate": 0.20,
         "action_types": ["hunt"],    "biochem_tags": ["basis:carbon"]},
        {"resource_type": "food_flora",    "max_yield": 4.0, "yield_renew_rate": 0.20,
         "action_types": ["forage"],  "biochem_tags": ["basis:carbon"]},
    ]),
    ("59e2edc9-210d-4cec-a181-9a6eaffb1ca8", "Ulum Highlands", [
        {"resource_type": "potable_water", "max_yield": 3.5, "yield_renew_rate": 0.20,
         "action_types": ["collect"], "biochem_tags": ["solvent:water"]},
        {"resource_type": "food_fauna",    "max_yield": 4.0, "yield_renew_rate": 0.20,
         "action_types": ["hunt"],    "biochem_tags": ["basis:carbon"]},
        {"resource_type": "food_flora",    "max_yield": 4.0, "yield_renew_rate": 0.20,
         "action_types": ["forage"],  "biochem_tags": ["basis:carbon"]},
        {"resource_type": "salt_mineral",  "max_yield": 0.5, "yield_renew_rate": 0.05,
         "action_types": ["collect"], "biochem_tags": []},
    ]),
    ("522506d1-b5e4-4109-b38a-b9a63d3ac536", "Hiparun's Rift", [
        {"resource_type": "potable_water", "max_yield": 5.0, "yield_renew_rate": 0.30,
         "action_types": ["collect"], "biochem_tags": ["solvent:water"]},
        {"resource_type": "food_fauna",    "max_yield": 2.0, "yield_renew_rate": 0.20,
         "action_types": ["hunt"],    "biochem_tags": ["basis:carbon"]},
        {"resource_type": "food_flora",    "max_yield": 2.0, "yield_renew_rate": 0.20,
         "action_types": ["forage"],  "biochem_tags": ["basis:carbon"]},
        {"resource_type": "salt_mineral",  "max_yield": 0.5, "yield_renew_rate": 0.05,
         "action_types": ["collect"], "biochem_tags": []},
    ]),
    # Salt Flats: no Pops at start; salt on first node
    ("c8a797bd-c293-40b0-8f4f-c0fec24e81db", "The Salt Flats", [
        {"resource_type": "salt_mineral",  "max_yield": 8.0, "yield_renew_rate": 0.30,
         "action_types": ["collect"], "biochem_tags": []},
    ]),
]

con = sqlite3.connect(db_path)
for loc_id, display_name, resources in PATCHES:
    serialized = []
    for r in resources:
        entry = dict(r)
        entry["current_yield"] = entry["max_yield"]
        serialized.append(entry)
    cur = con.execute(
        "UPDATE locations SET collectible_resources = ? WHERE id = ?",
        (json.dumps(serialized), loc_id),
    )
    status = "OK" if cur.rowcount == 1 else f"WARNING: {cur.rowcount} rows"
    print(f"  {display_name} ({loc_id[:8]}): {status}, {len(serialized)} resource(s)")

con.commit()
con.close()
print("\nDone.")
