#!/usr/bin/env python3
"""Seed resource_stockpile dicts on active PopLocations in oros_test_sandbox.db."""
import sqlite3
import json

db_path = "scenarios/oros_test_sandbox.db"

PATCHES = [
    ("17b5eeae-011a-47c0-aa4f-8c7cd62c8576", "Plains of Kir'an", {
        "potable_water": 1.75, "food_fauna": 2.0, "food_flora": 2.0,
    }),
    ("46a5dcd5-698a-4655-b03e-23be0faa6663", "Asvelim Savannah", {
        "potable_water": 1.75, "food_fauna": 3.0, "food_flora": 3.0,
    }),
    ("b187e5a3-d31a-42a0-9f1f-f68bde37e6e5", "Qaebdol Cave Village", {
        "potable_water": 3.0, "food_fauna": 1.0, "food_flora": 1.0, "salt_mineral": 0.25,
    }),
    ("a3e98311-59ef-4972-96ea-5c03e5ef17ee", "Dunes of Tor", {
        "potable_water": 0.75, "food_fauna": 1.0, "food_flora": 0.5, "salt_mineral": 1.0,
    }),
    ("60cca63f-eb80-415f-a1fe-49575cb63846", "The Ancestor Stones", {
        "food_flora": 0.4,
    }),
    ("ce21c4f7-1a7e-4637-9cb6-a1ce9aab801f", "Taem's Oasis", {
        "potable_water": 4.0, "food_fauna": 2.0, "food_flora": 2.0,
    }),
    ("59e2edc9-210d-4cec-a181-9a6eaffb1ca8", "Ulum Highlands", {
        "potable_water": 1.75, "food_fauna": 2.0, "food_flora": 2.0, "salt_mineral": 0.25,
    }),
    ("522506d1-b5e4-4109-b38a-b9a63d3ac536", "Hiparun's Rift", {
        "potable_water": 2.5, "food_fauna": 1.0, "food_flora": 1.0, "salt_mineral": 0.25,
    }),
]

con = sqlite3.connect(db_path)
for loc_id, name, stockpile in PATCHES:
    cur = con.execute(
        "UPDATE locations SET resource_stockpile = ? WHERE id = ?",
        (json.dumps(stockpile), loc_id),
    )
    status = "OK" if cur.rowcount == 1 else f"WARNING: {cur.rowcount} rows"
    print(f"  {name} ({loc_id[:8]}): {status}")

con.commit()
con.close()
print("\nDone.")
