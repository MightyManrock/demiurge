#!/usr/bin/env python3
"""Initialize PopAgentState for all Pops in oros_test_sandbox.db that lack pop_state.

Uses initialize_pop_state() from logic/needs_config.py so canonical need profiles
(nourishment + hydration split, trait modifiers, etc.) are applied correctly.
"""
import sys
import os
import sqlite3
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logic.needs_config import initialize_pop_state
from core.universe_core import Pop

db_path = "scenarios/oros_test_sandbox.db"

con = sqlite3.connect(db_path)
con.row_factory = sqlite3.Row

rows = con.execute(
    "SELECT * FROM pops WHERE pop_state IS NULL"
).fetchall()

print(f"Initializing pop_state for {len(rows)} Pop(s)...")

updated = 0
for row in rows:
    pop = Pop(
        id=row["id"],
        social_class=row["social_class"],
        wild_stratum=row["wild_stratum"],
        current_location=row["current_location"],
        size_fractional=row["size_fractional"],
        dominant_beliefs=json.loads(row["dominant_beliefs"] or "[]"),
        culture_tags=json.loads(row["culture_tags"] or "[]"),
        rider_traits=json.loads(row["rider_traits"] or "[]"),
        notable_mortal_ids=json.loads(row["notable_mortal_ids"] or "[]"),
        parent_pop_id=row["parent_pop_id"],
        child_pop_ids=json.loads(row["child_pop_ids"] or "[]"),
        splinter_cooldown=row["splinter_cooldown"] or 0,
        identity_anchor=row["identity_anchor"],
        visibility=row["visibility"] or 0.0,
        pinned=bool(row["pinned"]),
        visibility_stall_remaining=row["visibility_stall_remaining"] or 0,
        preaching_imago_id=row["preaching_imago_id"],
        preaching_goal_cooldown_until=row["preaching_goal_cooldown_until"] or 0,
        occupation=row["occupation"],
        linked_pop_ids=json.loads(row["linked_pop_ids"] or "[]"),
        active_directives=json.loads(row["active_directives"] or "[]"),
        asset_crew_for=row["asset_crew_for"],
        faction_ids=json.loads(row["faction_ids"] or "[]"),
    )

    state = initialize_pop_state(pop)
    serialized = state.model_dump_json()

    cur = con.execute(
        "UPDATE pops SET pop_state = ? WHERE id = ?",
        (serialized, str(pop.id)),
    )
    status = "OK" if cur.rowcount == 1 else f"WARNING: {cur.rowcount} rows"
    print(f"  {str(pop.id)[:8]} ({pop.social_class}:{pop.occupation}): {status}")
    updated += cur.rowcount

con.commit()
con.close()
print(f"\nDone. {updated} Pop(s) initialized.")
