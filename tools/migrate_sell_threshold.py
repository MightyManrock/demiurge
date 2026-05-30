"""Lower Durenn Vail's unobtanium sell threshold from 20 → 5."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utilities.scenario_loader import load_scenario
from utilities.scenario_exporter import export_scenario

DB = "scenarios/wardens_compact.db"

def main():
    state = load_scenario(DB)
    vail = next((m for m in state.mortals.values() if m.name == "Durenn Vail"), None)
    if vail is None or vail.civilian_state is None:
        print("ERROR: Durenn Vail not found.")
        sys.exit(1)
    for res in vail.civilian_state.inventory:
        if res.resource_type == "unobtanium":
            old = res.threshold
            res.threshold = 5.0
            print(f"unobtanium threshold: {old} → {res.threshold}")
    export_scenario(state, DB)
    print("Done.")

if __name__ == "__main__":
    main()
