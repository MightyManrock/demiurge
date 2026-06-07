"""One-shot script to seed pop_state for a Pop in the Oros scenario."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from utilities.scenario_loader import load_scenario
from logic.needs_config import initialize_pop_state

DB_PATH = "scenarios/oros_test_sandbox.db"

state = load_scenario(DB_PATH)
pop = next((p for p in state.pops.values() if p.pop_state is None), None)
if pop is None:
    print("All Pops already have pop_state")
    sys.exit(0)

pop.pop_state = initialize_pop_state(pop)

conn = sqlite3.connect(DB_PATH)
conn.execute(
    "UPDATE pops SET pop_state = ? WHERE id = ?",
    (pop.pop_state.model_dump_json(), str(pop.id)),
)
conn.commit()
conn.close()
print(f"Seeded pop_state for Pop {pop.id} ({pop.name})")
print(f"  social_class: {pop.social_class}")
print(f"  size_fractional: {pop.size_fractional}")
print(f"  needs: {[n.name for n in pop.pop_state.needs]}")
