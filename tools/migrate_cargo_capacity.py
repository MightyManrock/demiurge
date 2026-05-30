"""Set cargo_capacity=50 on Durenn Vail's merchant_vessel asset."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utilities.scenario_loader import load_scenario
from utilities.scenario_exporter import export_scenario

DB = "scenarios/wardens_compact.db"

def main():
    state = load_scenario(DB)
    vail = next((m for m in state.mortals.values() if m.name == "Durenn Vail"), None)
    if vail is None:
        print("ERROR: Durenn Vail not found.")
        sys.exit(1)
    vessel = next((a for a in vail.assets if a.asset_type == "merchant_vessel"), None)
    if vessel is None:
        print("ERROR: merchant_vessel asset not found.")
        sys.exit(1)
    vessel.cargo_capacity = 50.0
    print(f"merchant_vessel cargo_capacity set to {vessel.cargo_capacity}")
    export_scenario(state, DB)
    print("Done.")

if __name__ == "__main__":
    main()
