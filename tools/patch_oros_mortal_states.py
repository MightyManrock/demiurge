#!/usr/bin/env python3
"""Initialize MortalAgentState for all NotableMortals in oros_test_sandbox.db that lack mortal_state.

Uses initialize_mortal_state() from logic/needs_config.py so canonical need/desire
profiles (including culture_tag-based trait modifiers) are applied correctly.
"""
import sys
import os
import sqlite3
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logic.needs_config import initialize_mortal_state
from core.universe_core import NotableMortal

db_path = "scenarios/oros_test_sandbox.db"

con = sqlite3.connect(db_path)
con.row_factory = sqlite3.Row

rows = con.execute(
    "SELECT * FROM mortals WHERE mortal_state IS NULL"
).fetchall()

print(f"Initializing mortal_state for {len(rows)} NotableMortal(s)...")

updated = 0
for row in rows:
    culture_tags_raw = row["culture_tags"]
    if isinstance(culture_tags_raw, str):
        culture_tags = json.loads(culture_tags_raw)
    else:
        culture_tags = culture_tags_raw or {}

    # Build a minimal NotableMortal to pass to initialize_mortal_state
    mortal = NotableMortal(
        id=row["id"],
        name=row["name"],
        civilization_id=row["civilization_id"],
        role=row["role"],
        status=row["status"],
        species_id=row["species_id"],
        culture_tags=culture_tags,
        belief_tags=json.loads(row["belief_tags"] or "{}"),
        personal_tags=json.loads(row["personal_tags"] or "[]"),
        status_tags=json.loads(row["status_tags"] or "[]"),
        skill_tags=json.loads(row["skill_tags"] or "[]"),
        alignment=row["alignment"] or 0.0,
        chrono_age=row["chrono_age"] or 0.0,
        bio_age=row["bio_age"] or 0.0,
        home_location=row["home_location"],
        current_location=row["current_location"],
        pop_id=row["pop_id"],
        pop_milieu=row["pop_milieu"],
        faction_ids=json.loads(row["faction_ids"] or "[]"),
        led_faction_ids=json.loads(row["led_faction_ids"] or "[]"),
    )

    state = initialize_mortal_state(mortal)
    serialized = state.model_dump_json()

    cur = con.execute(
        "UPDATE mortals SET mortal_state = ? WHERE id = ?",
        (serialized, str(mortal.id)),
    )
    status = "OK" if cur.rowcount == 1 else f"WARNING: {cur.rowcount} rows"
    print(f"  {str(mortal.id)[:8]} ({mortal.name}): {status}")
    updated += cur.rowcount

con.commit()
con.close()
print(f"\nDone. {updated} NotableMortal(s) initialized.")
